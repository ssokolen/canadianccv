from lxml import etree
import os
from unittest import TestCase

import canadianccv
from canadianccv import CCV, SectionError

class TestCCV(TestCase):

    ccv = CCV()

    def test_init(self):
        self.assertTrue(isinstance(self.ccv.schema, etree._Element))

    def test_get_section_element(self):
        f = self.ccv.get_section_element

        elem = f("Courses Taught")
        self.assertTrue(isinstance(elem, etree._Element))

        self.assertRaises(SectionError, f, "Test")
        self.assertRaises(SectionError, f, "Research Disciplines")

    def test_get_field_elements(self):
        f = self.ccv.get_field_elements

        fields = f("Courses Taught")
        self.assertTrue(isinstance(fields, dict))
        self.assertTrue(len(fields) > 0)

        self.assertRaises(SectionError, f, "Test")
        self.assertRaises(SectionError, f, "Research Disciplines")

    def test_add_entries_from_toml(self):
        f = self.ccv.add_entries_from_toml

        path = os.path.join(os.path.dirname(__file__), 'toml_files')
        f(path)
        

