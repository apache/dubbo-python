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
import abc
from dataclasses import dataclass
from typing import Optional, Union

from dubbo.constants import (
    common_constants,
    config_constants,
    logger_constants,
    registry_constants,
)
from dubbo.proxy.handlers import RpcServiceHandler
from dubbo.url import URL, create_url
from dubbo.utils import NetworkUtils

__all__ = [
    "ApplicationConfig",
    "ReferenceConfig",
    "ServiceConfig",
    "RegistryConfig",
    "LoggerConfig",
]


class AbstractConfig(abc.ABC):
    """
    Abstract configuration class.
    """

    __slots__ = ["id"]

    def __init__(self):
        # Identifier for this configuration.
        self.id: Optional[str] = None


class ApplicationConfig(AbstractConfig):
    """
    Configuration for the dubbo application.
    """

    __slots__ = [
        "_name",
        "_version",
        "_owner",
        "_organization",
        "_architecture",
        "_environment",
    ]

    def __init__(
        self,
        name: str,
        version: Optional[str] = None,
        owner: Optional[str] = None,
        organization: Optional[str] = None,
        architecture: Optional[str] = None,
        environment: Optional[str] = None,
    ):
        """
        Initialize the application configuration.
        :param name: The name of the application.
        :type name: str
        :param version: The version of the application.
        :type version: Optional[str]
        :param owner: The owner of the application.
        :type owner: Optional[str]
        :param organization: The organization(BU) of the application.
        :type organization: Optional[str]
        :param architecture: The architecture of the application.
        :type architecture: Optional[str]
        :param environment: The environment of the application. e.g. dev, test, prod.
        :type environment: Optional[str]
        """
        super().__init__()

        self._name = name
        self._version = version
        self._owner = owner
        self._organization = organization
        self._architecture = architecture

        self._environment = self._ensure_environment(environment)

    @property
    def name(self) -> str:
        """
        Get the name of the application.
        :return: The name of the application.
        :rtype: str
        """
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        """
        Set the name of the application.
        :param name: The name of the application.
        :type name: str
        """
        self._name = name

    @property
    def version(self) -> Optional[str]:
        """
        Get the version of the application.
        :return: The version of the application.
        :rtype: Optional[str]
        """
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        """
        Set the version of the application.
        :param version: The version of the application.
        :type version: str
        """
        self._version = version

    @property
    def owner(self) -> Optional[str]:
        """
        Get the owner of the application.
        :return: The owner of the application.
        :rtype: Optional[str]
        """
        return self._owner

    @owner.setter
    def owner(self, owner: str) -> None:
        """
        Set the owner of the application.
        :param owner: The owner of the application.
        :type owner: str
        """
        self._owner = owner

    @property
    def organization(self) -> Optional[str]:
        """
        Get the organization(BU) of the application.
        :return: The organization(BU) of the application.
        :rtype: Optional[str]
        """
        return self._organization

    @organization.setter
    def organization(self, organization: str) -> None:
        """
        Set the organization(BU) of the application.
        :param organization: The organization(BU) of the application.
        :type organization: str
        """
        self._organization = organization

    @property
    def architecture(self) -> Optional[str]:
        """
        Get the architecture of the application.
        :return: The architecture of the application.
        :rtype: Optional[str]
        """
        return self._architecture

    @architecture.setter
    def architecture(self, architecture: str) -> None:
        """
        Set the architecture of the application.
        :param architecture: The architecture of the application.
        :type architecture: str
        """
        self._architecture = architecture

    @property
    def environment(self) -> str:
        """
        Get the environment of the application.
        :return: The environment of the application.
        :rtype: str
        """
        return self._environment

    @environment.setter
    def environment(self, environment: str) -> None:
        """
        Set the environment of the application.
        :param environment: The environment of the application.
        :type environment: str
        """
        self._environment = self._ensure_environment(environment)

    @staticmethod
    def _ensure_environment(environment: Optional[str]) -> str:
        """
        Ensure the environment is valid.
        :param environment: The environment.
        :type environment: Optional[str]
        :return: The environment. If the environment is None, return the default environment.
        :rtype: str
        """
        if not environment:
            return config_constants.PRODUCTION_ENVIRONMENT

        # ignore case
        environment = environment.lower()

        allowed_environments = [
            config_constants.TEST_ENVIRONMENT,
            config_constants.DEVELOPMENT_ENVIRONMENT,
            config_constants.PRODUCTION_ENVIRONMENT,
        ]

        if environment not in allowed_environments:
            raise ValueError(
                f"Unsupported environment: {environment}, "
                f"only support {allowed_environments}, "
                f"default is {config_constants.PRODUCTION_ENVIRONMENT}."
            )

        return environment


