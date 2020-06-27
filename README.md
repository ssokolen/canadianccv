## About The Project

The aim of this package is to facilitate filling out the Canadian Common CV ([CCV]) by minimizing manual entry via the web portal. Rather than filling out fields online, this package can be used to generate an XML import file directly from a set of YAML files. While required fields still have to filled, using YAML files allows for simple copy-pasting oft-repeated boilerplate while changing only a few key fields in an easy to read format. 

[CCV]: https://ccv-cvc.ca/indexresearcher-eng.frm

### Disclaimer
I am in no way affiliated with the CCV Network or any funding agency. I created this project out of a personal preference to keep local records in a text format. I cannot guarantee that the generated xml files will not break something so please back up your existing CV and use this package at your own risk.

### Data source
The package uses publically available XML schemas from the [CCV website], so the XML definitions should be relatively sound.

[CCV website]: https://ccv-cvc-admin.ca/schema/doc-en.html

### Current status
I'm still in the process of moving my own CCV entirely to YAML files and debugging as I go. Please open an issue if you would like to see extra examples or if something isn't working as intended.

The basic implementation seems like its working (at least on Linux) but small issues are likely to creep up. A couple of field types that I have not yet encountered in my own CV have not been properly implemented: `Datetime`, `Elapsed-Time`, and `PubMed`. Similarly, the code has technically been written for both English and French entries but I have not tested French input at all.

## Installation

Install directly from GitHub (or clone and install locally):

```sh
python3 -m pip install git+https://github.com/ssokolen/canadianccv
```

## Usage

Basic usage boils down to:

```python

from canadianccv import CCV

# Initialize blank CCV class
ccv = CCV()

# Populate a directory with yaml files (nested directories are fine)
# Assuming all yaml files are contained in a directory called "CCV_files"
ccv.add_files("/path/to/CCV_files", pattern = "*.yaml")

ccv.to_xml("/path/to/ccv_export.xml")
```

In most cases, new entries will likely be added to an existing XML file rather than generating an entire XML from scratch. If so, just add path to the existing file `CCV()`: 

```python

from canadianccv import CCV

# Initialize CCV class from existing file "old_ccv.xml"
ccv = CCV("/path/to/old_ccv.xml")

# Populate a directory with yaml files (nested directories are fine)
# Assuming all yaml files are contained in a directory called "CCV_files"
ccv.add_files("/path/to/CCV_files", pattern = "*.yaml")

ccv.to_xml("/path/to/ccv_export.xml")
```

This is what the contents of a typical yaml file would look like:

```python

from canadianccv import CCV

# Initialize CCV class from existing file "old_ccv.xml"
ccv = CCV()

# YAML string for demonstration purposes
yaml_text = """
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

# Add the entries and export
ccv.add_yaml(text)
ccv.to_xml("/path/to/ccv_export.xml")
```

Template files can be generated from any valid section label or id:

```python

from canadianccv import Section 

# Looking up section based on label
courses = Section("Courses Taught")
courses.template("template.yaml")

```

However, it will probably be more convenient to access Section/Field information from the [online schema].

[online schema]: https://ccv-cvc-admin.ca/schema/dataset-en.html

It is also possible to import an existing XML file and convert specific sections to YAML:

```python

from canadianccv import CCV

# Initialize CCV class from existing file "old_ccv.xml"
ccv = CCV("/path/to/old_ccv.xml")

# Output specific section of ccv to YAML file
ccv.to_yaml("export.yaml", "Courses Taught")
```

This last method is probably the easiest approach to adding new entries. Just load an existing XML export, output relevant section to YAML, and copy-paste the existing entries to make new ones. 

## Gotchas

A few things to be aware of:

* A few fields are restricted to a specific set of values that are defined in the schema as HTML characters. So, for example, "Master's Thesis" would likely fail to pass validation since it uses an ASCII apostrophe rather than the "right apostrophe" character U+2019. This is the only example I've encountered thus far, but there may be more.
* Existing CCV entries may contain symbols that have a special meaning in the YAML syntax (such as square brackets). There is no way around this right now other than editing such entries before trying to reimport them into XML from YAML.

## Roadmap

The first step will be to finish debugging everything and ensure that all fields and validations are implemented for both English and French entries. After that, I'll convert the existing functionality to a command-line tool.
