from lxml import etree
import os
import re
import tomlkit

from . import schema

class ReadError(Exception):
    """Raised when there is a generic issue parsing CCV data"""
    pass

class SectionError(Exception):
    """Raised when there is an issue parsing or generating CCV sections"""
    pass

class FieldError(Exception):
    """Raised when there is an issue parsing or generating CCV section fields"""
    pass

#===============================================================================
class CCV(object):

    #---------------------------------------------------------------------------
    def __init__(self, schema = schema.cv, lov = schema.lov, ref = schema.ref):
        self.schema = schema
        self.lov = lov
        self.ref = ref

        # Generating section and field lookup table
        self._sections = {}
        self._fields = {}

        for _, elem in etree.iterwalk(schema, events=("start",), tag="section"):
            label = elem.get("englishName")
            parent_label = elem.getparent().get("englishName")
            
            if label not in self._sections:
                self._sections[label] = { parent_label: elem }
            else:
                if parent_label in self._sections[label]:
                    err = '"{}" is not unique within "{}"'
                    err = err.format(label, parent_label)
                    raise SectionError(err)
                else:
                    self._sections[label][parent_label] = elem

            # Looping through fields within each section
            code = elem.get("id")
            self._fields[code] = {}

            for child in elem.getchildren():
                if child.tag == "field":
                    child_label = child.get("englishName")

                    if label in self._fields[code]:
                        err = '"{}" is not unique within "{}"'
                        err = err.format(child_label, child)
                        raise FieldError(err)
                    else:
                        self._fields[code][child_label] = child

        # Generating type lookup table
        self._types = {}
        for _, elem in etree.iterwalk(schema, events=("start",), tag="type"):
            self._types[elem.get("id")] = elem.get("englishName")

        # Generating type lookup table
        self._lov = {}
        for _, elem in etree.iterwalk(lov, events=("start",), tag="table"):
            self._lov[elem.get("id")] = {}

            for _, code in etree.iterwalk(elem, events=("start",), tag="code"):
                self._lov[elem.get("id")][code.get("englishName")] = code.get("id")

        # Reference tables are a bit more annoying -- each "final" value like
        # "Dalhousie University" carries with it reference metainformation such as
        # (Canada, Nova Scotia, Academic) so the lookup process is:
        # table id -> entry -> entry_id -> meta_ids -> meta
        
        # Simplifying this information yields 
        #   entry -> {id: string, meta: ((name, id), ...)

    #---------------------------------------------------------------------------
    def get_section_element(self, section, parent = None):

        if section not in self._sections:
            err = '"{}" section is not defined in the schema.'
            err = err.format(section)
            raise SectionError(err)

        table = self._sections[section]

        if (parent is None) and (len(table) == 1):
            return table[list(table.keys())[0]]

        if parent is None:
            err = '"{}" section is ambigious without a parent section (one of {})'
            err = err.format(section, ", ".join(table.keys()))
            raise SectionError(err)

        if parent not in table:
            err = '"{}" section is not defined within "{}".'
            err = err.format(section, parent)
            raise SectionError(err)

        return table[parent]

    #---------------------------------------------------------------------------
    def get_field_elements(self, section, parent = None):

        # First, get section
        section = self.get_section_element(section, parent)

        # And then use code to lookup fields
        return self._fields[section.get("id")]

    #---------------------------------------------------------------------------
    def get_field_type(self, field):

        data_type = field.get("dataType")

        if data_type not in self._types:
            err = '"{}" type is not defined in the schema.'
            err = err.format(data_type)
            raise FieldError(err)

        return self._types[data_type]

    #---------------------------------------------------------------------------
    def get_lov_id(self, value, field):

        # Double checking field type
        data_type = self.get_field_type(field)

        if data_type != "LOV":
            err = 'Processing error, {} is not an "LOV" field.'
            err = err.format(data_type)
            raise FieldError(err)

        # Getting appropriate table
        table_id = field.get("lookupId")
        table_name = field.get("lookupEnglishExplanation")
        if table_id not in self._lov:
            err = 'No lookup table "{}" defined in the schema.'
            err = err.format(table_name)
            raise FieldError(err)

        table = self._lov[table_id]

        # Checking if value is in table
        if value not in table:
            err = '"{}" is not a valid value for "{}" (one of {})'
            err = err.format(value, table_name, ", ".join(table.keys()))
            raise FieldError(err)

        return table[value]

    #---------------------------------------------------------------------------
    def gen_entry(self, entry):

        # Look up section based on entry
        section_label = None
        if "CCVSection" in entry:
            section_label = entry["CCVSection"]

        category_label = None
        if "CCVCategory" in entry:
            category_label = entry["CCVCategory"]

        section = self.get_section_element(section_label, category_label)
        fields = self.get_field_elements(section_label, category_label)

        # Initializing xml element
        xml = etree.Element("section", 
                id = section.get("id"), label = section.get("englishName"))

        # Loop through valid elements and add them
        for field_label in fields:

            if field_label in entry:
                element = self.gen_element(entry[field_label], fields[field_label])

    #---------------------------------------------------------------------------
    def gen_element(self, value, field):

        # First, determine what sort of field this is
        data_type = self.get_field_type(field)

        # Defining generic error message for missing implementations
        err = '"{}" data type is not currently supported due to lack of examples. ' \
              'Contact the package author with an XML example of field data.'
        err = err.format(data_type)

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
            inner = etree.Element("lov", id = self.get_lov_id(value, field))
            inner.text = value
        elif data_type == "Reference":
            pass
        elif data_type == "Bilingual":
            pass
        elif data_type == "PubMed":
            pass
        elif data_type == "Elapsed-Time":
            pass

        if inner is not None:
            elem.append(inner)

        print(etree.tostring(elem))

        print(value)

    #---------------------------------------------------------------------------
    def add_entries_from_toml(self, path, **kwargs):

        if os.path.isfile(path):
            if path.endswith(".toml"):
                f = open(path)
                with f:
                    text = f.read() 
                #self.add_entry(tomlkit.loads(text))
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
                        self.gen_entry(tomlkit.loads(text))
                     

        
