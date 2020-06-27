from collections import namedtuple
import fnmatch
from lxml import etree
import logging
import os
import re
import toml
import warnings
import yaml
from yaml.constructor import SafeConstructor

from .schema import *
from .schema import _wrapper, _schema

class CCVError(Exception):
    pass



# Hack to avoid Yes -> True Yaml conversion
def _add_bool(self, node):
    return self.construct_scalar(node)

SafeConstructor.add_constructor(u'tag:yaml.org,2002:bool', _add_bool)

# Setting up logger
def _add_logger():
    logger = logging.getLogger("CCV")
    log_format = logging.Formatter('CCV - %(levelname)s: %(message)s')

    log_handler = logging.FileHandler('ccv.log', mode = 'w')
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)

    log_handler = logging.StreamHandler()
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)
    logger.setLevel("INFO")

_add_logger()


#===============================================================================
class CCV(object):

    Entry = namedtuple("Entry", ["schema", "contents"])

    #---------------------------------------------------------------------------
    def __init__(self, xml_path = None, language = "english"):

        self._index = {}
        self._content = {}

        self.language = language
        self.log = logging.getLogger("CCV")

        if xml_path is not None:

            f = open(xml_path, 'rb')
            with f:
                content = f.read()
            xml = etree.XML(content)

            msg = '# Importing existing entries from "%s" #'
            self.log.info(msg, xml_path)
            
            # Re-mapping existing sections according to specified schema
            for _, section_xml in etree.iterwalk(xml, tag = "section"):

                # If any parents have fields, do not move
                section = XML(section_xml, language)
                section = Section(section.id)

                if section.is_container:
                    self.get_container(section)
                if not section.is_dependent:
                    self.add_content(self.parse_xml(section_xml), section)

            msg = '# Finished importing #'
            self.log.info(msg)

    #---------------------------------------------------------------------------
    # Function for parsing exising xml

    # ----------------------------------------
    def parse_xml(self, xml, content = None):

        if content is None:
            content = {}

        entry = XML(xml, self.language)
        entry = Section(entry.id)

        for field_xml in xml.iterchildren("field"):

            field = XML(field_xml, self.language)
            field = Field(field.id)

            # Bilingual and Reference require special parsing
            xml_children = field_xml.getchildren()
            if len(xml_children) == 0:
                wrn = '"%s" does not have a value, ignoring.'
                self.log.warning(wrn, field.label)
                continue
            elif field.type.label == "Reference":
                reference = xml_children[0].getchildren()[-1]
                value = field.reference.get_value(reference.get("value"))
                value = value.label
            elif field.type.label == "Bilingual":
                value = {}
                for component_xml in xml_children[1].getchildren():
                    value[component_xml.tag] = component_xml.text
            else:
                value = field_xml.getchildren()[0].text

            if value is None:
                value = ""
            content[field.label] = value

        # Most sections, the question is whether there is one or multiple
        for section_xml in xml.iterchildren("section"):

            section = XML(section_xml, self.language)
            section = Section(section.id)

            if section.label in content:

                if isinstance(content[section.label], dict):
                    content[section.label] = [content[section.label]]
                    
                content[section.label].append(self.parse_xml(section_xml))

            else:
                content[section.label] = self.parse_xml(section_xml)

        return content

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

                # Essentially, values can be strings or dicts
                if isinstance(value, dict):
                    values = []
                    for key in value:
                        if value[key] is None:
                            value[key] = ""
                        
                        value[key] = str(value[key])
                        values.append(value[key].strip(" \n\t"))
                else:
                    value = str(value)
                    value.strip(" \n\t")

            elif entry in section.sections:

                if isinstance(value, dict):
                    value = [value]

                subsection = Section(entry, section.label)
                for i, item in enumerate(value):
                    value[i] = self.validate_content(subsection, item)
                
            else:
                err = '"%s" is not a valid field or subsection in "%s"'
                self.log.warning(err, entry, section.label)

            out[entry] = value

        # Only validating fields for now
        for entry in section.fields:

            value = out[entry]

            # Hack as some entries still sneak through None
            if value is None:
                out[entry] = value = ""

            field = section.field(entry)
            errors = field.validate(value, out)
            
            if errors is not None:
                err = 'Errors validating "%s": %s'
                self.log.warning(err, field.label, errors)
                continue

        # After validation, if the value is blank, there is no need to add it
        for entry in section.fields:
            if out[entry] is None or out[entry] == "":
                del out[entry]

        return out

    # ----------------------------------------
    def add_content(self, entries, section = None, validate = True):

        # First, determine what section this is
        if section is None:
            try:
                section = Section.from_entries(list(entries.keys()))
            except SchemaError as e:
                self.log.warning(e)
                section = Section.from_entries(list(entries.keys()), error = False)

        # If section is none, then we are at the root, and it would be easier
        # to iterate through each component manually
        if section is None:
            for key in entries:
                self.add_content(entries[key], Section(key, str(None)), validate)

            return

        # If entries is a list, then split up the additions
        if isinstance(entries, list):
            for item in entries:
                self.add_content(item, section, validate)

            return

        self.log.info("Section identified as %s", section.label)

        # The section must be a top-level section (not a subsection)
        if section.is_dependent:
            err = 'A subsection like "%s" cannot be added on its own'
            raise CCVError(err, section.label)

        # Validate if required
        if validate:
            entries = self.validate_content(section, entries)

        # Then get container to put the content in
        container = self.get_container(section)

        if isinstance(container, list):
            container.append(entries)
        else: 
            container.update(entries)

    #---------------------------------------------------------------------------
    # Main content generation

    # ----------------------------------------
    def get_content(self, schema):

        if isinstance(schema, Root):
            return self.content_to_list(Root(), self._content)

        if not schema.is_container:
            err = 'Invalid section -- "{}" may refer to multiple entries'
            err = err.format(schema.label)
            raise CCVError(err)

        if schema.id not in self._index:
            err = 'Invalid section -- CCV does not contain "{}"'
            err = err.format(schema.label)
            raise CCVError(err)

        return self.content_to_list(schema, self._index[schema.id])

    # ----------------------------------------
    def content_to_list(self, schema, entries):
        """Convenience function that flattens content dictionary"""

        # If entries is actually a list, the move one level up in hierarchy
        if isinstance(entries, list):
            entries = {schema.label: entries}
            schema = schema.parent 

        field_list = []
        section_list = []

        # First, iterate through fields
        fields = schema.fields
        for key in fields:
            if key in entries:
                field_list.append(self.Entry(fields[key], entries[key]))

        # Then sections
        sections = schema.sections
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
                        key = lambda x: x[field] if field in x else "", 
                        reverse = reverse
                    )

                section = section._replace( 
                    contents = 
                        [self.content_to_list(schema, item) for item in contents]
                )

            
            section_list[i] = section

        return field_list + section_list

    # ----------------------------------------
    def content_to_xml(self, xml, entries):

        # Otherwise, generate new parents
        for entry in entries:
            
            schema, content = entry

            # If we are dealing with a field, just append xml to parent
            if isinstance(schema, Field):
                xml.append(schema.to_xml(content))

            # Otherwise, initialize new container and fill it
            elif isinstance(schema, Section):
                
                # If we have a list of lists, the same schema is reused
                if isinstance(content[0], self.Entry):
                    content = [content]

                for item in content:
                    container = schema.to_xml()
                    container = self.content_to_xml(container, item)
                    xml.append(container)

        return xml 

    # ----------------------------------------
    def content_to_yaml(self, yaml, entries, **kwargs):

        global _wrapper
        wrapper = copy.deepcopy(_wrapper)

        # Unpacking kwargs
        defaults = {
            "indent_level": 0,
            "prefix": ""
        }
        opts = dict(defaults, **kwargs)
        prefix = opts["prefix"]
        indent = opts["indent_level"]

        indent1 = _wrapper.initial_indent
        indent2 = _wrapper.subsequent_indent

        prefix1 = prefix
        prefix2 = ' ' * len(prefix) 

        wrapper.initial_indent = indent1 * indent + prefix1
        wrapper.subsequent_indent = indent2 * indent + prefix2

        # Otherwise, generate new parents
        for entry in entries:

            schema, content = entry

            # If we are dealing with a field add it
            if isinstance(schema, Field):
                yaml.extend(schema.to_yaml(content, wrapper))

            # Otherwise, initialize new container and fill it
            elif isinstance(schema, Section):
                
                yaml.extend(schema.to_yaml(wrapper))

                opts["indent_level"] = indent + 1

                # If we have a list of lists, then add yaml dashes 
                if isinstance(content[0], self.Entry):
                    self.content_to_yaml(yaml, content, **opts)
                elif len(content) == 1:
                    self.content_to_yaml(yaml, content[0], **opts)
                else: 
                    for item in content:
                        lines = []
                        opts["prefix"] = "- "
                        self.content_to_yaml(lines, item[:1],  **opts)

                        opts["prefix"] = "  "
                        self.content_to_yaml(lines, item[1:],  **opts)

                        yaml.extend([""] + lines)

        return yaml


    #---------------------------------------------------------------------------
    # User functions for content addition

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
            self.add_file(path)
            return

        for root, dirs, files in os.walk(path):
            for name in files:
                name = os.path.join(root, name)
                if path_check(name):
                    self.add_file(name)

    #----------------------------------------
    def add_file(self, path):
        """Add contents of a single file"""

        self.log.info("## Parsing %s ##", os.path.basename(path))

        f = open(path)
        with f:
            content = f.read()
        
        if len(content) < 1:
            self.log.info("No content found, ignoring...")
        else:
            
            if path.endswith(".yml") or path.endswith(".yaml"):
                self.add_yaml(content)
            elif path.endswith(".toml"):
                self.add_toml(content)
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

    #---------------------------------------------------------------------------
    # User functions for output

    #----------------------------------------
    def to_xml(self, path, *args, **kwargs):
        """Write xml file to path (adds .xml extension if none provided)"""

        if len(args) == 0:
            schema = Root()
        else:
            schema = Section(*args)

        entries = self.get_content(schema)
        xml = self.content_to_xml(schema.to_xml(), entries)

        if not path.endswith(".xml"):
            path = path + ".xml"

        f = open(path, 'wb')
        with f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(etree.tostring(xml, **kwargs))

    #----------------------------------------
    def to_yaml(self, path, *args):
        """Write yaml file to path (adds .yaml extension if none provided)"""

        # Prevent wrapping from losing information
        global _wrapper
        wrapper = copy.deepcopy(_wrapper)
        wrapper.max_lines = 100

        if len(args) == 0:
            schema = Root()
        else:
            schema = Section(*args)
        
        entries = self.get_content(schema)
        yaml = self.content_to_yaml([], entries)

        _wrapper = wrapper

        if not path.endswith(".yaml"):
            path = path + ".yaml"

        f = open(path, 'w')
        with f:
            f.write("\n".join(yaml))
