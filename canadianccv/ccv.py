from datetime import datetime
import fnmatch
from lxml import etree
import logging
import os
import re
import tomlkit
import warnings
import yaml

from .schema import Schema, SchemaError

class CCVWarning(UserWarning):
    pass

#===============================================================================
class CCV(object):

    #---------------------------------------------------------------------------
    def __init__(self, xml_path = None, log_path = "ccv.log", 
                 log_level = logging.INFO,  schema = Schema()):

        # Setting schema
        self.schema = schema

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

        self.log = logger
        # Overriding Schema logger with CCV one
        self.schema.log = self.log

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

                section_id = section.get("id")
                lock = self.schema.get_section_lock(section_id)

                if not lock:
                    self.add_xml_entry(section) 

    #---------------------------------------------------------------------------
    def gen_blank_entry(self, section_id):

        section_schema = self.schema.get_section_schema(section_id)
        section_id, section_label = self.schema.get_ids(section_schema)

        # Initializing xml element
        xml = etree.Element("section", id = section_id, label = section_label)

        return xml

    #---------------------------------------------------------------------------
    def gen_entry(self, entry):

        # Start with null section id
        section_id = None

        # Check if explicit section provided
        if "CCVSection" in entry:
            section_label = entry["CCVSection"]
            del entry["CCVSection"]
            
            try:
                category_label, section_label = section_label.split("/")
            except ValueError:
                category_label = None
                msg = "Section identified as %s from CCVSection entry"
                self.log.info(msg, section_label)
            else:
                msg = "Section identified as %s/%s from CCVSection entry"
                self.log.info(msg, category_label, section_label)

            try:
                section_id = self.schema.get_section_id(
                    section_label, category_label
                )
            except SchemaError as e:
                self.log.warning(e)
                warnings.warn(e, CCVWarning)
            
        if section_id is None:
            self.log.info("Attempting to infer entries based on fields")
            section_ids = self.schema.get_section_id_from_fields(list(entry.keys()))

            if len(section_ids) == 1:
                section_id = section_ids[0]
                section_xml = self.schema.get_section_schema(section_id)
                _, section_label = self.schema.get_ids(section_xml)
            elif section_id:
                msg = "CCV section could not be uniquely inferred from field names."
                self.log.error(msg)

        if section_id is None:
            msg = "CCV section could not be determined. See logs for details."
            self.log.info(msg)
            warnings.warn(msg, CCVWarning)
            return

        # Initializing xml element
        xml = self.gen_blank_entry(section_id)

        # Loop through valid elements and add them
        fields = self.schema.get_section_fields(section_id)
        sections = self.schema.get_section_sections(section_id)

        # Listing valid and invalid sections
        valid_fields = [field for field in entry if field in fields]
        if len(valid_fields) > 0:
            msg = "The following entries correspond to valid fields: %s"
            self.log.info(msg, ", ".join(valid_fields))

        valid_sections = [section for section in entry if section in sections]
        if len(valid_sections) > 0:
            msg = "The following entries correspond to valid sections: %s"
            self.log.info(msg, ", ".join(valid_sections))

        all_labels = list(fields.keys()) + list(sections.keys())
        invalid_labels = [label for label in entry if label not in all_labels]
        if len(invalid_labels) > 0:
            msg = "The following entries are invalid and will be ignored: %s"
            self.log.warning(msg, ", ".join(invalid_labels))

        # Parsing
        for field in valid_fields:
            xml.append(self.gen_element(entry[field], fields[field]))

        for section in valid_sections:
            entry[section]["CCVSection"] = section_label + "/" + section
            xml.append(self.gen_entry(entry[section]))

        # Return both entry and the xml schema it was based on 
        return xml

    #---------------------------------------------------------------------------
    def gen_element(self, value, schema):

        # All values should be strings
        value = str(value)

        # First, determine what sort of field this is
        data_type = self.schema.get_field_type(schema)

        field_id, field_label = self.schema.get_ids(schema)
        elem = etree.Element("field", id = field_id, label = field_label)

        # And then parse based on type
        inner = None

        if data_type == "Year":
            inner = etree.Element("value", format = "yyyy", type = data_type)
            inner.text = value

        elif data_type == "Year Month":
            inner = etree.Element("value", format = "yyyy/MM", type = data_type)
            inner.text = value

        elif data_type == "Month Day":
            inner = etree.Element("value", format = "MM/dd", type = data_type)
            inner.text = value

        elif data_type == "Date":
            inner = etree.Element("value", format = "yyyy-MM-dd", type = data_type)
            inner.text = value

        elif data_type == "Datetime":
            pass

        elif data_type == "String":
            inner = etree.Element("value", type = data_type)
            inner.text = value

        elif data_type == "Integer":
            inner = etree.Element("value", type = "Number")
            inner.text = value

        elif data_type == "LOV":
            lov_id = self.schema.get_lov_id(value, schema)
            inner = etree.Element("lov", id = lov_id)
            inner.text = value

        elif data_type == "Reference":
            ref_id, meta = self.schema.get_ref_ids(value, schema)
            inner = etree.Element("refTable", refValueId = ref_id)

            for link in meta:
                link = etree.Element("linkedWith", 
                    label = "x", value = link["label"], refOrLovId = link["id"]
                )
                inner.append(link)

        elif data_type == "Bilingual":
            inner = etree.Element("value", type = "Bilingual")
            inner.append(etree.Element("english"))
            inner.append(etree.Element("french"))
            inner[0].text = value
        
        elif data_type == "PubMed":
            pass
        
        elif data_type == "Elapsed-Time":
            pass

        if inner is None:
            # Defining generic error message for missing implementations
            err = '"{}" data type is not currently supported. ' \
                  'Contact the package author with an XML example of field data.'
            err = err.format(data_type)
            raise FieldError(err)

        elem.append(inner)

        return elem

    #---------------------------------------------------------------------------
    def add_dict_entry(self, entry):

        if entry is None:
            return

        # Generate the new xml segement to be added and pass it on
        xml_entry = self.gen_entry(entry)

        if xml_entry is None:
            return

        self.add_xml_entry(xml_entry)

    #---------------------------------------------------------------------------
    def add_xml_entry(self, entry):

        schema = self.schema.get_section_schema(entry.get("id"))

        # Then trace section hierarchy
        parents = []
        parent = schema.getparent()

        while parent is not None:
            parents.append(parent.get("id"))
            parent = parent.getparent()

        parents.reverse()

        xml_parent = self.xml

        # From there, step through parents and link
        for i in range(1, len(parents)):
            section_id = parents[i]

            if section_id not in self._sections:
                xml = self.gen_blank_entry(section_id)
                xml_parent.append(xml)
                self._sections[section_id] = xml

            xml_parent = self._sections[section_id]

        # Which should result in the simple addition of new element to parent
        xml_parent.append(entry)

    #---------------------------------------------------------------------------
    # File handling

    #----------------------------------------
    def read_file(self, path):

        if path.endswith(".yml") or path.endswith(".yaml"):
            return self.read_yaml(path)
        elif path.endswith(".toml"):
            return self.read_toml(path)
        else:
            self.log.debug("Ignoring %s", os.path.basename(path))

    #----------------------------------------
    def read_toml(self, path):
        """Read path to TOML file into dictionary"""

        self.log.info("## Parsing %s ##", os.path.basename(path))

        f = open(path)
        with f:
            text = f.read() 

        return tomlkit.loads(text)

    #----------------------------------------
    def read_yaml(self, path):
        """Read path to YAML file into dictionary"""

        self.log.info("## Parsing %s ##", os.path.basename(path))

        f = open(path)
        with f:
            text = f.read() 

        return yaml.safe_load(text)

    #---------------------------------------------------------------------------
    def add_entries(self, path, pattern = None):
        """Recursively add XML entries from specified path based on pattern"""

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
