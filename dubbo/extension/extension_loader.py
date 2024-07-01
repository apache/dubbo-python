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
from typing import Any

from dubbo.extension import registry
from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


class ExtensionLoader:

    _instance = None
    _ins_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._ins_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._registries = registry.get_all_extended_registry()

    def get_extension(self, superclass: Any, name: str) -> Any:
        # Get the registry for the extension
        extension_impls = self._registries.get(superclass)
        err_msg = None
        if not extension_impls:
            err_msg = f"Extension {superclass} is not registered."
            logger.error(err_msg)
            raise ValueError(err_msg)

        # Get the full name of the class -> module.class
        full_name = extension_impls.get(name)
        if not full_name:
            err_msg = f"Extension {superclass} with name {name} is not registered."
            logger.error(err_msg)
            raise ValueError(err_msg)

        module_name = class_name = None
        try:
            # Split the full name into module and class
            module_name, class_name = full_name.rsplit(".", 1)
            # Load the module
            module = importlib.import_module(module_name)
            # Get the class from the module
            subclass = getattr(module, class_name)
            if subclass:
                # Check if the class is a subclass of the extension
                if issubclass(subclass, superclass) and subclass is not superclass:
                    # Return the class
                    return subclass
                else:
                    err_msg = f"Class {class_name} does not inherit from {superclass}."
            else:
                err_msg = f"Class {class_name} not found in module {module_name}"

            if err_msg:
                # If there is an error message, raise an exception
                raise Exception(err_msg)
        except ImportError as e:
            logger.exception(f"Module {module_name} could not be imported.")
            raise e
        except AttributeError as e:
            logger.exception(f"Class {class_name} not found in {module_name}.")
            raise e
        except Exception as e:
            if err_msg:
                logger.error(err_msg)
            else:
                logger.exception(f"An error occurred while loading {full_name}.")
            raise e
