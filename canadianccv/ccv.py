from datetime import datetime
from lxml import etree
import os
import re
import tomlkit

from .schema import Schema, FieldError

#===============================================================================
class CCV(object):

    #---------------------------------------------------------------------------
    def __init__(self, schema = Schema()):
    
        self.schema = schema
        
        nsmap = {'generic-cv': 'http://www.cihr-irsc.gc.ca/generic-cv/1.0.0'}
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.xml = etree.Element('{%s}generic-cv' % nsmap['generic-cv'], 
                nsmap = nsmap, lang = "en", dateTimeGenerated=timestamp
        )

        self.sections = {}

    #---------------------------------------------------------------------------
    def gen_blank_entry(self, section, parent = None):

        section = self.schema.get_section_element(section, parent)

        # Initializing xml element
        xml = etree.Element("section", 
                id = section.get("id"), label = section.get("englishName"))

        return xml, section

    #---------------------------------------------------------------------------
    def gen_entry(self, entry):

        # Look up section based on entry
        section_label = None
        if "CCVSection" in entry:
            section_label = entry["CCVSection"]

        category_label = None
        if "CCVCategory" in entry:
            category_label = entry["CCVCategory"]

        # Initializing xml element
        xml, section = self.gen_blank_entry(section_label, category_label)

        # Loop through valid elements and add them
        fields = self.schema.get_field_elements(section_label, category_label)

        for field_label in fields:

            if field_label in entry:
                xml.append(self.gen_element(entry[field_label], fields[field_label]))

        # Return both entry and the xml schema it was based on 
        return xml, section

    #---------------------------------------------------------------------------
    def gen_element(self, value, field):

        # First, determine what sort of field this is
        data_type = self.schema.get_field_type(field)

        elem = etree.Element("field", 
            id = field.get("id"), label = field.get("englishName"))

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
            lov_id = self.schema.get_lov_id(value, field)
            inner = etree.Element("lov", id = lov_id)
            inner.text = value

        elif data_type == "Reference":
            ref_id, meta = self.schema.get_ref_ids(value, field)
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
    def add_entry(self, entry):

        # First generate the new xml segement to be added
        xml_entry, section = self.gen_entry(entry)

        # Then trace section hierarchy
        parents = []
        parent = section.getparent()

        while parent is not None:
            parents.append(parent.get("englishName"))
            parent = parent.getparent()

        parents.reverse()

        p0 = parents[0]
        p1 = parents[1]

        # Ensuring that the top-level section exists
        if p1 not in self.sections:
            self.sections[p1] = {}

        if p0 not in self.sections[p1]:
            xml, _ = self.gen_blank_entry(p1, p0)
            self.sections[p1][p0] = xml
            self.xml.append(xml)

        xml_parent = self.sections[p1][p0]

        # From there, keep stepping through and linking
        for i in range(2, len(parents)):
            p0 = parents[i-1]
            p1 = parents[i]

            if p1 not in self.sections:
                self.sections[p1] = {}

            if p0 not in self.sections[p1]:
                xml, _ = self.gen_blank_entry(p1, p0)
                self.sections[p1][p0] = xml
                xml_parent.append(xml)

            xml_parent = self.sections[p1][p0]

        # Which should result in the simple addition of new element to parent
        xml_parent.append(xml_entry)

    #---------------------------------------------------------------------------
    def add_entries_from_toml(self, path, **kwargs):

        if os.path.isfile(path):
            if path.endswith(".toml"):
                f = open(path)
                with f:
                    text = f.read() 
                self.add_entry(tomlkit.loads(text))
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
                        self.add_entry(tomlkit.loads(text))
                     

        
