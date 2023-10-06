#!/usr/bin/env python

import os
import sys
from pathlib import Path

import setuptools

from pyadtpulse.const import __version__

if sys.argv[-1] == "publish":
    os.system("python setup.py sdist upload")
    sys.exit()

# read the contents of your README file
from os import path

this_directory = path.abspath(path.dirname(__file__))
long_description = Path(
    path.join(this_directory, "README.md"), encoding="utf-8"
).read_text()

setuptools.setup(
    name="pyadtpulse",
    version=__version__,
    packages=["pyadtpulse"],
    description="Python interface for ADT Pulse security systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rlippmann/pyadtpulse",
    author="",
    author_email="",
    license="Apache Software License",
    install_requires=["aiohttp>=3.8.1", "uvloop>=0.17.0"],
    keywords=["security system", "adt", "home automation", "security alarm"],
    zip_safe=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)
