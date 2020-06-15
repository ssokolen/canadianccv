from cached_property import cached_property
from flatten_dict import flatten
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


# ==============================================================================
# Function dealing with general schema creation

_schema = {}

# ----------------------------------------
def _add_schema(class_, keys, value, unique=True, overwrite=False):

    global _schema

    name = "-".join(keys)
    keys = [class_] + keys.copy()

    lookup = _schema

    while len(keys) > 1:
        key = keys.pop(0)

        if key not in lookup:
            lookup[key] = {}
        lookup = lookup[key]

    key = keys.pop()

    if key in lookup:
        if unique:
            err = '"{}" is not unique in "{}"'
            err = err.format(name, class_)
            raise SchemaError(err)
        elif overwrite:
            lookup[key] = value
    else:
        lookup[key] = value


# ----------------------------------------
def _get_schema(class_, keys):

    global _schema

    name = "-".join(keys)
    keys = keys.copy()

    if class_ not in _schema:
        err = 'No schema found for "{}" class'
        err = err.format(class_)
        raise SchemaError(err)

    lookup = _schema[class_]

    while len(keys) > 0:
        key = keys.pop(0)

        if key not in lookup:
            err = 'No schema found for "{}" class with identifier "{}"'
            err = err.format(class_, name)
            raise SchemaError(err)

        lookup = lookup[key]

    # If the result is still a dictionary, flatten it to see if there
    # is just one nested key
    if isinstance(lookup, dict):
        flat = flatten(lookup)
        keys = list(flat.keys())

        if len(keys) == 1:
            return flat[keys[0]]
        else:
            err = 'Identifier "{}" is ambiguous for class "{}". '
            err = err.format(name, class_)

            if class_ == "Section":
                err = err + " Try adding parent section label."

            raise SchemaError(err)

    return lookup

# ----------------------------------------
def _read_xml(path, default):

    if path is None:
        
        content = importlib.resources.read_binary('canadianccv', default)
    
    else:

        f = open(path, "rb")
        with f:
            content = f.read()
    
    return etree.XML(content)


# ----------------------------------------
def load_schema(language="english", cv = None, lov = None, ref = None):

    global _schema

    cv = _read_xml(cv, "cv.xml")
    lov = _read_xml(lov, "cv-lov.xml")
    ref = _read_xml(ref, "cv-ref-table.xml")

    # Section lookup tables
    for _, xml in etree.iterwalk(cv, tag="section"):

        section = Section(xml = xml, language = language)
        _add_schema("Section", [section.id], section)
        _add_schema("Section", [section.label, str(section.parent_label)], section)

        # Section by entry
        for child in xml.iterchildren("section", "field"):

            # Using a generic schema class for either section or field
            entry = XML(child, language)
            
            # Initializing lookup set if necessary 
            _add_schema("entries", [entry.label], set(), unique = False)

            # Adding to lookup set
            _get_schema("entries", [entry.label]).add(section.id)

            # Adding to field lists
            if child.tag == "field":
                pass

                # Field by id
                #self.add_lookup(["field", "id", entry.id], child)
    
    # LOV lookup tables
    for _, xml in etree.iterwalk(lov, tag="table"):

        entry = LOV(xml=xml, language=language)
        _add_schema("LOV", [entry.id], entry)
        _add_schema("LOV", [entry.label], entry)
    """
    # Ref table lookup tables 
    for _, xml in etree.iterwalk(ref, tag="table"):

        entry = XML(xml, language)

        # Generating arbitrary container to hold both table and refTable entries
        container = etree.Element("container", **xml.attrib)
        container.append(xml)

        self.add_lookup(["ref", "id", entry.id], container)
        self.add_lookup(["ref", "label", entry.label], container)

    # Adding second component of ref tables
    for _, xml in etree.iterwalk(ref, tag="refTable"):

        entry = XML(xml, language)
        container = self.lookup(["ref", "id", entry.id])
        container.append(xml)

    # Rules
    for _, xml in etree.iterwalk(cv, tag="rule"):

        entry = XML(xml, language)
        self.add_lookup(["rule", "id", entry.id], xml)
        self.add_lookup(["rule", "label", entry.label], xml)
    """
    # Data types
    for _, xml in etree.iterwalk(cv, tag="type"):

        entry = Type(xml=xml, language=language)
        _add_schema("Type", [entry.id], entry)
        _add_schema("Type", [entry.label], entry)

    """
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
    """

