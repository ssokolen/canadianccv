import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import CCV, Section, _schema

log = logging.getLogger("CCV")
log.setLevel("CRITICAL")

class TestCCV(TestCase):

    ccv = CCV()

    def cycle_yaml(self, text):
        """All tests essentially boil down to ensuring import is consistent."""

        # First cycle
        self.ccv.add_yaml(text)
        self.ccv.to_yaml("test.yaml")
        self.ccv.to_xml("test.xml")

        f = open("test.xml")
        with f:
            first = f.read()

        f = open("test.yaml")
        with f:
            yaml = f.read()

        assert len(yaml) > 0

        # Second cycle
        self.ccv = CCV()
        self.ccv.add_file("test.yaml")
        self.ccv.to_xml("test.xml")

        f = open("test.xml")
        with f:
            second = f.read()

        assert first == second

    def test_student_yaml(self):

        text = """
        Student Name: Test Student
        Degree Type or Postdoctoral Status: Master’s Thesis
        Thesis/Project Title: >-
          A long and interesting thesis.

        Supervision Role: Academic Advisor
        Supervision Start Date: 2000/01
        Supervision End Date: 3000/01

        Student Degree Start Date: 2000/01
        Student Degree Expected Date: 3000/01
        Student Degree Status: In Progress

        Student Institution: Dalhousie University
        Student Canadian Residency Status: Canadian Citizen

        Project Description:
          english: A long and interesting project.
          french: 
        Degree Name:
          english: Engineering
          french: 
        Specialization:
          english: 
          french: 
        """

        self.cycle_yaml(text)

    def test_course_yaml(self):

        text = """
        Course Code: Test 1000
        Course Title: CCV Test
        Course Topic: Testing CCV import
        Course Level: Undergraduate
        Lecture Hours Per Week: 3
        Tutorial Hours Per Week: 2

        Academic Session: Winter
        Number of Students: 1
        Number of Credits: 3
        Start Date: 2000-01-01
        End Date: 2000-04-20

        Role: Professor
        Guest Lecture?: No
        Organization: Dalhousie University
        Department: Department of CCV
        Section: CCV Program
        """

        self.cycle_yaml(text)
