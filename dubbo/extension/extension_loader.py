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

import importlib
from typing import Any

from dubbo.common import SingletonBase
from dubbo.extension import registries as registries_module


class ExtensionError(Exception):
    """
    Extension error.
    """

    def __init__(self, message: str):
        """
        Initialize the extension error.
        :param message: The error message.
        :type message: str
        """
        super().__init__(message)


class ExtensionLoader(SingletonBase):
    """
    Singleton class for loading extension implementations.
    """

    def __init__(self):
        """
        Initialize the extension loader.

        Load all the registries from the registries module.
        """
        if not hasattr(self, "_initialized"):  # Ensure __init__ runs only once
            self._registries = {}
            for name in registries_module.__all__:
                registry = getattr(registries_module, name)
                self._registries[registry.interface] = registry.impls
            self._initialized = True

    def get_extension(self, interface: Any, impl_name: str) -> Any:
        """
        Get the extension implementation for the interface.

        :param interface: Interface class.
        :type interface: Any
        :param impl_name: Implementation name.
        :type impl_name: str
        :return: Extension implementation class.
        :rtype: Any
        :raises ExtensionError: If the interface or implementation is not found.
        """
        # Get the registry for the interface
        impls = self._registries.get(interface)
        if not impls:
            raise ExtensionError(f"Interface '{interface.__name__}' is not supported.")

        # Get the full name of the implementation
        full_name = impls.get(impl_name)
        if not full_name:
            raise ExtensionError(
                f"Implementation '{impl_name}' for interface '{interface.__name__}' is not exist."
            )

        try:
            # Split the full name into module and class
            module_name, class_name = full_name.rsplit(".", 1)

            # Load the module and get the class
            module = importlib.import_module(module_name)
            subclass = getattr(module, class_name)

            # Return the subclass
            return subclass
        except Exception as e:
            raise ExtensionError(
                f"Failed to load extension '{impl_name}' for interface '{interface.__name__}'. \n"
                f"Detail: {e}"
            )