# ------------------------------------------------------------------------------
class Schema(type):

    def __call__(cls, *args, **kwargs):

        # If xml provided, then initialize from that
        if "xml" in kwargs:
            return super(Schema, cls).__call__(*args, **kwargs)

        # Otherwise, check schema
        global _schema

        return _get_schema(cls.__name__, list(args))

# ===============================================================================
class XML(object):
    """
    A generic wrapper around an lxml Element that exposes commonly used tags as
    well as a lookup classemethod.
    """

    # ----------------------------------------
    def __init__(self, xml, language="english"):
        self.xml = xml
        self.language = language

    # ----------------------------------------
    @classmethod
    def from_xml(cls, xml, language="english"):

        return cls(cls.lookup(cls, keys), language)

    # ----------------------------------------
    # Basics

    @property
    def id(self):
        return self.xml.get("id")

    @property
    def name(self):
        return self.xml.get(self.language + "Name")

    @property
    def description(self):
        return self.xml.get(self.language + "Description")

    @property
    def label(self):
        name = self.name
        description = self.description
        return name if name is not None else description

    @property
    def order(self):
        return self.xml.get("orderIndex")

    # ----------------------------------------
    # Data type related

    @property
    def type(self):
        return self.xml.get("dataType")

    @property
    def lookup(self):
        return self.xml.get("lookupId")

    # ----------------------------------------
    # Rule related

    @property
    def validator(self):
        return self.xml.get("validatorRule")

    @property
    def parameters(self):
        return self.xml.get("parameters")

    # ----------------------------------------
    # Parent/child related

    @property
    def parent_label(self):
        parent = self.xml.getparent()
        if parent is not None:
            parent = XML(parent, self.language)
            return parent.label

    # ----------------------------------------
    # Helper function for sorting

    def sort_elements(dct, values = True, attr = None):
        if values:
            out = list(dct.values())
        else:
            out = list(dct.keys())

        out.sort(key = lambda x: x.order)

        if attr is not None:
            out = [getattr(item, attr) for item in out]

        return out

# ===============================================================================
class Type(XML, metaclass = Schema):
    """
    A generic type that covers all types without reference values.
    """

    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @property
    def prompt(self):

        prompts = {
            "Year": "yyyy",
            "Year Month": "yyyy/mm",
            "Month Day": "mm/dd",
            "Date": "yyyy-mm-dd",
        }

        try:
            return prompts[self.label]
        except KeyError:
            return ""

    # ----------------------------------------
    def to_xml(self, value):

        elem = None

        if self.label == "Year":
            elem = etree.Element("value", format="yyyy", type=self.label)
            elem.text = str(value)

        elif self.label == "Year Month":
            elem = etree.Element("value", format="yyyy/MM", type=self.label)
            elem.text = str(value)

        elif self.label == "Month Day":
            elem = etree.Element("value", format="MM/dd", type=self.label)
            elem.text = str(value)

        elif self.label == "Date":
            elem = etree.Element("value", format="yyyy-MM-dd", type=self.label)
            elem.text = str(value)

        elif self.label == "Datetime":
            pass

        elif self.label == "String":
            elem = etree.Element("value", type=self.label)
            elem.text = str(value)

        elif self.label == "Integer":
            elem = etree.Element("value", type="Number")
            elem.text = str(value)

        elif self.label == "Bilingual":
            elem = etree.Element("value", type="Bilingual")
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


