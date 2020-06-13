import importlib.resources
import locale
import logging
from lxml import etree
import re

locale.setlocale(locale.LC_ALL, "")

class SchemaError(Exception):
    """Raised when there is a generic issue parsing CCV data"""
    pass

#===============================================================================
class Schema(object):

    _section_by_id = {}
    _section_by_label = {}

    # This table has indexes of section entry labels and values of section id sets
    _section_id_by_entry = {}

    _field_by_id = {}
    # Fielf by label gets messy so its moved within Section

    _lov_by_id = {}
    _lov_by_label = {}

    _ref_by_id = {}
    _ref_by_label = {}

    _type_by_id = {}
    _type_by_label = {}

    #---------------------------------------------------------------------------
    def __init__(self, language = "english", cv = None, lov = None, ref = None):

        # Default schema
        def read_xml(path):
            #content = importlib.resources.read_binary('canadianccv', path)
            f = open(path, 'rb')
            with f:
                content = f.read()
            return etree.XML(content)

        cv = cv if cv is not None else read_xml("cv.xml")
        lov = cv if lov is not None else read_xml("cv-lov.xml")
        ref = cv if ref is not None else read_xml("cv-ref-table.xml")

        # Setting up default logger
        logger = logging.getLogger(__name__)
        log_format = logging.Formatter('Schema - %(levelname)s: %(message)s')
        log_handler = logging.StreamHandler()
        log_handler.setFormatter(log_format)
        logger.addHandler(log_handler)

        self._log = logger

        # Common function for adding lookup entries if not already in dct
        def check_add(key, value, dct, table_name = None):
            if key not in dct:
                dct[key] = value
            elif table_name is not None and key is not None:
                err = '"{}" is not unique within "{}"'
                err = err.format(key, table_name)
                raise SchemaError(err)

        # Section lookup tables
        for _, xml in etree.iterwalk(cv, tag="section"):

            section = Entry(xml, language)

            # Section by id
            lookup = self._section_by_id
            check_add(section.id, xml, lookup, "cv-xml")

            # Section by name
            lookup = self._section_by_label
            check_add(section.label, {}, lookup)

            lookup = self._section_by_label[section.label]
            check_add(section.parent.label, xml, lookup, section.label)

            # Section by entry
            for child in xml.getchildren():

                # Using a generic schema class for either section or field
                entry = Entry(child, language)

                lookup = self._section_id_by_entry
                check_add(entry.label, set(), lookup)

                lookup[entry.label].add(section.id)

                # Adding to field lists
                if child.tag == "field":

                    # Field by id
                    lookup = self._field_by_id
                    check_add(entry.id, child, lookup, "cv-xml")

        # LOV lookup tables 
        for _, xml in etree.iterwalk(lov, tag="table"):

            entry = Entry(xml, language)

            # LOV by id
            lookup = self._lov_by_id
            check_add(entry.id, xml, lookup, "cv-lov")

            # LOV by name
            lookup = self._lov_by_label
            check_add(entry.label, xml, lookup, "cv-lov")

        # Ref table lookup tables 
        for _, xml in etree.iterwalk(ref, tag="table"):

            entry = Entry(xml, language)

            # Generating arbitrary container to hold both table and refTable entries
            container = etree.Element("container", **xml.attrib)
            container.append(xml)

            # Ref table by id
            lookup = self._ref_by_id
            check_add(entry.id, container, lookup, "cv-ref-table")

            # Ref table by name
            lookup = self._ref_by_label
            check_add(entry.label, container, lookup, "cv-ref-table")

        # Adding second component of ref tables
        for _, xml in etree.iterwalk(ref, tag="refTable"):

            entry = Entry(xml, language)

            # Manually combining xml code
            lookup = self._ref_by_id
            if entry.id not in lookup:
                err = 'No matching table for refTable "{}"'.format(entry.id)
                raise SchemaError(err)
            else:
                lookup[entry.id].append(xml)

        # Data types
        for _, xml in etree.iterwalk(cv, tag="type"):

            entry = Entry(xml, language)

            # Type by id
            lookup = self._type_by_id
            check_add(entry.id, xml, lookup, "cv-lov")

            # LOV by name
            lookup = self._type_by_label
            check_add(entry.label, xml, lookup, "cv-lov")

            
