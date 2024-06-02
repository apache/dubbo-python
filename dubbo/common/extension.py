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
import threading
from typing import Dict, Type

from dubbo.common.utils.file_utils import IniFileUtils


def load_type(config_str: str) -> Type:
    """
    Dynamically load a type from a module based on a configuration string.

    :param config_str: Configuration string in the format 'module_path:class_name'.
    :return: The loaded type.
    :raises ValueError: If the configuration string format is incorrect or the object is not a type.
    :raises ImportError: If there is an error importing the specified module.
    :raises AttributeError: If the specified attribute is not found in the module.
    """
    module_path, class_name = '', ''
    try:
        # Split the configuration string to obtain the module path and object name
        module_path, class_name = config_str.rsplit(':', 1)

        # Import the module
        module = importlib.import_module(module_path)

        # Get the specified type from the module
        loaded_type = getattr(module, class_name)

        # Ensure the loaded object is a type (class)
        if not isinstance(loaded_type, type):
            raise ValueError(f"'{class_name}' is not a valid type in module '{module_path}'")

        return loaded_type
    except ValueError as e:
        raise ValueError("Invalid configuration string. Use 'module_path:class_name' format.") from e
    except ImportError as e:
        raise ImportError(f"Error importing module '{module_path}': {e}") from e
    except AttributeError as e:
        raise AttributeError(f"Module '{module_path}' does not have an attribute '{class_name}'") from e


class ExtensionLoader:
    """
    Extension loader.
    """

    def __init__(self, class_type: type, classes: Dict[str, str]):
        self._class_type = class_type  # class type
        self._classes = {}
        self._instances = {}
        self._instance_lock = threading.Lock()
        for name, config_str in classes.items():
            o = load_type(config_str)
            if issubclass(o, class_type):
                self._classes[name] = o
            else:
                raise ValueError(f"Class {class_type} is not a subclass of {object}")

    @property
    def class_type(self):
        return self._class_type

    @property
    def classes(self):
        return self._classes

    def get_instance(self, name: str):
        # check if the class exists
        if name not in self._classes:
            raise ValueError(f"Class {name} not found in {self._class_type}")

        # get the instance
        if name not in self._instances:
            with self._instance_lock:
                if name not in self._instances:
                    self._instances[name] = self._classes[name]()
        return self._instances[name]


class ExtensionManager:
    """
    Extension manager.
    """

    def __init__(self):
        self._extension_loaders: Dict[type, ExtensionLoader] = {}

    def initialize(self):
        """
        Read the configuration file and initialize the extension manager.
        """
        extensions = IniFileUtils.parse_config("extensions.ini")
        for section, classes in extensions.items():
            class_type = load_type(section)
            self._extension_loaders[class_type] = ExtensionLoader(class_type, classes)

    def get_extension_loader(self, class_type: type) -> ExtensionLoader:
        """
        Get the extension loader for a given class object.

        :param class_type: Class object.
        :return: Extension loader.
        """
        return self._extension_loaders.get(class_type)
