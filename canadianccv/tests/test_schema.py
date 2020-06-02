from lxml import etree
from unittest import TestCase

import canadianccv

import canadianccv.schema as schema

class TestSchema(TestCase):
    def test_loaded(self):
        self.assertTrue(isinstance(schema.cv, etree._Element))
