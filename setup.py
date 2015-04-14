#!/usr/bin/env python
# coding: utf-8
"""
Python Dubbo Library Client Server - Setup
 
Created
    2015-4-10 by Joe - https://github.com/JoeCao
"""

import os
from setuptools import setup, find_packages

THISDIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(THISDIR)

VERSION = open("version.txt").readline().strip()
HOMEPAGE = "https://github.com/ofpay/dubbo-client-py"
DOWNLOAD_BASEURL = "https://github.com/ofpay/dubbo-client-py/raw/master/dist/"
DOWNLOAD_URL = DOWNLOAD_BASEURL + "dubbo-client-%s-py2.7.egg" % VERSION


setup(
    name = "dubbo-client",
    version = VERSION,
    description = (
        "Python Dubbo Client"
    ),
    long_description = open("README.MD").read(),
    keywords = (
        "Dubbo, JSON-RPC, JSON, RPC, Client,"
        "HTTP-Client, Remote Procedure Call, JavaScript Object Notation, "
    ),
    author = "Joe Cao",
    author_email = "chinalibra@gmail.com",
    url = HOMEPAGE,
    download_url = DOWNLOAD_URL,
    packages = find_packages(),
    classifiers = [
        #"Development Status :: 1 - Planning",
        # "Development Status :: 2 - Pre-Alpha",
        # "Development Status :: 3 - Alpha",
        "Development Status :: 4 - Beta",
        # "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications",
        "Topic :: System :: Networking",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
    ],
    install_requires = ["kazoo>=2.0", "python-jsonrpc>=0.7.3"],
)