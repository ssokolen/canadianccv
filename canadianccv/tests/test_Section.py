import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import _schema, Section, XML

class TestSection(TestCase):

    def test_sections(self):

        # From single name
        course = Section("Courses Taught")

        assert course.label == "Courses Taught"
        assert course.id == "9dc74140d0ff4b26a2d4a559bc9b5a2b"

        # From id
        course = Section(course.id)

        assert course.label == "Courses Taught"
        assert course.id == "9dc74140d0ff4b26a2d4a559bc9b5a2b"

        # From two names and caching
        course2 = Section("Courses Taught", "Teaching Activities")

        assert course2 is course

        # From entries

        # Error
        #course2 = Section.from_entries(["Role", "Course Code", "Order"])
        
        course2 = Section.from_entries(
            ["Role", "Organization", "Department", "Course Code"])

        assert course2 is course

        #print(course.yaml_template())