class ReferenceConfig(AbstractConfig):
    """
    Configuration for the dubbo reference.
    """

    __slots__ = ["_protocol", "_service", "_host", "_port"]

    def __init__(
        self,
        protocol: str,
        service: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """
        Initialize the reference configuration.
        :param protocol: The protocol of the server.
        :type protocol: str
        :param service: The name of the server.
        :type service: str
        :param host: The host of the server.
        :type host: Optional[str]
        :param port: The port of the server.
        :type port: Optional[int]
        """
        super().__init__()
        self._protocol = protocol
        self._service = service
        self._host = host
        self._port = port

    @property
    def protocol(self) -> str:
        """
        Get the protocol of the server.
        :return: The protocol of the server.
        :rtype: str
        """
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: str) -> None:
        """
        Set the protocol of the server.
        :param protocol: The protocol of the server.
        :type protocol: str
        """
        self._protocol = protocol

    @property
    def service(self) -> str:
        """
        Get the name of the service.
        :return: The name of the service.
        :rtype: str
        """
        return self._service

    @service.setter
    def service(self, service: str) -> None:
        """
        Set the name of the service.
        :param service: The name of the service.
        :type service: str
        """
        self._service = service

    @property
    def host(self) -> Optional[str]:
        """
        Get the host of the server.
        :return: The host of the server.
        :rtype: Optional[str]
        """
        return self._host

    @host.setter
    def host(self, host: str) -> None:
        """
        Set the host of the server.
        :param host: The host of the server.
        :type host: str
        """
        self._host = host

    @property
    def port(self) -> Optional[int]:
        """
        Get the port of the server.
        :return: The port of the server.
        :rtype: Optional[int]
        """
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        """
        Set the port of the server.
        :param port: The port of the server.
        :type port: int
        """
        self._port = port

    def to_url(self) -> URL:
        """
        Convert the reference configuration to a URL.
        :return: The URL.
        :rtype: URL
        """
        return URL(
            scheme=self.protocol,
            host=self.host,
            port=self.port,
            path=self.service,
            parameters={common_constants.SERVICE_KEY: self.service},
        )

    @classmethod
    def from_url(cls, url: Union[str, URL]) -> "ReferenceConfig":
        """
        Create a reference configuration from a URL.
        :param url: The URL.
        :type url: Union[str,URL]
        :return: The reference configuration.
        :rtype: ReferenceConfig
        """
        if isinstance(url, str):
            url = create_url(url)
        return cls(
            protocol=url.scheme,
            service=url.parameters.get(common_constants.SERVICE_KEY, url.path),
            host=url.host,
            port=url.port,
        )


class ServiceConfig(AbstractConfig):
    """
    Configuration for the dubbo service.
    """

    def __init__(
        self,
        service_handler: RpcServiceHandler,
        host: Optional[str] = None,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
    ):
        super().__init__()

        self._service_handler = service_handler
        self._host = host or NetworkUtils.get_local_address() or common_constants.LOCAL_HOST_VALUE
        self._port = port or common_constants.DEFAULT_PORT
        self._protocol = protocol or common_constants.TRIPLE_SHORT

    @property
    def service_handler(self) -> RpcServiceHandler:
        """
        Get the service handler.
        :return: The service handler.
        :rtype: RpcServiceHandler
        """
        return self._service_handler

    @service_handler.setter
    def service_handler(self, service_handler: RpcServiceHandler) -> None:
        """
        Set the service handler.
        :param service_handler: The service handler.
        :type service_handler: RpcServiceHandler
        """
        self._service_handler = service_handler

    @property
    def host(self) -> str:
        """
        Get the host of the service.
        :return: The host of the service.
        :rtype: str
        """
        return self._host

    @host.setter
    def host(self, host: str) -> None:
        """
        Set the host of the service.
        :param host: The host of the service.
        :type host: str
        """
        self._host = host

    @property
    def port(self) -> int:
        """
        Get the port of the service.
        :return: The port of the service.
        :rtype: int
        """
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        """
        Set the port of the service.
        :param port: The port of the service.
        :type port: int
        """
        self._port = port

    @property
    def protocol(self) -> str:
        """
        Get the protocol of the service.
        :return: The protocol of the service.
        :rtype: str
        """
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: str) -> None:
        """
        Set the protocol of the service.
        :param protocol: The protocol of the service.
        :type protocol: str
        """
        self._protocol = protocol

    def to_url(self) -> URL:
        """
        Convert the service configuration to a URL.
        :return: The URL.
        :rtype: URL
        """
        return URL(
            scheme=self.protocol,
            host=self.host,
            port=self.port,
            parameters={common_constants.SERVICE_KEY: self.service_handler.service_name},
            attributes={common_constants.SERVICE_HANDLER_KEY: self.service_handler},
        )


