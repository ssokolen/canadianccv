import importlib.resources
import logging
from lxml import etree
import re

class SchemaError(Exception):
    """Raised when there is a generic issue parsing CCV data"""
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

    #---------------------------------------------------------------------------
    def __init__(self, schema = _cv, lov = _lov, ref = _ref):

        # Setting up default logger (which will in practice be overwritten by CCV)
        logger = logging.getLogger(__name__)
        log_format = logging.Formatter('Schema - %(levelname)s: %(message)s')
        log_handler = logging.StreamHandler()
        log_handler.setFormatter(log_format)
        logger.addHandler(log_handler)

        self.log = logger

        self._lang = "english"

        # Generating section/field tables
        self._section_lookup = {}
        self._section_lookup_by_field = {}
        self._section_lookup_by_fields = {}

        self._sections = {}

        # Walk over every section
        for _, section in etree.iterwalk(schema, tag="section"):

            section_id, section_label = self.get_ids(section)

            parent = section.getparent()
            _, parent_label = self.get_ids(parent)

            # Add to lookup table by name
            if section_label not in self._section_lookup:
                self._section_lookup[section_label] = {}
                
            if parent_label in self._section_lookup[section_label]:
                err = '"{}" is not unique within "{}"'
                err = err.format(section_label, parent_label)
                raise SchemaError(err)
            
            self._section_lookup[section_label][parent_label] = section_id

            # Generating full entry
            self._sections[section_id] = {
                "schema": section,
                "label": section_label,
                "fields": {},
                "sections": {},
            }

            # Looping through fields within each section
            fields = self._sections[section_id]["fields"]
            sections = self._sections[section_id]["sections"]

            for child in section.getchildren():

                child_id, child_label = self.get_ids(child)

                if child.tag == "field":

                    if child_label not in self._section_lookup_by_field:
                        self._section_lookup_by_field[child_label] = set()
                    
                    self._section_lookup_by_field[child_label].add(section_id)

                    if child_label in fields:
                        err = '"{}" is not unique within "{}"'
                        err = err.format(child_label, section_label)
                        raise SchemaError(err)

                    fields[child_label] = child

                elif child.tag == "section":

                    if child_label in sections:
                        err = '"{}" is not unique within "{}"'
                        err = err.format(child_label, section_label)
                        raise SchemaError(err)

                    sections[child_label] = child

        # Any section that is found within a section that has fields must be locked
        # (to prevent stakeholder from drifting out of research funding)
        for section_id in self._sections:
            section = self._sections[section_id]["schema"]

            # Trace section hierarchy
            parents = []
            parent = section.getparent()

            while parent is not None:
                parents.append(parent.get("id"))
                parent = parent.getparent()

            parents.reverse()

            lock = False

            # Ignoring the root, we look for any parent that has fields
            for i in range(1, len(parents)):
                parent_id = parents[i]
                fields = self._sections[parent_id]["fields"]

                if len(fields) > 0:
                    lock = True
                    break

            self._sections[section_id]["lock"] = lock

        # Generating type lookup table
        self._type_names = {}
        for _, elem in etree.iterwalk(schema, tag="type"):
            elem_id, elem_label = self.get_ids(elem)
            self._type_names[elem_id] = elem_label

        # Generating lov lookup table
        self._lov_categories = {}
        self._lov_ids = {}

        for _, table in etree.iterwalk(lov, tag="table"):

            table_id, table_label = self.get_ids(table)
            
            self._lov_ids[table_id] = codes = {}
            self._lov_categories[table_label] = table_id

            for _, code in etree.iterwalk(table, tag="code"):

                code_id, code_label = self.get_ids(code)
                codes[code_label] = code_id 

        # Generating ref lookup table
        self._ref_categories = {}
        
        # First pass over the meta
        for _, table in etree.iterwalk(ref, tag="table"):

            table_id, table_label = self.get_ids(table)
            self._ref_categories[table_label] = table_id

        # Second pass
        meta = {}
        for _, table in etree.iterwalk(ref, tag="table"):

            table_id, table_label = self.get_ids(table)
            meta[table_id] = {}
           
            values = {}
            
            ref_ids_raw = []
            ref_ids = []

            # Within the meta, go over values
            for _, value in etree.iterwalk(table, tag="value"):
                value_id, value_label = self.get_ids(value)

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
            for _, field in etree.iterwalk(table, tag="field"):

                field_id, field_label = self.get_ids(field)

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
        for _, table in etree.iterwalk(ref, tag = "refTable"):

            table_id, table_value = self.get_ids(table)

            if table_id not in meta:
                err = "Schema inconsistency in refTable mapping. Aborting."
                raise SchemaError(err)

            self._ref_ids[table_id] = values = {}

            for _, value in etree.iterwalk(table, tag = "value"):
                value_id, value_label = self.get_ids(value, key = "Description")

                if value_id not in meta[table_id]:
                    err = "Schema inconsistency in refTable mapping. Aborting."
                    raise SchemaError(err)
                
                meta[table_id][value_id][-1]["label"] = value_label
                values[value_label] = (value_id, meta[table_id][value_id])

    #---------------------------------------------------------------------------
    def get_ids(self, elem, key = "Name"):
        """Get XML element identifiers based on language"""
        return elem.get("id"), elem.get(self._lang + key)

    #---------------------------------------------------------------------------
    def get_section_id(self, section, parent = None):

        if section not in self._section_lookup:
            err = '"{}" section is not defined in the schema.'
            err = err.format(section)
            raise SchemaError(err)

        table = self._section_lookup[section]

        if (parent is None) and (len(table) == 1):
            return table[list(table.keys())[0]]

        if parent is None:
            err = '"{}" section is ambigious without a parent section (one of {})'
            err = err.format(section, ", ".join(table.keys()))
            raise SchemaError(err)

        if parent not in table:
            err = '"{}" section is not defined within "{}".'
            err = err.format(section, parent)
            raise SchemaError(err)

        return table[parent]

    #---------------------------------------------------------------------------
    def get_section_id_from_fields(self, fields):

        # Parsing fields in alphabetical order for consistency
        fields.sort()

        # First, check if the full set of fields has been previously stored
        full_list = "".join(fields)

        if full_list in self._section_lookup_by_fields:
            section_id = self._section_lookup_by_fields[full_list]
            section_label = self.get_section_label(section_id)
            msg = "%s has been previously identified from fields: %s"
            self.log.debug(msg, section_label, full_list)

            return section_label

        # Helper fu
        
        field_numbers = []
        section_sets = [set()]

        for field in fields:
            if field not in self._section_lookup_by_field:
                msg = "%s is not a valid field, ignoring"
                self.log.debug(msg, field)
                continue
            
            # Generating new intersection with every existing set
            n_matches = 0
            new_set = self._section_lookup_by_field[field]
            
            for i in range(len(section_sets)): 
                intersection = section_sets[i] & new_set 

                if len(intersection) > 0:
                    section_sets[i] = intersection
                    field_numbers[i-1] += 1
                    n_matches += 1

            # If there were no matches, start a new set
            if n_matches == 0:
                msg = "Generating new section set starting from %s"
                self.log.debug(msg, field)

                section_sets.append(new_set)
                field_numbers.append(1)

            # Printing out most likely set
            index = field_numbers.index(max(field_numbers)) + 1
            section_labels = [self.get_section_label(i) for i in section_sets[index]]
            msg = "Likely set of sections updated to: %s"
            self.log.debug(msg, ", ".join(sorted(section_labels)))

        # Picking off set with most fields
        index = field_numbers.index(max(field_numbers))

        # Issue an error
        if len(field_numbers) > 1:
            msg = "Only %i of %i fields were matched to the same set of sections"
            self.log.warn(msg, field_numbers[index], sum(field_numbers))

        return list(section_sets[index + 1])

    #---------------------------------------------------------------------------
    def get_section_components(self, section_id):

        if section_id not in self._sections:
            err = '"{}" section id is not defined in the schema.'
            err = err.format(section_id)
            raise SchemaError(err)

        return self._sections[section_id]

    #---------------------------------------------------------------------------
    def get_section_schema(self, section_id):

        return self.get_section_components(section_id)["schema"]

    #---------------------------------------------------------------------------
    def get_section_label(self, section_id):

        return self.get_section_components(section_id)["label"]

    #---------------------------------------------------------------------------
    def get_section_fields(self, section_id):

        return self.get_section_components(section_id)["fields"]

    #---------------------------------------------------------------------------
    def get_section_sections(self, section_id):

        return self.get_section_components(section_id)["sections"]

    #---------------------------------------------------------------------------
    def get_section_lock(self, section_id):

        return self.get_section_components(section_id)["lock"]

    #---------------------------------------------------------------------------
    def get_field_type(self, field):

        data_type = field.get("dataType")

        if data_type not in self._type_names:
            err = '"{}" type is not defined in the schema.'
            err = err.format(data_type)
            raise SchemaError(err)

        return self._type_names[data_type]

    #---------------------------------------------------------------------------
    def get_lov_id(self, value, field):

        # Double checking field type
        data_type = self.get_field_type(field)

        if data_type != "LOV":
            err = 'Processing error, {} is not an "LOV" field.'
            err = err.format(data_type)
            raise SchemaError(err)

        # Getting appropriate table
        table_id = field.get("lookupId")
        table_name = field.get("lookupEnglishExplanation")
        if table_id not in self._lov_ids:
            err = '"{}" lookup table not defined in the schema.'
            err = err.format(table_name)
            raise SchemaError(err)

        table = self._lov_ids[table_id]

        # Checking if value is in table
        if value not in table:
            err = '"{}" is not a valid value for "{}" (one of {})'
            err = err.format(value, table_name, ", ".join(table.keys()))
            raise SchemaError(err)

        return table[value]

    #---------------------------------------------------------------------------
    def get_ref_ids(self, value, field):

        # Double checking field type
        data_type = self.get_field_type(field)

        if data_type != "Reference":
            err = 'Processing error, {} is not a "Reference" field.'
            err = err.format(data_type)
            raise SchemaError(err)

        # Getting appropriate table
        table_id = field.get("lookupId")
        table_name = field.get("lookupEnglishExplanation")
        if table_id not in self._ref_ids:
            err = '"{}" reference table not defined in the schema.'
            err = err.format(table_name)
            raise SchemaError(err)

        table = self._ref_ids[table_id]

        # Checking if value is in table
        if value not in table:
            err = '"{}" is not a valid value for "{}"'
            err = err.format(value, table_name)
            raise SchemaError(err)

        return table[value]
