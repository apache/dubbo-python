#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from setuptools import find_packages, setup


# Read version from dubbo/__version__.py
with open("dubbo/__version__.py", "r", encoding="utf-8") as f:
    global_vars = {}
    exec(f.read(), global_vars)
    version = global_vars["__version__"]

# Read long description from README.md
with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="dubbo-python",
    version=version,
    license="Apache License Version 2.0",
    description="Python Implementation For Apache Dubbo.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Apache Dubbo Community",
    author_email="dev@dubbo.apache.org",
    url="https://github.com/apache/dubbo-python",
    classifiers=[
        "Development Status :: 4- Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.11",
        "Framework :: AsyncIO",
        "Topic :: Internet",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Networking",
    ],
    keywords=["dubbo", "rpc", "dubbo-python", "http2", "network"],
    packages=find_packages(include=("dubbo", "dubbo.*")),
    test_suite="tests",
    python_requires=">=3.11",
    install_requires=["h2>=4.1.0", "uvloop>=0.19.0; platform_system!='Windows'"],
    extras_require={"zookeeper": ["kazoo>=2.10.0"]},
)
