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

class CCVWarning(UserWarning):
    pass

#===============================================================================
class CCV(object):

    #---------------------------------------------------------------------------
    def __init__(self, xml_path = None, language = "english",
                 log_path = "ccv.log", log_level = "INFO"):

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

        self._sections = {}

        nsmap = {'generic-cv': 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.xml = etree.Element('{%s}generic-cv' % nsmap['generic-cv'], 
                nsmap = nsmap, lang = "en", dateTimeGenerated = timestamp,
        )

        if xml_path is not None:

            f = open(xml_path, 'rb')
            with f:
                content = f.read()
            xml = etree.XML(content)

            msg = '# Importing existing entries from "%s" #'
            self.log.info(msg, xml_path)
            
            # Re-mapping existing sections according to specified schema
            for _, section in etree.iterwalk(xml, tag="section"):

                # If any parents have fields, do not move
                move = True
                section = Section(section, language)
                
                for parent_id in section.parent_ids:
                    parent = Section.from_id(parent_id, language)

                    if len(parent.fields) > 0:
                        move = False
                        break

                if move:
                    pass 

    #---------------------------------------------------------------------------
    # Main parsing function

    #----------------------------------------
    def add_dict(self, dct):
        """Add content of dictionary"""

        # First, determine what section this is
        section = Section.from_entries(list(dct.keys()), language = self.language)
        self.log.info("Section identified as %s", section.label)

        # Ensure parents have been generated (in reverse order)
        parent_ids = section.parent_ids.copy()
        parent_ids.reverse()

        xml = self.xml
        for parent_id in parent_ids:
            if parent_id not in self._sections:
                parent_section = Section.from_id(parent_id, language = self.language)
                new_xml = parent_section.to_xml()

                self._sections[parent_id] = new_xml
                xml.append(new_xml)
                xml = new_xml
            else:
                xml = self._section[parent_id]

        # Generate empty template (making validation more consistent)
        entries = {}

        for field in section.fields:
            entries[field] = ""

        # Then adding new entries if they are valid
        for entry in list(dct.keys()):

            # Cleaning up string entries a little
            value = dct[entry]

            try:
                value.strip(" \n\t")
            except AttributeError:
                pass

            if entry in section.fields:
                entries[entry] = value
            else:
                err = '"%s" is not a valid field or subsection in "%s"'
                self.log.warning(entry, section.label)

        # Final loop to validate and generate xml
        for field in section.field_list():

            value = entries[field.label]

            errors = field.validate(value, entries)
            if errors is not None:
                err = 'Errors validating "%s": %s'
                self.log.warning(err, field.label, errors)
                continue

            # After validation, if the value is blank, there is no need to add it
            if value is None or value == "":
                continue

            try:
                new_xml = field.to_xml(value)
            except SchemaError as e:
                err = 'Errors validating "%s": %s'
                self.log.warning(err, field.label, str(e))
                continue

            xml.append(new_xml)

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
            self.add_dict_entry(self.read_file(path))
            return

        for root, dirs, files in os.walk(path):
            for name in files:
                name = os.path.join(root, name)
                if path_check(name):
                    self.add_dict_entry(self.read_file(name))

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

        self.add_dict(yaml.safe_load(text))

    #----------------------------------------
    def add_toml(self, text):
        """Add contents of TOML formatted string"""

        self.add_dict(toml.load(text))

    #----------------------------------------
    def write_xml(self, path, pretty_print = False):
        """Write xml file to path (adds .xml extension if none provided)"""

        if not path.endswith(".xml"):
            path = path + ".xml"

        f = open(path, 'wb')
        with f:
            f.write(etree.tostring(self.xml, pretty_print = pretty_print))
