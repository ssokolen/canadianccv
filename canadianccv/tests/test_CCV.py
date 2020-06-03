from lxml import etree
import os
from unittest import TestCase

import canadianccv
from canadianccv import CCV

class TestCCV(TestCase):

    ccv = CCV()

    def test_add_entries_from_toml(self):
        f = self.ccv.add_entries_from_toml

        path = os.path.join(os.path.dirname(__file__), 'toml_files')
        f(path)

        f = open('test.xml', 'wb')
        with f:
            #f.write(etree.tostring(self.ccv.xml, pretty_print = True))
            f.write(etree.tostring(self.ccv.xml, 
                pretty_print = False, xml_declaration = True, encoding = "UTF-8"))
        

