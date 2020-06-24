from cached_property import cached_property
import copy
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
# Helper function for line wrapping in template

_wrapper = TextWrapper(
    initial_indent = "    ",
    subsequent_indent = "    ",
    width = 80,
    max_lines = 2,
    placeholder = " ...",
    drop_whitespace = False,
    replace_whitespace = True,
)

def load_wrapper(wrapper = None):

    global _wrapper
    _wrapper = wrapper


# ==============================================================================
# Function dealing with general schema creation

_schema = {}

# ----------------------------------------
def _add_schema(class_, keys, value, unique = True, overwrite = False):

    # If overwrite is true, makes no sense to error out on unique check
    if overwrite:
        unique = False

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
    for _, xml in etree.iterwalk(cv, tag = "section"):

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

                # Field by id
                field = Field(xml = child, language = language)
                _add_schema("Field", [entry.id],  field)
    
    # LOV lookup tables
    for _, xml in etree.iterwalk(lov, tag = "table"):

        entry = LOV(xml = xml, language = language)
        _add_schema("LOV", [entry.id], entry)
        _add_schema("LOV", [entry.label], entry)
    
    # Ref table lookup tables 
    for _, xml in etree.iterwalk(ref, tag = "table"):

        entry = XML(xml, language)

        # Generating arbitrary container to hold both table and refTable entries
        container = etree.Element("container", **xml.attrib)
        container.append(xml)

        _add_schema("Reference", [entry.id], container)
        _add_schema("Reference", [entry.label], container)

    # Adding second component of ref tables
    for _, xml in etree.iterwalk(ref, tag = "refTable"):

        entry = XML(xml, language)
        container = _get_schema("Reference", [entry.id])
        container.append(xml)

        # And replace the placeholder container with a Reference element
        table = Reference(xml = container, language = language)
        _add_schema("Reference", [table.id], table, overwrite = True)
        _add_schema("Reference", [table.label], table, overwrite = True)

    # Data types
    for _, xml in etree.iterwalk(cv, tag = "type"):

        entry = Type(xml = xml, language = language)
        _add_schema("Type", [entry.id], entry)
        _add_schema("Type", [entry.label], entry)

    # Rules
    for _, xml in etree.iterwalk(cv, tag = "rule"):

        entry = Rule(xml = xml, language = language)
        _add_schema("Rule", [entry.id], entry)
        _add_schema("Rule", [entry.label], entry)


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
    def type_id(self):
        return self.xml.get("dataType")

    @property
    def lookup_id(self):
        return self.xml.get("lookupId")

    # ----------------------------------------
    # Rule related

    @property
    def validator(self):
        return self.xml.get("validatorRule")

    # ----------------------------------------
    # Parent/child related

    @property
    def parent_label(self):
        parent = self.xml.getparent()
        if parent is not None:
            parent = XML(parent, self.language)
            return parent.label

    # ----------------------------------------
    # Helper functions for sorting

    def to_list(lst, value = None, sort = "alpha"):
        lst = lst.copy()

        if sort == "alpha":
            lst.sort(key = lambda x: locale.strxfrm(x.label))
        elif sort == None:
            pass
        else:
            lst.sort(key = lambda x: getattr(x, sort))

        if value is not None:
            lst = [getattr(item, value) for item in lst]

        return lst

    def to_dict(lst, key, value = None):

        if value is None:
            get = lambda x: x
        else:
            get = lambda x: getattr(x, value)

        out = {getattr(item, key):get(item) for item in lst}

        return out