class RegistryConfig(AbstractConfig):
    """
    Configuration for the registry.
    """

    __slots__ = [
        "_protocol",
        "_host",
        "_port",
        "_username",
        "_password",
        "_load_balance",
        "_group",
        "_version",
    ]

    def __init__(
        self,
        protocol: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        load_balance: Optional[str] = None,
        group: Optional[str] = None,
        version: Optional[str] = None,
    ):
        """
        Initialize the registry configuration.
        :param protocol: The protocol of the registry.
        :type protocol: str
        :param host: The host of the registry.
        :type host: str
        :param port: The port of the registry.
        :type port: int
        :param username: The username of the registry.
        :type username: Optional[str]
        :param password: The password of the registry.
        :type password: Optional[str]
        :param load_balance: The load balance of the registry.
        :type load_balance: Optional[str]
        :param group: The group of the registry.
        :type group: Optional[str]
        :param version: The version of the registry.
        :type version: Optional[str]
        """
        super().__init__()

        self._protocol = protocol
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._load_balance = load_balance
        self._group = group
        self._version = version

    @property
    def protocol(self) -> str:
        """
        Get the protocol of the registry.
        :return: The protocol of the registry.
        :rtype: str
        """
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: str) -> None:
        """
        Set the protocol of the registry.
        :param protocol: The protocol of the registry.
        :type protocol: str
        """
        self._protocol = protocol

    @property
    def host(self) -> str:
        """
        Get the host of the registry.
        :return: The host of the registry.
        :rtype: str
        """
        return self._host

    @host.setter
    def host(self, host: str) -> None:
        """
        Set the host of the registry.
        :param host: The host of the registry.
        :type host: str
        """
        self._host = host

    @property
    def port(self) -> int:
        """
        Get the port of the registry.
        :return: The port of the registry.
        :rtype: int
        """
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        """
        Set the port of the registry.
        :param port: The port of the registry.
        :type port: int
        """
        self._port = port

    @property
    def username(self) -> Optional[str]:
        """
        Get the username of the registry.
        :return: The username of the registry.
        :rtype: Optional[str]
        """
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        """
        Set the username of the registry.
        :param username: The username of the registry.
        :type username: str
        """
        self._username = username

    @property
    def password(self) -> Optional[str]:
        """
        Get the password of the registry.
        :return: The password of the registry.
        :rtype: Optional[str]
        """
        return self._password

    @password.setter
    def password(self, password: str) -> None:
        """
        Set the password of the registry.
        :param password: The password of the registry.
        :type password: str
        """
        self._password = password

    @property
    def load_balance(self) -> Optional[str]:
        """
        Get the load balance of the registry.
        :return: The load balance of the registry.
        :rtype: Optional[str]
        """
        return self._load_balance

    @load_balance.setter
    def load_balance(self, load_balance: str) -> None:
        """
        Set the load balance of the registry.
        :param load_balance: The load balance of the registry.
        :type load_balance: str
        """
        self._load_balance = load_balance

    @property
    def group(self) -> Optional[str]:
        """
        Get the group of the registry.
        :return: The group of the registry.
        :rtype: Optional[str]
        """
        return self._group

    @group.setter
    def group(self, group: str) -> None:
        """
        Set the group of the registry.
        :param group: The group of the registry.
        :type group: str
        """
        self._group = group

    @property
    def version(self) -> Optional[str]:
        """
        Get the version of the registry.
        :return: The version of the registry.
        :rtype: Optional[str]
        """
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        """
        Set the version of the registry.
        :param version: The version of the registry.
        :type version: str
        """
        self._version = version

    def to_url(self) -> URL:
        """
        Convert the registry configuration to a URL.
        :return: The URL.
        :rtype: URL
        """
        parameters = {}
        if self.load_balance:
            parameters[registry_constants.LOAD_BALANCE_KEY] = self.load_balance
        if self.group:
            parameters[config_constants.GROUP] = self.group
        if self.version:
            parameters[config_constants.VERSION] = self.version

        return URL(
            scheme=self.protocol,
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            parameters=parameters,
        )

    @classmethod
    def from_url(cls, url: Union[str, URL]) -> "RegistryConfig":
        """
        Create a registry configuration from a URL.
        :param url: The URL.
        :type url: Union[str,URL]
        :return: The registry configuration.
        :rtype: RegistryConfig
        """
        if isinstance(url, str):
            url = create_url(url)
        return cls(
            protocol=url.scheme,
            host=url.host,
            port=url.port,
            username=url.username,
            password=url.password,
            load_balance=url.parameters.get(registry_constants.LOAD_BALANCE_KEY),
            group=url.parameters.get(config_constants.GROUP),
            version=url.parameters.get(config_constants.VERSION),
        )


