import importlib.resources
import locale
import logging
from lxml import etree
import operator
import re
from textwrap import TextWrapper

locale.setlocale(locale.LC_ALL, "")

class SchemaError(Exception):
    """Raised when there is a generic issue parsing CCV data"""
    pass

#===============================================================================
class Schema(object):

    _lookup = {}

    #----------------------------------------
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

        # Section lookup tables
        for _, xml in etree.iterwalk(cv, tag="section"):

            section = Entry(xml, language)

            lookup = ["section", "id", section.id]
            self.add_lookup(lookup, xml)
            
            lookup = ["section", "label", section.label, section.parent.label]
            self.add_lookup(lookup, xml)

            # Section by entry
            for child in xml.getchildren():

                if child.tag not in ["section", "field"]:
                    continue

                # Using a generic schema class for either section or field
                entry = Entry(child, language)
                
                lookup = ["section", "entry_label", entry.label]

                # Initializing lookup set if necessary 
                self.add_lookup(lookup, set(), unique = False)

                # Adding to lookup set
                self.lookup(lookup).add(section.id)

                # Adding to field lists
                if child.tag == "field":

                    # Field by id
                    self.add_lookup(["field", "id", entry.id], child)

        # LOV lookup tables 
        for _, xml in etree.iterwalk(lov, tag="table"):

            entry = Entry(xml, language)
            self.add_lookup(["lov", "id", entry.id], xml)
            self.add_lookup(["lov", "label", entry.label], xml)

        # Ref table lookup tables 
        for _, xml in etree.iterwalk(ref, tag="table"):

            entry = Entry(xml, language)

            # Generating arbitrary container to hold both table and refTable entries
            container = etree.Element("container", **xml.attrib)
            container.append(xml)

            self.add_lookup(["ref", "id", entry.id], container)
            self.add_lookup(["ref", "label", entry.label], container)

        # Adding second component of ref tables
        for _, xml in etree.iterwalk(ref, tag="refTable"):

            entry = Entry(xml, language)
            container = self.lookup(["ref", "id", entry.id])
            container.append(xml)

        # Data types
        for _, xml in etree.iterwalk(cv, tag="type"):

            entry = Entry(xml, language)
            self.add_lookup(["type", "id", entry.id], xml)
            self.add_lookup(["type", "label", entry.label], xml)

        # Rules
        for _, xml in etree.iterwalk(cv, tag="rule"):

            entry = Entry(xml, language)
            self.add_lookup(["rule", "id", entry.id], xml)
            self.add_lookup(["rule", "label", entry.label], xml)

    #----------------------------------------
    def add_lookup(self, keys, value, unique = True, overwrite = False):

        keys = keys.copy()

        full_name = "-".join(keys[:-1])

        lookup = self._lookup

        while len(keys) > 1:
            key = keys.pop(0)

            if key not in lookup:
                lookup[key] = {}
            lookup = lookup[key]

        key = keys.pop()
        
        if key in lookup:
            if unique:
                err = '"{}" is not unique in "{}"'
                err = err.format(key, full_name)
                raise SchemaError(err)
            elif overwrite:
                lookup[key] = value
        else:
            lookup[key] = value

    #----------------------------------------
    def lookup(self, keys, cache = None):

        keys = keys.copy()

        lookup = self._lookup
        lookup_name = "lookup"

        while len(keys) > 0:
            key = keys.pop(0)

            if key not in lookup:
                err = '"{}" does not exist within "{}"'
                err = err.format(key, lookup_name)
                raise SchemaError(err)
                
            lookup = lookup[key]
            lookup_name += "-" + key

        return lookup

