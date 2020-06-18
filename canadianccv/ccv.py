from collections import namedtuple
from datetime import datetime
import fnmatch
from lxml import etree
import logging
import os
import re
import toml
import warnings
import yaml

from .schema import *

class CCVError(Exception):
    pass


#===============================================================================
class CCV(object):

    Entry = namedtuple("Entry", ["schema", "contents"])

    #---------------------------------------------------------------------------
    def __init__(self, xml_path = None, language = "english",
                 log_path = "ccv.log", log_level = "INFO"):

        self._index = {}
        self._content = {}

        self.language = language

        # Setting up logger
        logger = logging.getLogger(__name__)
        log_format = logging.Formatter('CCV - %(levelname)s: %(message)s')

        if log_path is not None:
            log_handler = logging.FileHandler('file.log', mode = 'w')
            log_handler.setFormatter(log_format)
            logger.addHandler(log_handler)

        log_handler = logging.StreamHandler()
        log_handler.setFormatter(log_format)
        logger.addHandler(log_handler)
        logger.setLevel(log_level)

        self.log = logger

        if xml_path is not None:

            f = open(xml_path, 'rb')
            with f:
                content = f.read()
            xml = etree.XML(content)

            msg = '# Importing existing entries from "%s" #'
            self.log.info(msg, xml_path)
            
            # Re-mapping existing sections according to specified schema
            for _, section in etree.iterwalk(xml, tag = "section"):

                # If any parents have fields, do not move
                section = Section(section.get("id"))
                
                if move:
                    pass 

    #---------------------------------------------------------------------------
    # Function for adding new elements to CCV

    # ----------------------------------------
    def get_container(self, section):

        # If index already exists, return container
        if section.id in self._index:
            return self._index[section.id]

        # Get container of parent or specify main dict as parent
        parents = section.parent_list
        if len(parents) > 0:
            parent = self.get_container(parents[0])
        else:
            parent = self._content

        # Add new section to content and index
        if len(section.fields) > 0 and not section.is_dependent:
            parent[section.label] = container = []
        else:
            parent[section.label] = container = {}

        self._index[section.id] = container

        return container

    # ----------------------------------------
    def validate_content(self, section, entries):

        out = {}

        # Filling in blank fields to make validation easier
        for field in section.fields:
            
            out[field] = ""      

        # Basic parsing cleanup
        for entry in list(entries.keys()):

            value = entries[entry]

            if entry in section.fields:

                if isinstance(value, str):
                    value.strip(" \n\t")
                elif isinstance(value, dict):
                    [values[item].strip(" \n\t") for item in values]

            elif entry in section.sections:

                if isinstance(value, dict):
                    value = [value]

                subsection = Section(entry)
                for i, item in enumerate(value):
                    value[i] = self.validate_content(subsection, item)
                
            else:
                err = '"%s" is not a valid field or subsection in "%s"'
                self.log.warning(err, entry, section.label)

            out[entry] = value

        # Only validating fields for now
        for entry in section.fields:

            value = out[entry]

            field = section.field(entry)
            errors = field.validate(value, entries)
            
            if errors is not None:
                err = 'Errors validating "%s": %s'
                self.log.warning(err, field.label, errors)
                continue

            # After validation, if the value is blank, there is no need to add it
            if value is None or value == "":
                del out[entry]

        return out

    # ----------------------------------------
    def add_content(self, entries, validate = True):

        # First, determine what section this is
        try:
            section = Section.from_entries(list(entries.keys()))
        except SchemaError as e:
            self.log.warning(e)
            section = Section.from_entries(list(entries.keys()), error = False)

        if section is None:
            return

        self.log.info("Section identified as %s", section.label)

        # The section must be a top-level section (not a subsection)
        if section.is_dependent:
            err = 'A subsection like "{}" cannot be added on its own'
            raise CCVError(err)

        # Validate if required
        if validate:
            entries = self.validate_content(section, entries)

        # Then get container to put the content in
        container = self.get_container(section)

        container.append(entries)

    #---------------------------------------------------------------------------
    # Main content generation

    # ----------------------------------------
    def content_to_list(self, parent = None, entries = None):
        """Convenience function that flattens content dictionary"""

        # If there is no parent, then we are starting at root
        if parent is None:
            entries = self._content
            sections = {key:Section(key, str(None)) for key in entries}
            fields = {}
        else:
            sections = parent.sections
            fields = parent.fields
            parent_label = parent.label

        field_list = []
        section_list = []

        # First, iterate through fields
        for key in fields:
            if key in entries:
                field_list.append(self.Entry(fields[key], entries[key]))

        # Then sections
        for key in sections:
            if key in entries:
                section_list.append(self.Entry(sections[key], entries[key]))

        # External sort
        field_list.sort(key = lambda x: x.schema.order)
        section_list.sort(key = lambda x: x.schema.order)

        # Recurse into the sections
        for i, section in enumerate(section_list):

            schema = section.schema
            contents = entries[schema.label]
            
            if isinstance(contents, dict):
                section = section._replace(
                    contents = 
                        self.content_to_list(schema, contents)
                )
            else:
                sorting = reversed(schema.sorting)

                for field, direction in sorting:
                    reverse = True if direction != "asc" else False
                    section.contents.sort(
                        key = lambda x: x[field], reverse = reverse
                    )

                section = section._replace( 
                    contents = 
                        [self.content_to_list(schema, item) for item in contents]
                )

            
            section_list[i] = section

        return field_list + section_list

    # ----------------------------------------
    def content_to_xml(self, parent = None, entries = None):
        """Convenience function that flattens content dictionary"""

        Entry = namedtuple("Entry", ["schema", "contents"])

        # If there is no parent, then generate whole list
        if parent is None:
            entries = self.content_to_list(None, None)

            nsmap = {
                'generic-cv': 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'
            }
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            parent = etree.Element(
                '{%s}generic-cv' % nsmap['generic-cv'], 
                nsmap = nsmap, lang = "en", dateTimeGenerated = timestamp
            )

        # Otherwise, generate new parents
        for entry in entries:
            
            schema, content = entry

            # If we are dealing with a field, just append xml to parent
            if isinstance(schema, Field):
                parent.append(schema.to_xml(content))

            # Otherwise, initialize new container and fill it
            elif isinstance(schema, Section):
                
                # If we have a list of lists, the same schema is reused
                if isinstance(content[0], self.Entry):
                    content = [content]

                for item in content:
                    container = schema.to_xml()
                    container = self.content_to_xml(container, item)
                    parent.append(container)

        return parent

    #---------------------------------------------------------------------------
    # User functions

    #----------------------------------------
    def add_files(self, path, pattern = None):
        """Recursively add contents of files from specified path based on pattern"""

        if pattern is None:
            msg = "# Adding entries from %s #"
            self.log.info(msg, path)
        else:
            msg = "# Adding entries from %s (using pattern %s) "
            self.log.info(msg, path, pattern)

        if pattern is None:
            path_check = lambda x: True
        else:
            path_check = lambda x: fnmatch.fnmatch(x, pattern)

        if os.path.isfile(path) and path_check(path):
            self.add_content(self.read_file(path))
            return

        for root, dirs, files in os.walk(path):
            for name in files:
                name = os.path.join(root, name)
                if path_check(name):
                    self.add_content(self.read_file(name))

    #----------------------------------------
    def add_file(self, path):
        """Add contents of a single file"""

        def read_path():
            f = open(path)
            with f:
                return f.read()

        self.log.info("## Parsing %s ##", os.path.basename(path))
        
        if path.endswith(".yml") or path.endswith(".yaml"):
            self.add_yaml(read_path())
        elif path.endswith(".toml"):
            self.add_toml(read_path())
        else:
            self.log.info("Ignoring %s", os.path.basename(path))

    #----------------------------------------
    def add_yaml(self, text):
        """Add contents of YAML formatted string"""

        self.add_content(yaml.safe_load(text))

    #----------------------------------------
    def add_toml(self, text):
        """Add contents of TOML formatted string"""

        self.add_content(toml.load(text))

    #----------------------------------------
    def to_xml(self, path, pretty_print = False, sort = True):
        """Write xml file to path (adds .xml extension if none provided)"""

        xml = self.content_to_xml()

        if not path.endswith(".xml"):
            path = path + ".xml"

        f = open(path, 'wb')
        with f:
            f.write(etree.tostring(xml, pretty_print = pretty_print))
