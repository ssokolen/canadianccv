import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import CCV

class TestCCV(TestCase):

    ccv = CCV(log_level = logging.DEBUG)

    def test_add_entries_from_yaml(self):
    
        path = os.path.join(os.path.dirname(__file__), 'yaml_files')
        path = os.path.join(path, "course.yaml")
        self.ccv.add_file(path)

        self.ccv.write_xml("test.xml", pretty_print = True)


