import logging
from lxml import etree
import os
from unittest import TestCase
import warnings

import canadianccv
from canadianccv import CCV, Section

class TestCCV(TestCase):

    ccv = CCV(log_level = logging.DEBUG)

    def test_entry_addition(self):
    
        dirpath = os.path.join(os.path.dirname(__file__), 'yaml_files')
        
        path = os.path.join(dirpath, "course.yaml")
        self.ccv.add_file(path)

        path = os.path.join(dirpath, "course2.yaml")
        self.ccv.add_file(path)

        self.ccv.to_xml("test.xml", pretty_print = True)

        #print(self.ccv._index)
        #print(self.ccv._content)


