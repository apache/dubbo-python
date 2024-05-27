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


class ExtensionLoader:
    """
    Extension loader Interface.
    Any class that implements this interface can be called an extension loader.
    """

    @classmethod
    def set(cls, name: str, extension):
        """
        Set the extension.
        :param name: The name of the extension.
        :param extension: The extension.
        """
        raise NotImplementedError("Method 'set' is not implemented.")

    @classmethod
    def get(cls, name: str):
        """
        Get the extension.
        :param name: The name of the extension.
        :return: The extension.
        """
        raise NotImplementedError("Method 'get' is not implemented.")

    @classmethod
    def register(cls, name: str):
        """
        Register the extension.
        This method is a decorator.
        :param name: The name of the extension.
        """
        raise NotImplementedError("Method 'register' is not implemented.")
