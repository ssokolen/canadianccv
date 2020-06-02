import importlib.resources
from lxml import etree

def _read_schema(path):
    content = importlib.resources.read_binary('canadianccv', path)
    return etree.XML(content)

cv = _read_schema("cv.xml")
lov = _read_schema("lov.xml")
ref = _read_schema("ref.xml")
