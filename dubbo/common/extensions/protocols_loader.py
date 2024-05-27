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

from dubbo.common.extensions import extension
from dubbo.protocols.protocol import Protocol


class ProtocolExtensionLoader(extension.ExtensionLoader):
    """
    Protocol extension loader.
    """
    # Store the protocol classes. k: name, v: protocol class
    __protocols: dict[str, type] = dict()

    @classmethod
    def set(cls, name: str, protocol_class: type):
        """
        Set the protocol.
        :param name: The name of the protocols.
        :param protocol_class: The protocol class.
        """
        # Check if the protocol_class is a subclass of Protocol.
        if not issubclass(protocol_class, Protocol):
            raise TypeError(f"Need a subclass of Protocol, but got {protocol_class}")
        cls.__protocols[name] = protocol_class

    @classmethod
    def get(cls, name) -> Protocol:
        """
        Get the protocols.
        :param name: The name of the protocols.
        :return: The protocol instance.
        """
        try:
            return cls.__protocols.get(name)()
        except KeyError:
            raise KeyError(f"Protocol extension not found: {name}")

    @classmethod
    def register(cls, name: str):
        """
        Register the protocols.
        This method is a decorator.
        :param name: The name of the protocols.
        """

        def decorator(protocol_class):
            cls.set(name, protocol_class)
            return protocol_class

        return decorator