# -------------------------------------------------------------------------------
class LOV(XML, metaclass = Schema):
    """
    A reference for Type with an LOV value.
    """

    # ----------------------------------------
    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @cached_property
    def value_labels(self):

        values = {}

        for child in self.xml.getchildren():
            entry = XML(child, self.language)
            values[entry.label] = entry

        return values

    # ----------------------------------------
    @cached_property
    def value_ids(self):

        values = {}

        for child in self.xml.getchildren():
            values[entry.id] = entry

        return values

    # ----------------------------------------
    @property
    def values_list(self):
        return sorted(list(self.value_labels.keys()), key=locale.strxfrm)

    # ----------------------------------------
    def has_id(self, id_):

        return id_ in self._by_id

    # ----------------------------------------
    def has_label(self, label):

        return label in self._by_label

    # ----------------------------------------
    def by_id(self, id_):

        if not self.has_id(id_):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_id[id_]

    # ----------------------------------------
    def by_label(self, label):

        if not self.has_label(label):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

    # ----------------------------------------
    def to_xml(self, value):

        elem = etree.Element("lov", id=self.id)
        elem.text = self.by_label(value).label

        return elem


# -------------------------------------------------------------------------------
class RefTable(XML, metaclass = Schema):
    """
    Essentially a Type that also has a limited set of values it can take (with each
    value being references to a metatable of references).
    """

    _cache = {}

    # ----------------------------------------
    def __init__(self, xml, language="english"):

        super(Type, self).__init__(xml, language)

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

        self.values = sorted(list(_by_label.keys()), key=locale.strxfrm)
        self.prompt = ", ".join(self.values)

    # ----------------------------------------
    def has_id(self, id_):

        return id_ in self._by_id

    # ----------------------------------------
    def has_label(self, label):

        return label in self._by_label

    # ----------------------------------------
    def by_id(self, id_):

        if not self.has_id(id_):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_id[id_]

    # ----------------------------------------
    def by_label(self, label):

        if not self.has_label(label):
            err = '"{}" is not a valid value for "{}"'
            err = err.format(label, self.label)
            raise SchemaError(err)
        else:
            return self._by_label[label]

    # ----------------------------------------
    def to_xml(self, value):

        value = self.by_label(value)

        ids = self.tables + [self]
        values = value.references + [value]

        elem = etree.Element("refTable", refValueId=value.id)

        for i in range(len(ids)):
            link = etree.Element(
                "linkedWith",
                label="x",
                value=values[i].label,
                refOrLovId=ids[i].id,
            )
            elem.append(link)

        return elem


# ===============================================================================
class Rule(XML, metaclass = Schema):
    """
    Validation rule that can be used to assess Field entries.
    """

    _cache = {}

    # ----------------------------------------
    def __init__(self, xml, parameters, language="english"):

        super().__init__(xml, language)

        # Since only a small fraction of rules are used in practice,
        # only generating validations for these

        self.parameters = parameters

        rule_id = int(self.id)

        # Default validation
        def validate(self, value, entries=None):
            return ""

        prompt = '"{}" -- not currently checked'.format(self.label)

        # Specific rules
        if rule_id == 8:

            def validate(self, value, entries=None):
                if len(value) > int(parameters):
                    return "too long"

            prompt = "Must be fewer than {} characters long.".format(
                parameters
            )

        elif rule_id == 11:

            def validate(self, value, entries=None):
                if len(value) == 0:
                    return "null entries not allowed"

            prompt = "Must not be left blank."

        elif rule_id == 15:
            # Validate Unique Value -- unclear rule
            pass

        elif rule_id == 18:

            def validate(self, value, entries=None):
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

    # ----------------------------------------
    @classmethod
    def from_id(cls, id_, parameters, language="english"):

        xml = cls.lookup(cls, ["rule", "id", id_], cls._cache)
        return cls(xml, parameters, language)

    # ----------------------------------------
    @classmethod
    def from_label(cls, label, parameters, language="english"):

        xml = cls.lookup(cls, ["rule", "label", label], cls._cache)
        return cls(xml, parameters, language)