#===============================================================================
class Entry(Schema):
    """
    A generic wrapper around an lxml Element that exposes commonly used tags as
    well as a lookup classemethod.
    """

    def __init__(self, xml, language = "english"):
        self.xml = xml
        self._language = language

        self.id = xml.get("id")
        self.name = xml.get(language + "Name")
        self.description = xml.get(language + "Description")
        self.label = self.name if self.name is not None else self.description

        self.order = xml.get("orderIndex")
        self.type_id = xml.get("dataType")
        self.lookup_id = xml.get("lookupId")
        self.lookup_label = xml.get("lookup" + language + "Explanation")

        self.parent = None 
        if xml.getparent() is not None:
            self.parent = Entry(xml.getparent(), language)

    @classmethod
    def from_keys(cls, keys, lookup, language = "english", cache = None):

        keys.reverse()
        
        key1 = keys.pop()
        if key1 not in lookup:
            err = '"{}" is not defined in the schema'
            err = err.format(key1)
            raise SchemaError(err)

        lookup = lookup[key1]

        while len(keys) > 0:
            key2 = key1
            key1 = keys.pop()

            if key1 == None:
                break

            if key1 not in lookup:
                err = '"{}" label does not exist within "{}"'
                err = err.format(key2, key1)
                raise SchemaError(err)

            lookup = lookup[key1]

        if isinstance(lookup, etree._Element):
            xml = lookup
        elif len(lookup) == 1:
            xml = lookup[list(lookup.keys())[0]]
        else:
            err = 'There are multiple "{}" entries; specify parent keys'
            err = err.format(key1)
            raise SchemaError(err)

        return cls(xml, language)

#===============================================================================
class Type(Entry):
    """
    Types serve as a desriptive elements for a field and describe how lxml Elements 
    should be generated. LOV and RefTable types have their own objects as
    they have slightly more complicated logic.
    """

    @classmethod
    def from_id(cls, id_, lookup_id = None, language = "english"):

        out = super().from_keys([id_], cls._type_by_id, language)
        
        if out.label == "LOV":
            return LOV.from_id(lookup_id, language)
        elif out.label == "Reference":
            return RefTable.from_id(lookup_id, language)
        else:
            return out

    @classmethod
    def from_label(cls, label, lookup_label = None, language = "english"):

        out = super().from_keys([label], cls._type_by_label, language)

        if out.label == "LOV":
            return LOV.from_label(lookup_label, language)
        elif out.label == "Reference":
            return RefTable.from_label(lookup_label, language)
        else:
            return out

#-------------------------------------------------------------------------------
class LOV(Entry):
    """
    Essentially a Type that also has a limited set of values it can take.
    """

    _cache = {}
    
    def __init__(self, xml, language = "english"):
        
        super().__init__(xml, language)

        # Extract values
        _by_label = {}
        _by_id = {}

        for child in xml.getchildren():
            entry = Entry(child, language)
            _by_label[entry.label] = entry
            _by_id[entry.id] = entry

        self._by_label = _by_label
        self._by_id = _by_id

        self.values = sorted(list(_by_label.keys()), key = locale.strxfrm)

        # Store to cache
        self._cache[self.id] = self
        self._cache[self.label] = self

    @classmethod
    def from_id(cls, id_, language = "english"):

        return super().from_keys([id_], cls._lov_by_id, language, cls._cache)

    @classmethod
    def from_label(cls, label, language = "english"):

        return super().from_keys([label], cls._lov_by_label, language, cls._cache)

    def value_by_label(self, label):

        if label not in self._by_label:
            err = '"{}" is not a valid option for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

#-------------------------------------------------------------------------------
class RefTable(Entry):
    """
    Essentially a Type that also has a limited set of values it can take (with each
    value being references to a metatable of references).
    """

    _cache = {}
    
    def __init__(self, xml, language = "english"):

        super().__init__(xml, language)

        # Extract values
        _by_label = {}
        _by_id = {}

        # First, just getting names
        reftable = xml.xpath("./refTable")[0]
        for child in reftable.getchildren():
            entry = Entry(child, language)
            _by_label[entry.label] = entry
            _by_id[entry.id] = entry

        table = xml.xpath("./table")[0]

        # First pass to pick off reference tables
        tables = []
        for child in table:
            entry = Entry(child, language)
            if entry.id != "-1":
                break

            label_type = re.sub(".*?\((.*?)\).*", r"\1", entry.label)
            label = re.sub("[ ]*\(.*?\)", "", entry.label)
            if label_type == "List Of Values":
                entry = LOV.from_label(label)
            elif label_type == "Reference Table":
                entry = RefTable.from_label(label)

            tables.append(entry)

        # Second pass to pick off values
        _values = {}
        for _, xml in etree.iterwalk(table, tag="value"):

            entry = Entry(xml, language)
            _values[entry.id] = entry

        # Third pass to pick off table elements
        for _, xml in etree.iterwalk(table, tag="field"):

            entry = Entry(xml, language)
            references = [_values[i.get("id")] for i in xml.getchildren()]
            _by_id[entry.id].references = references 
            _values[entry.id] = entry

        self.tables = tables
        self._by_label = _by_label
        self._by_id = _by_id

        # So at the end of the day, the refTable codes will correspond to the
        # general self.tables entries, while the labels will correspond to the
        # individual entry.references list stored in _by_label or _by_id

        self.values = sorted(list(_by_label.keys()), key = locale.strxfrm)

        # Store to cache
        self._cache[self.id] = self
        self._cache[self.label] = self

    @classmethod
    def from_id(cls, id_, language = "english"):

        return super().from_keys([id_], cls._ref_by_id, language, cls._cache)

    @classmethod
    def from_label(cls, label, language = "english"):

        return super().from_keys([label], cls._ref_by_label, language, cls._cache)

    def value_by_label(self, label):

        if label not in self._by_label:
            err = '"{}" is not a valid option for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

