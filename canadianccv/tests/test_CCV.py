import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import CCV

class TestCCV(TestCase):

    #ccv = CCV(os.path.join(os.path.dirname(__file__), 'toml_files', 'ccv.xml'))
    ccv = CCV(log_level = logging.DEBUG)

    def test_add_entries_from_toml(self):
        f = self.ccv.add_entries

        path = os.path.join(os.path.dirname(__file__), 'toml_files')
        f(path)

        f = open('test.xml', 'wb')
        with f:
            f.write(etree.tostring(self.ccv.xml, pretty_print = True))

    def test_add_entries_from_yaml(self):
    
        f = self.ccv.add_entries

        path = os.path.join(os.path.dirname(__file__), 'yaml_files')
        f(path)

        f = open('test.xml', 'wb')
        with f:
            f.write(etree.tostring(self.ccv.xml, pretty_print = True))

    def test_add_entries(self):
        f = self.ccv.add_entries

        path = os.path.join(os.path.dirname(__file__))
        f(path)

        f = open('test.xml', 'wb')
        with f:
            f.write(etree.tostring(self.ccv.xml, pretty_print = True))

    def test_add_entries_glob(self):
        f = self.ccv.add_entries

        path = os.path.join(os.path.dirname(__file__))
        f(path, pattern = "*yaml")

        f = open('test.xml', 'wb')
        with f:
            f.write(etree.tostring(self.ccv.xml, pretty_print = True))
