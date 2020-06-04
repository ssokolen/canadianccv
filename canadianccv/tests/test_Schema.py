from lxml import etree
from unittest import TestCase

import canadianccv
from canadianccv import Schema, SectionError

class TestSchema(TestCase):

    schema = Schema()

    def test_get_section_id(self):
        f = self.schema.get_section_id

        section_id = f("Courses Taught")
        elem = self.schema.get_section_schema(section_id)
        self.assertTrue(isinstance(elem, etree._Element))

        self.assertRaises(SectionError, f, "Test")
        self.assertRaises(SectionError, f, "Research Disciplines")

    def test_get_lov_id(self):
        f = self.schema.get_lov_id

        section_id = self.schema.get_section_id("Courses Taught")
        fields = self.schema.get_section_fields(section_id)

        lov_id = f("Undergraduate", fields["Course Level"])
        self.assertTrue(lov_id == "00000000000000000000000100000400")

    def test_get_ref_ids(self):
        f = self.schema.get_ref_ids

        section_id = self.schema.get_section_id("Courses Taught")
        fields = self.schema.get_section_fields(section_id)

        ref_id, meta = f("Dalhousie University", fields["Organization"])
        self.assertTrue(ref_id == "00000000000000000000006544937977")

        self.assertTrue(len(meta) == 4)
        self.assertTrue(meta[1]["label"] == "Nova Scotia")