# ===============================================================================
class Type(XML, metaclass = Schema):
    """
    A generic data type.
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

        if self.label in prompts:
            return prompts[self.label]
        else:
            return ""

    # ----------------------------------------
    def to_xml(self, value):

        # Coding out the basic types
        label = self.label

        basic_types = {
            "Year": etree.Element("value", format="yyyy", type=label),
            "Year Month": etree.Element("value", format="yyyy/MM", type=label),
            "Month Day": etree.Element("value", format="MM/dd", type=label),
            "Date":etree.Element("value", format="yyyy-MM-dd", type=label),
            "String":etree.Element("value", type=self.label),
            "Integer":etree.Element("value", type="Number"),
        }

        # Removing all single newlines
        if isinstance(value, str):
            value = re.sub("[ \t]*\n{1}[ \t]*", " ", value)

        if self.label in basic_types:

            elem = basic_types[self.label]
            elem.text = str(value)
        
        elif self.label == "Bilingual":
            
            if isinstance(value, str):
                value_dct = {"english":"", "french":""}
                value_dct[self.language] = value
            elif isinstance(value, dict):
                value_dct = value
            else:
                err = "Bilingual data type value must be a string or dictionary."
                raise SchemaError(err)

            elem = etree.Element("value", type="Bilingual")

            elem.append(etree.Element("english"))
            elem[0].text = str(value_dct["english"])
            elem[0].text = re.sub("[ \t]*\n{1}[ \t]*", " ", elem[0].text)

            elem.append(etree.Element("french"))
            elem[1].text = str(value_dct["french"])
            elem[1].text = re.sub("[ \t]*\n{1}[ \t]*", " ", elem[1].text)

        elif self.label in ["Datetime", "Pubmed", "Elapsed-Time"]:

            err = '"{}" type is not currently supported'.format(self.label)
            raise SchemaError(err)

        elif self.label in ["LOV", "Reference"]:

            err = '"{}" should not have entered here, something went wrong'
            err = err.format(self.label)
            raise SchemaError(err)

        else: 

            err = '"{}" is not a known data type, something went wrong'
            err = err.format(self.label)
            raise SchemaError(err)

        return elem

# ===============================================================================
class ReferenceType(XML, metaclass = Schema):
    """
    A generic class for LOV and Reference data types, which share a few
    common principles in that both are associated with a list of possible
    values depending on the instance of the type.
    """

    # ----------------------------------------
    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @property
    def prompt(self):

        out = XML.to_list(self.values_list, "label")
        return "One of: " + ", ".join(out)

    # ----------------------------------------
    @cached_property
    def values(self):
        
        return XML.to_dict(self.values_list, "label")

    # ----------------------------------------
    def get_value(self, value):

        dct = self.values

        if value not in dct:
            err = '"{}" is not a valid value for "{}"'
            err = err.format(value, self.label)
            raise SchemaError(err)
        else:
            return dct[value]

# -------------------------------------------------------------------------------
class LOV(ReferenceType, metaclass = Schema):
    """
    Essentially a Type that also has a limited set of values it can take.
    """

    # ----------------------------------------
    @cached_property
    def values_list(self):

        values = []

        for child in self.xml.getchildren():
            entry = XML(child, self.language)
            values.append(entry)

        return values

    # ----------------------------------------
    def to_xml(self, value):

        value = self.get_value(value)

        elem = etree.Element("lov", id = self.id)
        elem.text = value.label

        return elem

# -------------------------------------------------------------------------------
class Reference(ReferenceType, metaclass = Schema):
    """
    Essentially a Type that also has a limited set of values it can take (with each
    value being linked to a metatable of references).
    """

    # ----------------------------------------
    @cached_property
    def values_list(self):

        values = {}

        # Initializing the values as simple XML elements around names
        for child in self.xml.xpath("refTable/value"):
            entry = XML(child, self.language)
            values[entry.id] = entry

        # However, this simple set of values has a reference table attached
        # to it in the final XML table, which requires a set of reference
        # ids and a set of reference names

        # The RefOrLovId slots in the final table
        # correspond to the ids referenced in the first couple lines of values
        table_ids = []
        
        for child in self.xml.xpath("table/value"):
            
            entry = XML(child, self.language)
            
            if entry.id != "-1":
                break

            label_type = re.sub(".*?\((.*?)\).*", r"\1", entry.label)
            label = re.sub("[ ]*\(.*?\)", "", entry.label)
            
            if label_type == "List Of Values":
                entry = LOV(label)
            elif label_type == "Reference Table":
                entry = Reference(label)

            # But all we want is the id
            table_ids.append(entry.id)

        # The final id is the id of this active Reference
        table_ids.append(self.id)

        # And the values of the table are split up into two parts,
        # the values themselves and a lookup table, so start by reading
        # off the lookup table

        lookup = {}
        
        for child in self.xml.xpath("table/value"):

            entry = XML(child, self.language)
            lookup[entry.id] = entry.label

        values_list = []

        # Then go through the tables and convery ids to labels
        for i, child in enumerate(self.xml.xpath("table/field")):

            table_values = [lookup[i.get("id")] for i in child.getchildren()]

            # And finally tack on this list of values (and previous ids)
            # to the original XML entry
            entry = XML(child, self.language)
            
            entry = values[entry.id]
            entry.ids = table_ids
            entry.values = table_values

            # And store this element in a final list
            values_list.append(entry)

        return values_list

    # ----------------------------------------
    def to_xml(self, value):

        value = self.get_value(value)

        ids = value.ids 
        values = value.values
        values.append(value.label)

        elem = etree.Element("refTable", refValueId = value.id)

        for i in range(len(ids)):
            link = etree.Element(
                "linkedWith",
                label="x",
                value=values[i],
                refOrLovId=ids[i],
            )
            elem.append(link)

        return elem

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

        # If we are only looking up by 1 field, add some qualifiers
        if len(entries) == 1:
            name = name + "--"
        
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
    def parent_list(self):

        parents = []

        for parent in self.xml.iterancestors(tag = "section"):
            section = Section(parent.get("id"))
            parents.append(section)

        return parents

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

        rules = []

        for child in self.xml.iterchildren(tag = "constraint"):
            rule = Rule.from_id(child.get("validatorRule"))
            rule._parameters = child.get("parameters")
            rules.append(rule)

        return rules

    # ----------------------------------------
    @cached_property
    def sorting(self):

        sorting = []

        i = 1
        while True:
            field = self.xml.get("sortOnField" + str(i))
            direction = self.xml.get("sortOnFieldDirection" + str(i))
            i += 1
            if field is not None:
                field = Field(field)
                direction.lower()
                sorting.append((field.label, direction))
            else:
                break

        return sorting

    # ----------------------------------------
    @cached_property
    def is_dependent(self):
        """True if any parent section has fields"""

        for key in self.parents:
            if len(self.parents[key].fields) > 0:
                return True

        return False

    # ----------------------------------------
    @cached_property
    def is_container(self):
        """True if neither this section nor parent sections have fields"""

        if len(self.fields) > 0:
            return False

        for key in self.parents:
            if len(self.parents[key].fields) > 0:
                return False

        return True

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
    def to_yaml(self, wrapper = _wrapper):

        section = wrapper.wrap(self.label + ": ")

        return section

    # ----------------------------------------
    def yaml_template(self, sep = "\n", indent_level = 0, add_description = True,
                      add_type = True, add_constraint = True, join = True):

        global _wrapper
        wrapper = copy.deepcopy(_wrapper)

        lines = []

        initial_indent = _wrapper.initial_indent
        subsequent_indent = _wrapper.subsequent_indent

        wrapper.initial_indent = initial_indent * indent_level
        wrapper.subsequent_indent = subsequent_indent * indent_level

        for field in XML.to_list(list(self.fields.values()), sort = "order"):

            if add_description:
                line = "# [Description] " + field.description
                lines.extend(wrapper.wrap(line))

            if add_type:
                line = "# [Type] " + field.type.label
                
                if field.type.prompt != "":
                    line = line + " -- " + field.type.prompt

                if field.reference is not None:
                    line = line + " -- " + field.reference.prompt

                lines.extend(wrapper.wrap(line))

            if add_constraint:
                for rule in field.rules:
                    line = "# [Constraint] " + rule.prompt
                    lines.extend(wrapper.wrap(line))

            line = field.label + ":"
            lines.extend(wrapper.wrap(line))
            lines[-1] = lines[-1] + sep

        for section in XML.to_list(list(self.sections.values()), sort = "order"):

            line = section.label + ":"
            lines.extend(wrapper.wrap(line))
            lines[-1] = lines[-1] + sep

            lines.extend(
                section.yaml_template(
                    sep, indent_level + 1, add_description,
                    add_type, add_constraint, join = False
                )
            )

        if join:
            return "\n".join(lines)
        else:
            return lines

# ===============================================================================
class Field(XML, metaclass = Schema):

    # ----------------------------------------
    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @classmethod
    def from_section(cls, label, *args):
        section = Section(*args)
        return section.field(label)

    # ----------------------------------------
    @property
    def type(self):
        return Type(self.type_id)

    # ----------------------------------------
    @property
    def reference(self):

        lookup = self.lookup_id if self.lookup_id is not None else self.label
        
        if self.type.label == "LOV":
            return LOV(lookup)
        elif self.type.label == "Reference":
            return Reference(lookup)

    # ----------------------------------------
    @cached_property
    def rules(self):

        rules = []

        for child in self.xml.iterchildren(tag = "constraint"):
            rule = Rule.from_id(child.get("validatorRule"))
            rule._parameters = child.get("parameters")
            rules.append(rule)

        return rules

    # ----------------------------------------
    def validate(self, value, entries):

        msgs = []

        for rule in self.rules:
            msg = rule.validate(value, entries)
            if msg is not None:
                msgs.append(msg)

        if len(msgs) > 0:
            return "; ".join(msgs)

    # ----------------------------------------
    def to_xml(self, value):

        field = etree.Element("field", id = self.id, label = self.label)

        # Adding on the actual value based on type
        if self.reference is not None:
            field.append(self.reference.to_xml(value))
        else:
            field.append(self.type.to_xml(value))

        return field

    # ----------------------------------------
    def to_yaml(self, value, wrapper = _wrapper):

        global _wrapper

        # The only field that needs special formatting is bilingual
        if self.type.label == "Bilingual":
            content = {"english": "", "french": ""}
            if isinstance(value, str):
                content[self.language] = value
            elif isinstance(value, dict):
                content.update(value)
            else:
                err = '"Bilingual" field value must be str or dict' 
                raise SchemaError(err)

            field = wrapper.wrap(self.label + ":")

            wrapper = copy.deepcopy(wrapper)
            wrapper.initial_indent += _wrapper.initial_indent
            wrapper.subsequent_indent += _wrapper.subsequent_indent

            field += Field.text_to_yaml("english", content["english"], wrapper)
            field += Field.text_to_yaml("french", content["french"], wrapper)
            
        else:
            field = Field.text_to_yaml(self.label, value, wrapper)

        return field 

    # ----------------------------------------
    def text_to_yaml(header, content, wrapper = _wrapper):

        # First pass, wrap as normal
        lines = wrapper.wrap(header + ": " + content)

        # If this results in multiple lines, then we need an extra indent
        if ( len(lines) > 1 ):
            lines = wrapper.wrap(header + ": >-")
            wrapper = copy.deepcopy(wrapper)

            # Blanking out indents to make sure there are no list dashes
            wrapper.initial_indent = " " * (len(wrapper.initial_indent) + 2)
            wrapper.subsequent_indent = " " * (len(wrapper.initial_indent) + 2)
            lines = lines + wrapper.wrap(content)

        return lines

# ===============================================================================
class Rule(XML):
    """
    Validation rule that can be used to assess Field entries.
    """

    # ----------------------------------------
    def __init__(self, *args, xml = None, language = "english"):

        super().__init__(xml, language)

    # ----------------------------------------
    @classmethod
    def from_id(cls, id_):

        return copy.deepcopy(_get_schema(cls.__name__, [id_]))

    # ----------------------------------------
    @cached_property
    def parameters(self):

        par = self._parameters
        id_ = int(self.id)

        if id_ == 8 or id_ == 18:

            return int(par)
        
        elif id_ == 20:
            # Requires parsing parameters
            lines = par.split(";")

            field_id = re.sub(":.*", "", lines[1])
            field = Field(field_id)

            lov_id = re.sub(":.*", "", lines[2])
            lov = LOV(lov_id)

            other_id = lines[-1]
            other = XML.to_dict(lov.values_list, "id")[other_id]

            out = {
                "field":field.label,
                "value":other.label,
            }

            op = re.sub(":.*", "", lines[-2])
            if int(op) == 359:
                out["is"] = True 
                out["op"] = operator.eq
                out["err"] = "entry required if {} is {}"
            else:
                out["is"] = False 
                out["op"] = operator.ne
                out["err"] = "entry required if {} is not {}"

            return out
        
        elif id_ == 24:
            
            field_id = re.sub(":.*", "", par)
            field = Field(field_id)

            return field.label

    # ----------------------------------------
    @property
    def prompt(self):

        id_ = int(self.id)

        # Only covering a fraction of the more common rules
        if id_ == 8:

            msg = "Must be fewer than {} characters long."
            return msg.format(self.parameters)
        
        elif id_ == 11:

            msg = "Must not be left blank."
            return msg

        elif id_ == 18:

            msg = "Must have {} entries or fewer."
            return msg.format(parameters)

        elif id_ == 20:

            if self.parameters["is"]:
                msg = "Required if {} is {}"
            else:
                msg = "Required if {} is not {}"

            return msg

        elif id_ == 24:
            
            msg = "Mutually exclusive with {}."
            return msg.format(self.parameters)

        return '"{}" -- not currently checked'.format(self.label)

    # ----------------------------------------
    def validate(self, value, entries = None):

        # Rules technically used but not implemented
        # 15 -- Unclear
        # 19 -- Unclear
        # 25 -- PubMed
        # 28 -- Birthday

        id_ = int(self.id)

        # Only covering a fraction of the more common rules
        if id_ == 8:

            if len(value) > self.parameters:
                return "too long"
        
        elif id_ == 11:

            if len(value) == 0:
                return "null entries not allowed"

        elif id_ == 18:

            if len(value) > self.parameters:
                return "too many entries"

        elif id_ == 20:

            # This rule has two parts: the virst part asks if the value is nil
            # The second asks whether another value is something or not
            # The error is parsed accordingly
            pars = self.parameters
            test = pars["op"](entries[pars["field"]], pars["value"])

            if len(value) == 0 and test:
                err = pars["err"]
                err = err.format(pars["field"], pars["value"])
                return err

        elif id_ == 24:

            # Requires parsing parameters
            if len(entries[self.parameters]) > 0 and len(value) > 0:
                err = '"{}" must be left blank if using "{}"'
                err = msg.format(self.parameters, value)
                return msg


# Generating default schema
load_schema()