#===============================================================================
class Section(Entry):

    _cache = {}

    def __init__(self, xml, language = "english"):
        super().__init__(xml, language)

        # Then proceed to extract fields by label...


    @classmethod
    def from_id(cls, id_, language = "english"):

        return super().from_keys([id_], cls._section_by_id, language)
        
    @classmethod
    def from_label(cls, section_label, parent_label = None, language = "english"):

        return super().from_keys([section_label, parent_label], 
                cls._section_by_label, language)

    @classmethod
    def from_entries(cls, entries, warning = True, language = "english"):

        lookup = cls._section_id_by_entry

        # Parsing fields in alphabetical order for consistency
        entries.sort()

        # First, check if the full set of fields has been previously stored
        full_list = "".join(entries)

        if full_list in cls._cache:
            return cls._cache[full_list]
            
        numbers = [0]
        sets = [set()]

        for entry in entries:
            if entry not in lookup:
                continue
            
            # Generating new intersection with every existing set
            n_matches = 0
            new_set = lookup[entry]
            
            for i in range(len(sets)): 
                intersection = sets[i] & new_set 

                if len(intersection) > 0:
                    sets[i] = intersection
                    numbers[i] += 1
                    n_matches += 1

            # If there were no matches, start a new set
            if n_matches == 0:
                sets.append(new_set)
                numbers.append(1)

        # Picking off set with most fields
        if max(numbers) == 0:
            return None

        index = numbers.index(max(numbers))

        if len(sets[index]) > 1:
            return None

        section = cls.from_id(list(sets[index])[0], language)

        # Issue an error
        if warning and len(numbers) > 2:
            msg = '"{}" section matched with {} of {} entries'
            msg = msg.format(section.label, numbers[index], sum(numbers))
            _schema._log.warning(msg)

        # Store to cache
        cls._cache[full_list] = section

        return section

#===============================================================================
class Field(Entry):

    def __init__(self, xml, language = "english"):
    
        # Default parsing
        super().__init__(xml, language)

        # But a field also has a type
        self.type = Type.from_id(self.type_id, self.lookup_id)


_schema = Schema()

#f = Type.from_label("Date")
#print(f.id)
a = RefTable.from_label("Organization")
b = Type.from_label("Reference", "Organization")

s = Section.from_label("Courses Taught")
print(s.label)

class TEMP:

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

        if data_type is None:
            return

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

    #---------------------------------------------------------------------------
    def generate_template(self, section, parent = None):

        # First, attempt to get section id
        section_id = self.get_section_id(section, parent)

        # Define generic dict to list conversion
        def generate_list(entry_dict):
            entry_list = []
            entry_order = {}

            for key in entry_dict:
                xml = entry_dict[key]
                
                order = int(xml.get("orderIndex"))
                entry_order[key] = order

                comments = []
                comments.append(self.get_description(xml))

                field_type = self.get_field_type(xml)
                if field_type is not None:
                    comments.append("[" + field_type + "]")

                entry_list.append([key, comments])

            entry_list.sort(key = lambda x: entry_order[x[0]])

            return entry_list

        # Pull up dictionary of sections 
        fields = generate_list(self.get_section_fields(section_id))
        sections = generate_list(self.get_section_sections(section_id))
        
        # Recursively apply operation to all sections
        for i in range(len(sections)):
            sections[i].append(self.generate_template(sections[i][0], section))

        # Return combination
        return fields + sections


    #---------------------------------------------------------------------------
    def generate_yaml_template(self, section, parent = None):

        template = self.generate_template(section, parent)

        # As the yaml structure isn't particularly complicated, it's
        # easier to generate a string manually, thereby preserving order
        def add_line(item, string_list = [], indent = ""):

            comment_string = ""
            for line in item[1]:
                comment_string = comment_string + "\n" + indent + "#" + line

            string_list.append(comment_string)
            string_list.append(indent + item[0] + ":")

            if len(item) > 2:
                for item2 in item[2]:
                    add_line(item2, string_list, indent + " "*4)

        string_list = []
        for item in template:
            add_line(item, string_list)

        return "\n".join(string_list)

