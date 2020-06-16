import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import _schema, Type, LOV, Reference, Field, XML

class TestField(TestCase):

    def test_fields(self):

        # From section
        field = Field.from_section("Role", "Courses Taught")

        assert field.label == "Role"
        assert field.id == "cefdb78ecd9e43fb8554d21e7d454132"

        # From id
        field2 = Field(field.id)

        assert field2.label == "Role"
        assert field2.id == "cefdb78ecd9e43fb8554d21e7d454132"

        # Double check caching
        assert field2 is field

    def test_field_lovs(self):

        # Checking LOV in field
        field = Field.from_section("Degree Type", "Degrees", "Education")

        assert field.label == "Degree Type"
        assert field.id == "a83a0af883924c57bb66107cc32b6d5e"

        assert field.type is Type("LOV")
        assert field.reference is LOV("Degree Type")

        id_ = field.reference.get_value("Bachelor's").id
        assert int(id_) == 71

    def test_field_refs(self):

        # Checking LOV in field
        field = Field.from_section("Organization", "Courses Taught")

        assert field.label == "Organization"
        assert field.id == "8280ef884eec43938a1aa4f7173a501e"

        assert field.type is Type("Reference")
        assert field.reference is Reference("Organization")

        id_ = field.reference.get_value("Dalhousie University").id
        assert int(id_) == 6544937977