#===============================================================================
class Entry(Schema):
    """
    A generic wrapper around an lxml Element that exposes commonly used tags as
    well as a lookup classemethod.
    """

    #----------------------------------------
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

        self.validator = xml.get("validatorRule")
        self.parameters = xml.get("parameters")

        self.parent = None 
        if xml.getparent() is not None and xml.tag != "rule":
            self.parent = Entry(xml.getparent(), language)


    #----------------------------------------
    @classmethod
    def from_lookup(cls, keys, language = "english", cache = None):

        full_name = "-".join(keys)

        if cache is not None and full_name in cache:
            return cache[full_name]

        out = cls(cls.lookup(cls, keys), language)
        
        if cache is not None:
            cache[full_name] = out

        return out

#===============================================================================
class Type(Entry):
    """
    Types serve as a desriptive elements for a field and describe how lxml Elements 
    should be generated. LOV and RefTable types have their own objects as
    they have slightly more complicated logic.
    """

    def __init__(self, xml, language = "english"):

        super().__init__(xml, language)

        # Generating entry prompts for certain field types
        self.prompt = ""
        
        if self.label == "Year":
            self.prompt = "yyyy"
        elif self.label == "Year Month":
            self.prompt = "yyyy/mm"
        elif self.label == "Month Day":
            self.prompt = "mm/dd"
        elif self.label == "Date":
            self.prompt = "yyyy-mm-dd"

    #----------------------------------------
    @classmethod
    def from_id(cls, type_id, lookup_id = None, language = "english"):

        out = cls.from_lookup(["type", "id", type_id], language)

        if out.label == "LOV" and lookup_id is not None:
            return LOV.from_id(lookup_id, language)
        elif out.label == "Reference" and lookup_id is not None:
            return RefTable.from_id(lookup_id, language)
        else:
            return out

    #----------------------------------------
    @classmethod
    def from_label(cls, type_label, lookup_label = None, language = "english"):

        out = cls.from_lookup(["type", "label", type_label], language)

        if out.label == "LOV":
            return LOV.from_label(lookup_label, language)
        elif out.label == "Reference":
            return RefTable.from_label(lookup_label, language)
        else:
            return out

    #---------------------------------------------------------------------------
    def to_xml(self, value):

        if self.label == "Year":
            elem = etree.Element("value", format = "yyyy", type = self.label)
            elem.text = str(value)

        elif self.label == "Year Month":
            elem = etree.Element("value", format = "yyyy/MM", type = self.label)
            elem.text = str(value)

        elif self.label == "Month Day":
            elem = etree.Element("value", format = "MM/dd", type = self.label)
            elem.text = str(value)

        elif self.label == "Date":
            elem = etree.Element("value", format = "yyyy-MM-dd", type = self.label)
            elem.text = str(value)

        elif self.label == "Datetime":
            pass

        elif self.label == "String":
            elem = etree.Element("value", type = self.label)
            elem.text = str(value)

        elif self.label == "Integer":
            elem = etree.Element("value", type = "Number")
            elem.text = str(value)

        elif self.label == "Bilingual":
            elem = etree.Element("value", type = "Bilingual")
            elem.append(etree.Element("english"))
            elem.append(etree.Element("french"))

            if self.language == "english":
                elem[0].text = str(value)
            else:
                elem[1].text = str(value)
        
        elif self.label == "PubMed":
            pass
        
        elif self.label == "Elapsed-Time":
            pass

        if elem is None:
            # Defining generic error message for missing implementations
            err = '"{}" data type is not currently supported. '
            err = err.format(self.label)
            raise SchemaError(err)

        return elem 

#-------------------------------------------------------------------------------
class LOV(Entry):
    """
    Essentially a Type that also has a limited set of values it can take.
    """

    _cache = {}
    
    #----------------------------------------
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
        self.prompt = ", ".join(self.values)

    #----------------------------------------
    @classmethod
    def from_id(cls, id_, language = "english"):

        return cls.from_lookup(["lov", "id", id_], language, cls._cache)

    #----------------------------------------
    @classmethod
    def from_label(cls, label, language = "english"):

        return cls.from_lookup(["lov", "label", label], language, cls._cache)

    #----------------------------------------
    def has_id(self, id_):

        return id_ in self._by_id 

    #----------------------------------------
    def has_label(self, label):

        return label in self._by_label

    #----------------------------------------
    def by_id(self, id_):

        if not self.has_id(id_):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_id[id_]

    #----------------------------------------
    def by_label(self, label):

        if not self.has_label(label):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

    #----------------------------------------
    def to_xml(self, value):

        elem = etree.Element("lov", id = self.id)
        elem.text = self.by_label(value).label

        return elem 