# ===============================================================================
class Section(XML, metaclass = Schema):

    # ----------------------------------------
    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @classmethod
    def from_entries(cls, entries, error = True):

        # Parsing fields in alphabetical order for consistency
        entries.sort()

        # First, check if the full set of fields has been previously stored
        name = "".join(entries)
        
        try:
            return _get_schema("Section", [name])
        except SchemaError:
            pass

        numbers = [0]
        sets = [set()]

        lookup = _schema["entries"] 

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
            
            if error:
                msg = 'Multiple sections matched with the same entries'
                raise SchemaError(msg)

            return None

        section = cls(list(sets[index])[0])

        # Issue an error
        if error and len(numbers) > 2:
            msg = '"{}" section matched with {} of {} entries'
            msg = msg.format(section.label, numbers[index], sum(numbers))
            raise SchemaError(msg)

        # Store to cache
        _add_schema("Section", [name], section)

        return section

    # ----------------------------------------
    @cached_property
    def parents(self):

        parents = {}

        for parent in self.xml.iterancestors(tag = "section"):
            section = Section(parent.get("id"))
            parents[section.label] = section

        return parents

    # ----------------------------------------
    @cached_property
    def sections(self):

        children = {}

        for child in self.xml.iterchildren(tag = "section"):
            section = Section(child.get("id"))
            children[section.label] = section

        return children

    # ----------------------------------------
    @cached_property
    def fields(self):

        children = {}

        for child in self.xml.iterchildren(tag = "field"):
            field = Field(child.get("id"))
            children[field.label] = field

        return children

    # ----------------------------------------
    @cached_property
    def rules(self):

        children = {}

        for child in self.xml.iterchildren(tag = "constraint"):
            section = Rule(child.get("id"))
            children[parents.label] = section

        return children


    # ----------------------------------------
    def field(self, label):
        if label in self.fields:
            return self.fields[label]
        else:
            err = '"{}" field does not exist in "{}" section.'
            err = err.format(label, self.label)
            raise SchemaError(err)


    # ----------------------------------------
    def to_xml(self):

        section = etree.Element("section", id = self.id, label = self.label)

        return section

    # ----------------------------------------
    def yaml_template(
        self,
        sep="\n",
        width=80,
        max_lines=2,
        indent_char="    ",
        indent_level=0,
        add_description=True,
        add_type=True,
        add_constraint=True,
        join=True,
    ):

        lines = []

        def format_line(line, comment=False):

            indent = indent_char * indent_level
            if comment:
                indent = indent + "#"

            wrapper = TextWrapper(
                initial_indent=indent,
                subsequent_indent=indent,
                width=width,
                max_lines=max_lines,
                placeholder=" ...",
                drop_whitespace=False,
            )
            lines = wrapper.wrap(line)

            return lines

        for field in XML.sort(self.fields):

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
                    sep,
                    width,
                    max_lines,
                    indent_char,
                    indent_level + 1,
                    join=False,
                )
            )

        if join:
            return "\n".join(lines)
        else:
            return lines


# ===============================================================================
class Field(XML, metaclass = Schema):

    _cache = {}

    # ----------------------------------------
    def __init__(self, xml, language="english"):

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

    # ----------------------------------------
    @classmethod
    def from_id(cls, id_, language="english"):
        return cls.from_lookup(["field", "id", id_], language, cls._cache)

    # ----------------------------------------
    @classmethod
    def from_label(cls, label, section):
        return section.field(label)

    # ----------------------------------------
    def validate(self, value, entries):

        msgs = []

        for rule in self.rules:
            msg = rule.validate(rule, value, entries)
            if msg is not None:
                msgs.append(msg)

        if len(msgs) > 0:
            return "; ".join(msgs)

    # ----------------------------------------
    def to_xml(self, value):

        field = etree.Element("field", id=self.id, label=self.label)

        # Adding on the actual value based on type
        field.append(self.type.to_xml(value))

        return field


# Generating default schema
load_schema()
