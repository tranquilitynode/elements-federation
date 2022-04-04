#!/usr/bin/env python
from setuptools import setup, find_packages
import os

setup(name='elements-federation',
      version='0.1',
      description='Federation Node Daemon',
      author='Originally CommerceBlock, modified by Tranquility Node Ltd',
      url='http://github.com/tranquilitynode/elements-federation',
      packages=find_packages(),
      scripts=[],
      include_package_data=True,
      data_files=[],
)