#-------------------------------------------------------------------------------
class RefTable(Entry):
    """
    Essentially a Type that also has a limited set of values it can take (with each
    value being references to a metatable of references).
    """

    _cache = {}
    
    #----------------------------------------
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
        self.prompt = ", ".join(self.values)

    #----------------------------------------
    @classmethod
    def from_id(cls, id_, language = "english"):

        return cls.from_lookup(["ref", "id", id_], language, cls._cache)

    #----------------------------------------
    @classmethod
    def from_label(cls, label, language = "english"):

        return cls.from_lookup(["ref", "label", label], language, cls._cache)

    #----------------------------------------
    def has_id(self, id_):

        return id_ in self._by_id 

    #----------------------------------------
    def has_label(self, label):

        return label in self._by_label 

    #----------------------------------------
    def by_id(self, id_):

        if not self.has_id(id_):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_id[id_]

    #----------------------------------------
    def by_label(self, label):

        if not self.has_label(label):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

    #----------------------------------------
    def to_xml(self, value):

        value = self.by_label(value)

        ids = self.tables + [self]
        values = value.references + [value]

        elem = etree.Element("refTable", refValueId = value.id)

        for i in range(len(ids)):
            link = etree.Element("linkedWith", 
                label = "x", value = values[i].label, refOrLovId = ids[i].id
            )
            elem.append(link)

        return elem 

#===============================================================================
class Rule(Entry):
    """
    Validation rule that can be used to assess Field entries.
    """

    _cache = {}

    #----------------------------------------
    def __init__(self, xml, parameters, language = "english"):

        super().__init__(xml, language)

        # Since only a small fraction of rules are used in practice,
        # only generating validations for these

        self.parameters = parameters

        rule_id = int(self.id)

        # Default validation
        def validate(self, value, entries = None):
            return ""

        prompt = '"{}" -- not currently checked'.format(self.label)

        # Specific rules
        if rule_id == 8:
            def validate(self, value, entries = None):
                if len(value) > int(parameters):
                    return "too long"

            prompt = "Must be fewer than {} characters long.".format(
                parameters
            )

        elif rule_id == 11:
            def validate(self, value, entries = None):
                if len(value) == 0:
                    return "null entries not allowed"

            prompt = "Must not be left blank."

        elif rule_id == 15:
            # Validate Unique Value -- unclear rule
            pass

        elif rule_id == 18:
            def validate(self, value, entries = None):
                if len(value) > int(parameters):
                    return "too many entries"

            prompt = "Must have {} entries or fewer.".format(parameters)

        elif rule_id == 19:
            # Validate Primary Record Chosen -- unclear rule
            pass

        elif rule_id == 20:
            
            # Requires parsing parameters
            lines = parameters.split(";")
            
            field_id = re.sub(":.*", "", lines[1])
            field = Field.from_id(field_id, language)

            lov_id = re.sub(":.*", "", lines[2])
            lov = LOV.from_id(lov_id, language)

            other_id = lines[-1]
            other = lov.by_id(other_id)

            op = re.sub(":.*", "", lines[-2])

            if int(op) == 359:
                op = operator.eq
                prompt = "Required if {} is {}"
                prompt = prompt.format(field.label, other.label)
                
                msg = "entry required if {} is {}"
                msg = msg.format(field.label, other.label)
            else:
                op = operator.ne
                prompt = "Required if {} is not {}"
                prompt = prompt.format(field.label, other.label)
                
                msg = "entry required if {} is not {}"
                msg = msg.format(field.label, other.label)

            def validate(self, value, entries):
                other_value = entries[field.label]
                if len(value) == 0 and op(other_value, other.label):
                    return msg

        elif rule_id == 24:

            # Requires parsing parameters
            field_id = re.sub(":.*", "", parameters)
            field = Field.from_id(field_id, language)

            def validate(self, value, entries):
                other_value = entries[field.label]
                if len(other_value) > 0 and len(value) > 0:
                    msg = "Must be left blank if using {}"
                    msg = msg.format(field.label)
                    return msg

            prompt = "Mutually exclusive with {}.".format(field.label)

        elif rule_id == 25:
            # PubMed, leaving for now
            pass

        elif rule_id == 28:
            # Birthday, too limited to implement now
            pass

        self.validate = validate
        self.prompt = prompt

    #----------------------------------------
    @classmethod
    def from_id(cls, id_, parameters, language = "english"):

        xml = cls.lookup(cls, ["rule", "id", id_], cls._cache)
        return cls(xml, parameters, language)

    #----------------------------------------
    @classmethod
    def from_label(cls, label, parameters, language = "english"):

        xml = cls.lookup(cls, ["rule", "label", label], cls._cache)
        return cls(xml, parameters, language)

