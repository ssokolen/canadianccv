from lxml import etree
from unittest import TestCase

import canadianccv
from canadianccv import Schema, SectionError

class TestSchema(TestCase):

    schema = Schema()

    def test_ref_table(self):
        table_id = "ee597e9073b6479b94f903ca08f81903"
        self.assertTrue(table_id in self.schema._ref_ids)

        ref_label = "Dalhousie University"
        self.assertTrue(ref_label in self.schema._ref_ids[table_id])
        
        dal_id, meta = self.schema._ref_ids[table_id][ref_label]
        self.assertTrue(dal_id == "00000000000000000000006544937977")
        self.assertTrue(len(meta) == 4)
        self.assertTrue(meta[1]["label"] == "Nova Scotia")

        # There is however a discrepency between Canada and CANADA that
        # may cause problems in the future

    def test_get_section_element(self):
        f = self.schema.get_section_element

        elem = f("Courses Taught")
        self.assertTrue(isinstance(elem, etree._Element))

        self.assertRaises(SectionError, f, "Test")
        self.assertRaises(SectionError, f, "Research Disciplines")

    def test_get_lov_id(self):
        f = self.schema.get_lov_id

        fields = self.schema.get_field_elements("Courses Taught")

        lov_id = f("Undergraduate", fields["Course Level"])
        self.assertTrue(lov_id == "00000000000000000000000100000400")

    def test_get_ref_ids(self):
        f = self.schema.get_ref_ids

        fields = self.schema.get_field_elements("Courses Taught")

        ref_id, meta = f("Dalhousie University", fields["Organization"])
        self.assertTrue(ref_id == "00000000000000000000006544937977")

        self.assertTrue(len(meta) == 4)
        self.assertTrue(meta[1]["label"] == "Nova Scotia")


