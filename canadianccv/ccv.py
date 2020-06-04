from datetime import datetime
from lxml import etree
import os
import re
import tomlkit

from .schema import Schema, SchemaError

#===============================================================================
class CCV(object):

    #---------------------------------------------------------------------------
    def __init__(self, xml_path = None, schema = Schema()):
    
        self.schema = schema
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

        section_label = None
        if "CCVSection" in entry:
            category_label = entry["CCVSection"]
            del entry["CCVSection"]

        category_label = None
        if "CCVCategory" in entry:
            category_label = entry["CCVCategory"]
            del entry["CCVCategory"]

        # Try to infer section based on fields
        section_ids = self.schema.get_section_id_from_fields(list(entry.keys()))

        if len(section_ids) == 1:
            section_id = section_ids[0]
        else:
            if "CCVSection" is None:
                err = "Add CCVSection to explicitly identify entry sections."
                raise SchemaError

            section_id = self.schema.get_section_id(section_label, category_label)

        # Initializing xml element
        xml = self.gen_blank_entry(section_id)

        # Loop through valid elements and add them
        fields = self.schema.get_section_fields(section_id)
        sections = self.schema.get_section_sections(section_id)

        for label in entry:

            if label in fields:
                xml.append(self.gen_element(entry[label], fields[label]))
            elif label in sections:
                entry[label]["CCVSection"] = label
                entry[label]["CCVCategory"] = section_label
                xml.append(self.gen_entry(entry[label]))
            else:
                err = '"{}" is not a valid field or section in "{}"'
                err = err.format(label, section_label)

        # Return both entry and the xml schema it was based on 
        return xml

    #---------------------------------------------------------------------------
    def gen_element(self, value, schema):

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

        # Generate the new xml segement to be added and pass it on
        xml_entry = self.gen_entry(entry)

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
    def add_entries_from_toml(self, path, **kwargs):

        if os.path.isfile(path):
            if path.endswith(".toml"):
                f = open(path)
                with f:
                    text = f.read() 
                self.add_dict_entry(tomlkit.loads(text))
            else:
                err = '"path" must be a TOML file (with .toml suffix) or directory '\
                      'containing TOML files'
                raise ReadError(err)
                
        elif os.path.isdir(path):

            # Walk through directory
            for root, dirs, files in os.walk(path, **kwargs):
                for name in files:
                    name = os.path.join(root, name)

                    if name.endswith(".toml"):
                        f = open(name)
                        with f:
                            text = f.read() 
                        self.add_dict_entry(tomlkit.loads(text))
                     

        
