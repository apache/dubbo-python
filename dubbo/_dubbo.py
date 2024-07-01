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
import threading
from typing import Dict, List

from dubbo.config import ApplicationConfig, ConsumerConfig, LoggerConfig, ProtocolConfig
from dubbo.logger.logger_factory import loggerFactory

logger = loggerFactory.get_logger(__name__)


class Dubbo:

    # class variable
    _instance = None
    _ins_lock = threading.Lock()

    # instance variable
    # common
    _application: ApplicationConfig
    _protocols: Dict[str, ProtocolConfig]
    _logger: LoggerConfig
    # consumer
    _consumer: ConsumerConfig
    # provider
    # ....

    __slots__ = ["_application", "_protocols", "_logger", "_consumer"]

    def __new__(cls, *args, **kwargs):
        # dubbo object is singleton
        if cls._instance is None:
            with cls._ins_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # common
        self._application = ApplicationConfig.default_config()
        self._protocols = {}
        self._logger = LoggerConfig.default_config()
        # consumer
        self._consumer = ConsumerConfig.default_config()
        # provider
        # TODO add provider config

    # @overload
    # def new_client(
    #     self, reference: str, consumer: Optional[ConsumerConfig] = None
    # ) -> Client: ...
    #
    # @overload
    # def new_client(
    #     self,
    #     reference: ReferenceConfig,
    #     consumer: Optional[ConsumerConfig] = None,
    # ) -> Client: ...
    #
    # def new_client(
    #     self,
    #     reference: Union[str, ReferenceConfig],
    #     consumer: Optional[ConsumerConfig] = None,
    # ) -> Client:
    #     """
    #     Create a new client
    #     Args:
    #         reference: reference value
    #         consumer: consumer config
    #     Returns:
    #         Client: A new instance of Client
    #     """
    #     if isinstance(reference, str):
    #         reference = ReferenceConfig()
    #     elif isinstance(reference, ReferenceConfig):
    #         reference = reference
    #     else:
    #         raise TypeError(
    #             "reference must be a string or an instance of ReferenceConfig"
    #         )
    #     consumer_config = consumer or self._consumer.clone()
    #     return Client(reference, consumer_config)

    def new_server(self):
        """
        Create a new server
        """
        pass

    def _init(self):
        pass

    def start(self):
        pass

    def destroy(self):
        pass

    def with_application(self, application_config: ApplicationConfig) -> "Dubbo":
        """
        Set application config
        Args:
            application_config: new application config
        Returns:
            self: Dubbo instance
        """
        if application_config is None or not isinstance(
            application_config, ApplicationConfig
        ):
            raise ValueError("application must be an instance of ApplicationConfig")
        self._application = application_config
        return self

    def with_protocol(self, protocol_config: ProtocolConfig) -> "Dubbo":
        """
        Set protocol config
        Args:
            protocol_config: new protocol config
        Returns:
            self: Dubbo instance
        """
        if protocol_config is None or not isinstance(protocol_config, ProtocolConfig):
            raise ValueError("protocol must be an instance of ProtocolConfig")
        self._protocols[protocol_config.name] = protocol_config
        return self

    def with_protocols(self, protocol_configs: List[ProtocolConfig]) -> "Dubbo":
        """
        Set protocol config
        Args:
            protocol_configs: new protocol configs
        Returns:
            self: Dubbo instance
        """
        for protocol_config in protocol_configs:
            self.with_protocol(protocol_config)
        return self

    def with_logger(self, logger_config: LoggerConfig) -> "Dubbo":
        """
        Set logger config
        Args:
            logger_config: new logger config
        Returns:
            self: Dubbo instance
        """
        if logger_config is None or not isinstance(logger_config, LoggerConfig):
            raise ValueError("logger must be an instance of LoggerConfig")
        self._logger = logger_config
        return self

    def with_consumer(self, consumer_config: ConsumerConfig) -> "Dubbo":
        """
        Set consumer config
        Args:
            consumer_config: new consumer config
        Returns:
            self: Dubbo instance
        """
        if consumer_config is None or not isinstance(consumer_config, ConsumerConfig):
            raise ValueError("consumer must be an instance of ConsumerConfig")
        self._consumer = consumer_config
        return self