#===============================================================================
class Section(Entry):

    _cache = {}

    #----------------------------------------
    def __init__(self, xml, language = "english"):
        super().__init__(xml, language)

        # Get all parents -- using xml to avoid recursion error
        parent_ids = []

        parent = xml.getparent()
        parent_id = parent.get("id")

        while parent_id is not None:
            parent_ids.append(parent_id)
            parent = parent.getparent()
            parent_id = parent.get("id")

        self.parent_ids = parent_ids

        self.fields = {}
        self.sections = {}
        
        # Parsing fields
        for child in xml.getchildren():

            # Adding to field lists
            if child.tag == "field":
                entry = Field(child, language)
                lookup = self.fields
            elif child.tag == "section":
                entry = Section(child, language)
                lookup = self.sections
            else:
                continue

            if entry.label in lookup:
                err = '"{}" is not unique within "{}"'
                err = err.format(entry.label, self.label)
                raise SchemaError(err)

            lookup[entry.label] = entry

        # Gather all rules
        self.rules = []

        for child in xml.xpath("constraint"):
            entry = Entry(child, language)
            self.rules.append(Rule.from_id(entry.validator, language))

    #----------------------------------------
    @classmethod
    def from_id(cls, id_, language = "english"):

        return cls.from_lookup(["section", "id", id_], language, cls._cache)
        
    #----------------------------------------
    @classmethod
    def from_label(cls, section_label, parent_label = None, language = "english"):

        # Check cache
        full_name = section_label + str(parent_label)
        if full_name in cls._cache:
            return cls._cache[full_name]

        # Check just section label
        section = cls.lookup(cls, ["section", "label", section_label])

        # If there is only one key, generate class
        keys = list(section.keys())
        if len(keys) == 1:
            out = cls(section[keys[0]], language)
        else:
            if parent_label is not None:
                if parent_label not in keys:
                    err = '"{}" section not in {}'
                    err = err.format(section_label, parent_label)
                    raise SchemaError(err)
                else:
                    out = cls(section[parent_label])
            else:
                err = '"{}" section is ambiguous, specify parent label'
                err = err.format(section_label)
                raise SchemaError(err)

        cls._cache[full_name] = out

        return out

    #----------------------------------------
    @classmethod
    def from_entries(cls, entries, warning = True, language = "english"):

        # Parsing fields in alphabetical order for consistency
        entries.sort()

        # First, check if the full set of fields has been previously stored
        full_name = "".join(entries)

        if full_name in cls._cache:
            return cls._cache[full_name]
            
        numbers = [0]
        sets = [set()]

        lookup = cls.lookup(cls, ["section", "entry_label"])

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
        cls._cache[full_name] = section

        return section

    #----------------------------------------
    def field(self, label):
        if label in self.fields:
            return self.fields[label]
        else:
            err = '"{}" field does not exist in "{}" section.'
            err = err.format(label, self.label)
            raise SchemaError(err)

    #----------------------------------------
    def field_list(self):
        out = list(self.fields.values())
        out.sort(key = lambda x: x.order)
        return out

    #----------------------------------------
    def section_list(self):
        out = list(self.sections.values())
        out.sort(key = lambda x: x.order)
        return out

    #----------------------------------------
    def to_xml(self):
        
        section = etree.Element("section", id = self.id, label = self.label)

        return section

    #----------------------------------------
    def yaml_template(self, sep = '\n', width = 80, max_lines = 2, 
                      indent_char = '    ', indent_level = 0,
                      add_description = True, add_type = True, 
                      add_constraint = True,
                      join = True):

        lines = []

        def format_line(line, comment = False):

            indent = indent_char*indent_level
            if comment:
                indent = indent + "#"

            wrapper = TextWrapper(
                initial_indent = indent, subsequent_indent = indent,
                width = width, max_lines = max_lines, placeholder = " ...", 
                drop_whitespace = False
            )
            lines = wrapper.wrap(line)

            return(lines)

        for field in self.field_list():

            if add_description:
                line = "[Description] " + field.description
                lines.extend(format_line(line, True))
            
            if add_type:
                line = "[Type] " + field.type.label
                if field.type.prompt != "":
                    line = line + " -- " + field.type.prompt

                lines.extend(format_line(line, True))

            if add_constraint:
                for rule in field.rules:
                    line = "[Constraint] " + rule.prompt
                    lines.extend(format_line(line, True))

            line = field.label + ":"
            lines.extend(format_line(line))
            lines[-1] = lines[-1] + sep

        for section in self.section_list():

            line = section.label + ":"
            lines.extend(format_line(line))
            lines[-1] = lines[-1] + sep

            lines.extend(
                section.yaml_template(
                    sep, width, max_lines, indent_char, indent_level + 1, 
                    join = False
                )
            )

        if join:
            return "\n".join(lines)
        else:
            return lines