class LoggerConfig(AbstractConfig):
    """
    Logger Configuration.
    """

    @dataclass
    class ConsoleConfig:
        """
        Console logger configuration.

        :param formatter: Console formatter.
        :type formatter: Optional[str]
        """

        formatter: Optional[str] = None

    @dataclass
    class FileConfig:
        """
        File logger configuration.

        :param file_formatter: File formatter.
        :type file_formatter: Optional[str]
        :param file_dir: File directory.
        :type file_dir: str
        :param file_name: File name.
        :type file_name: str
        :param rotate: File rotate type.
        :type rotate: logger_constants.FileRotateType
        :param backup_count: Backup count.
        :type backup_count: int
        :param max_bytes: Max bytes.
        :type max_bytes: int
        :param interval: Interval.
        :type interval: int
        """

        file_formatter: Optional[str] = None
        file_dir: str = logger_constants.DEFAULT_FILE_DIR_VALUE
        file_name: str = logger_constants.DEFAULT_FILE_NAME_VALUE
        rotate: logger_constants.FileRotateType = logger_constants.FileRotateType.NONE
        backup_count: int = logger_constants.DEFAULT_FILE_BACKUP_COUNT_VALUE
        max_bytes: int = logger_constants.DEFAULT_FILE_MAX_BYTES_VALUE
        interval: int = logger_constants.DEFAULT_FILE_INTERVAL_VALUE

    __slots__ = [
        "_level",
        "_global_formatter",
        "_console_enabled",
        "_console_config",
        "_file_enabled",
        "_file_config",
    ]

    def __init__(
        self,
        level: str = logger_constants.DEFAULT_LEVEL_VALUE,
        formatter: Optional[str] = None,
        console_enabled: bool = logger_constants.DEFAULT_CONSOLE_ENABLED_VALUE,
        file_enabled: bool = logger_constants.DEFAULT_FILE_ENABLED_VALUE,
    ):
        """
        Initialize the logger configuration.
        :param level: The logger level.
        :type level: str, default is "INFO".
        :param console_enabled: Whether to enable console logger.
        :type console_enabled: bool, default is True.
        :param file_enabled: Whether to enable file logger.
        """
        super().__init__()
        # logger level
        self._level = level.upper()

        # global formatter
        self._global_formatter = formatter

        # console logger
        self._console_enabled = console_enabled
        self._console_config = LoggerConfig.ConsoleConfig()

        # file logger
        self._file_enabled = file_enabled
        self._file_config = LoggerConfig.FileConfig()

    @property
    def level(self) -> str:
        """
        Get logger level.
        :return: The logger level.
        :rtype: str
        """
        return self._level

    @level.setter
    def level(self, level: str) -> None:
        """
        Set logger level.
        :param level: The logger level.
        :type level: str
        """
        if self._level != level.upper():
            self._level = level.upper()

    @property
    def global_formatter(self) -> Optional[str]:
        """
        Get global formatter.
        :return: The global formatter.
        :rtype: Optional[str]
        """
        return self._global_formatter

    def is_console_enabled(self) -> bool:
        """
        Check if console logger is enabled.
        :return: True if console logger is enabled, otherwise False.
        :rtype: bool
        """
        return self._console_enabled

    def enable_console(self) -> None:
        """
        Enable console logger.
        """
        self._console_enabled = True

    def disable_console(self) -> None:
        """
        Disable console logger.
        """
        self._console_enabled = False

    @property
    def console_config(self) -> ConsoleConfig:
        """
        Get console logger configuration.
        :return: Console logger configuration.
        :rtype: ConsoleConfig
        """
        return self._console_config

    def set_console(self, console_config: ConsoleConfig):
        """
        Set console logger configuration.
        :param console_config: Console logger configuration.
        :type console_config: ConsoleConfig
        """
        self._console_config = console_config

    def is_file_enabled(self) -> bool:
        """
        Check if file logger is enabled.
        :return: True if file logger is enabled, otherwise False.
        :rtype: bool
        """
        return self._file_enabled

    def enable_file(self) -> None:
        """
        Enable file logger.
        """
        self._file_enabled = True

    def disable_file(self) -> None:
        """
        Disable file logger.
        """
        self._file_enabled = False

    @property
    def file_config(self) -> FileConfig:
        """
        Get file logger configuration.
        :return: File logger configuration.
        :rtype: FileConfig
        """
        return self._file_config

    def set_file(self, file_config: FileConfig) -> None:
        """
        Set file logger configuration.
        :param file_config: File logger configuration.
        :type file_config: FileConfig
        """
        self._file_config = file_config
