import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import _schema, Type, LOV

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

        country.value_labels
        country.value_labels

        """
        # Using id lookup
        year = GenericType.from_id(year.id)

        assert year.__class__.__name__ == "GenericType"
        assert year.label == "Year"
        assert year.id == "00000000000000000000000000000014"

        # Using label lookup
        year = GenericType.from_label(year.label)

        assert year.__class__.__name__ == "GenericType"
        assert year.label == "Year"
        assert year.id == "00000000000000000000000000000014"
        """