#===============================================================================
class Field(Entry):

    _cache = {}

    #----------------------------------------
    def __init__(self, xml, language = "english"):
    
        # Default parsing
        super().__init__(xml, language)

        self.type = Type.from_id(self.type_id, self.lookup_id)

        # Double checking in case lookup was none while it should have a value
        if self.type.label == "LOV":
            lov = LOV.from_label(self.label)
            self.type = Type.from_id(self.type_id, lov.id)
        elif self.type.label == "Reference":
            ref = RefTable.from_label(self.label)
            self.type = Type.from_id(self.type_id, ref.id)

        # And adding rules
        self.rules = []

        for child in xml.xpath("constraint"):
            entry = Entry(child, language)
            self.rules.append(
                Rule.from_id(entry.validator, entry.parameters, language)
            )

    #----------------------------------------
    @classmethod
    def from_id(cls, id_, language = "english"):
        return cls.from_lookup(["field", "id", id_], language, cls._cache)

    #----------------------------------------
    @classmethod
    def from_label(cls, label, section):
        return section.field(label)

    #----------------------------------------
    def validate(self, value, entries):
        
        msgs = []

        for rule in self.rules:
            msg = rule.validate(rule, value, entries)
            if msg is not None:
                msgs.append(msg)

        if len(msgs) > 0:
            return "; ".join(msgs)

    #----------------------------------------
    def to_xml(self, value):
        
        field = etree.Element("field", id = self.id, label = self.label)

        # Adding on the actual value based on type
        field.append(self.type.to_xml(value))

        return field

_schema = Schema()
