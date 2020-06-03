import importlib.resources
from lxml import etree
import re

class SchemaError(Exception):
    """Raised when there is a generic issue parsing CCV data"""
    pass

class SectionError(Exception):
    """Raised when there is an issue parsing CCV sections"""
    pass

class FieldError(Exception):
    """Raised when there is an issue parsing CCV section fields"""
    pass

#===============================================================================
# Loading default schema that comes with package
# Downloaded from (https://ccv-cvc-admin.ca/report/schema/doc-en.html)

def _read_schema(path):
    content = importlib.resources.read_binary('canadianccv', path)
    return etree.XML(content)

_cv = _read_schema("cv.xml")
_lov = _read_schema("lov.xml")
_ref = _read_schema("ref.xml")

#===============================================================================
class Schema(object):
    """ 
    _entries [section name][parent name] -> 
        {section: [XML], fields: [field name] -> XML}
    
    _type_names [type id] -> name

    _lov_ids [table id][lov name] -> [lov id]
    _ref_ids [table id][ref name] -> ([ref id],  [meta dicts of id, name])
    """

    #---------------------------------------------------------------------------
    def __init__(self, schema = _cv, lov = _lov, ref = _ref):

        # Generating entry lookup table
        self._entries = {}

        # Walk over every section
        for _, elem in etree.iterwalk(schema, events=("start",), tag="section"):
            section_label = elem.get("englishName")
            parent_label = elem.getparent().get("englishName")
            
            if section_label not in self._entries:
                self._entries[section_label] = {}
                
            if parent_label in self._entries[section_label]:
                err = '"{}" is not unique within "{}"'
                err = err.format(section_label, parent_label)
                raise SectionError(err)
            
            self._entries[section_label][parent_label] = {
                "section": elem, "fields": {}
            }

            # Looping through fields within each section
            fields = self._entries[section_label][parent_label]["fields"]
            for field in elem.getchildren():
                
                if field.tag != "field":
                    continue

                field_label = field.get("englishName")

                if field_label in fields:
                    err = '"{}" is not unique within "{}"'
                    err = err.format(field_label, section_label)
                    raise FieldError(err)

                fields[field_label] = field

        # Generating type lookup table
        self._type_names = {}
        for _, elem in etree.iterwalk(schema, events=("start",), tag="type"):
            self._type_names[elem.get("id")] = elem.get("englishName")

        # Generating lov lookup table
        self._lov_categories = {}
        self._lov_ids = {}

        for _, table in etree.iterwalk(lov, events=("start",), tag="table"):

            table_id = table.get("id")
            table_label = table.get("englishName")
            self._lov_ids[table_id] = codes = {}
            self._lov_categories[table_label] = table_id

            for _, code in etree.iterwalk(table, events=("start",), tag="code"):
                code_id = code.get("id")
                code_label = code.get("englishName")
                codes[code_label] = code_id 

        # Generating ref lookup table
        self._ref_categories = {}

        
        # First pass over the meta
        for _, table in etree.iterwalk(ref, events=("start",), tag="table"):

            table_id = table.get("id")
            table_label = table.get("englishName")
            self._ref_categories[table_label] = table_id


        # Second pass
        meta = {}
        for _, table in etree.iterwalk(ref, events=("start",), tag="table"):

            table_id = table.get("id")
            table_label = table.get("englishName")
            meta[table_id] = {}
           
            values = {}
            
            ref_ids_raw = []
            ref_ids = []

            # Within the meta, go over values
            for _, value in etree.iterwalk(table, events=("start",), tag="value"):
                value_id = value.get("id")
                value_label = value.get("englishName")

                if value_id == "-1":
                    table_label = re.sub(".*?\((.*?)\).*", r"\1", value_label)
                    value_label = re.sub("[ ]*\(.*?\)", "", value_label)
                    ref_ids_raw.append({"label":value_label, "table":table_label})
                else:
                    values[value_id] = value_label

            # Converting ref_ids to proper ids
            for item in ref_ids_raw:
                value_label = item["label"].strip(" ")
                table_label = item["table"].strip(" ")

                if table_label == "List Of Values":
                    ref_ids.append(self._lov_categories[value_label])
                elif table_label == "Reference Table":
                    ref_ids.append(self._ref_categories[value_label])
                else:
                    err = "Schema inconsistency in refTable mapping. Aborting."
                    raise SchemaError(err)

            # Then use those value to fill in the meta info
            for _, field in etree.iterwalk(table, events=("start",), tag="field"):

                field_id = field.get("id")
                field_label = field.get("englishName")

                ids = [v.get("id") for v in field.getchildren()]
                n = len(ids)
                meta[table_id][field_id] = [
                        {"id":ref_ids[i], "label":values[ids[i]]} for i in range(n)
                ]

                meta[table_id][field_id].append(
                        {"id":table_id, "label":""}
                )

        # With the meta information decoded, do final pass over ref table entries
        self._ref_ids = {}
        for _, table in etree.iterwalk(ref, events=("start",), tag="refTable"):

            table_id = table.get("id")

            if table_id not in meta:
                err = "Schema inconsistency in refTable mapping. Aborting."
                raise SchemaError(err)

            self._ref_ids[table_id] = values = {}

            for _, value in etree.iterwalk(table, events=("start",), tag="value"):
                value_id = value.get("id")
                value_label = value.get("englishDescription")

                if value_id not in meta[table_id]:
                    err = "Schema inconsistency in refTable mapping. Aborting."
                    raise SchemaError(err)
                
                meta[table_id][value_id][-1]["label"] = value_label
                values[value_label] = (value_id, meta[table_id][value_id])


    #---------------------------------------------------------------------------
    def get_section_components(self, section, parent = None):

        if section not in self._entries:
            err = '"{}" section is not defined in the schema.'
            err = err.format(section)
            raise SectionError(err)

        table = self._entries[section]

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
    def get_section_element(self, section, parent = None):

        return self.get_section_components(section, parent)["section"]

    #---------------------------------------------------------------------------
    def get_field_elements(self, section, parent = None):

        return self.get_section_components(section, parent)["fields"]

    #---------------------------------------------------------------------------
    def get_field_type(self, field):

        data_type = field.get("dataType")

        if data_type not in self._type_names:
            err = '"{}" type is not defined in the schema.'
            err = err.format(data_type)
            raise FieldError(err)

        return self._type_names[data_type]

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
        if table_id not in self._lov_ids:
            err = '"{}" lookup table not defined in the schema.'
            err = err.format(table_name)
            raise FieldError(err)

        table = self._lov_ids[table_id]

        # Checking if value is in table
        if value not in table:
            err = '"{}" is not a valid value for "{}" (one of {})'
            err = err.format(value, table_name, ", ".join(table.keys()))
            raise FieldError(err)

        return table[value]

    #---------------------------------------------------------------------------
    def get_ref_ids(self, value, field):

        # Double checking field type
        data_type = self.get_field_type(field)

        if data_type != "Reference":
            err = 'Processing error, {} is not a "Reference" field.'
            err = err.format(data_type)
            raise FieldError(err)

        # Getting appropriate table
        table_id = field.get("lookupId")
        table_name = field.get("lookupEnglishExplanation")
        if table_id not in self._ref_ids:
            err = '"{}" reference table not defined in the schema.'
            err = err.format(table_name)
            raise FieldError(err)

        table = self._ref_ids[table_id]

        # Checking if value is in table
        if value not in table:
            err = '"{}" is not a valid value for "{}"'
            err = err.format(value, table_name)
            raise FieldError(err)

        return table[value]
