import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import _schema, XML, Type, LOV, Reference

class TestType(TestCase):

    def test_basic_types(self):
    
        # On its own
        year = Type("Year")

        assert year.__class__.__name__ == "Type"
        assert year.label == "Year"
        assert year.id == "00000000000000000000000000000014"

    def test_lov_types(self):

        # On its own
        country = LOV("Country")

        assert country.__class__.__name__ == "LOV"
        assert country.label == "Country"
        assert country.id == "00000000000000000000000000002000"

        assert ( XML.to_list(country.values_list, "label")[:2] ==
                ['Afghanistan', 'Aland Islands'])

        assert ( XML.to_list(country.values_list, "label", sort = "id")[:2] ==
                ['Afghanistan', 'Albania'])

    def test_ref_types(self):

        # On its own
        org = Reference("Organization")

        assert org.__class__.__name__ == "Reference"
        assert org.label == "Organization"
        assert org.id == "ee597e9073b6479b94f903ca08f81903"

        assert ( XML.to_list(org.values_list, "label")[:2] ==
                ['Aachen Technical University', 'Aalborg Universitet'])
