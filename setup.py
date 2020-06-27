from setuptools import setup

setup(name='canadianccv',
      version='0.1',
      description='Canadian Common CV generator',
      url='TBD',
      author='Stanislav Sokolenko',
      author_email='stanislav@sokolenko.net',
      license='Apache-2.0',
      packages=['canadianccv'],
      zip_safe=False,
      test_suite='nose.collector',
      tests_require=['nose'],
      include_package_data=True,
      install_requires=[
          'cached-property',
          'flatten-dict',
          'lxml',
          'pyyaml',
          'tomlkit',
      ],)
