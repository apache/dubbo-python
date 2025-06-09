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

import dubbo

from nacos import NacosClient
from nacos.timer import NacosTimer, NacosTimerManager

from dubbo.constants import common_constants, registry_constants
from dubbo.registry import NotifyListener, Registry, RegistryFactory
from dubbo.url import URL
from dubbo.loggers import loggerFactory

_LOGGER = loggerFactory.get_logger()

DEFAULT_APPLICATION = "DEFAULT"


class NacosSubscriber:
    """
    Nacos instance subscriber
    """

    def __init__(
        self, nacos_client: NacosClient, service_name: str, listener: NotifyListener
    ):
        self._nacos_client = nacos_client
        self._service_name = service_name
        self._listener = listener
        self._timer_manager = NacosTimerManager()
        self._subscribed = False

    def refresh_instances(self):
        """
        Refresh nacos instances
        """
        if not self._subscribed:
            return

        try:
            instances = self._nacos_client.list_naming_instance(self._service_name)
            hosts = instances["hosts"]
            urls = [
                URL(scheme="tri", host=h["ip"], port=h["port"])
                for h in hosts
                if h["enabled"]
            ]
            self._listener.notify(urls=urls)
        except Exception as e:
            _LOGGER.error("nacos subscriber refresh_instance failed: %s", e)

    def subscribe(self):
        """
        Start timer to watch instances
        """
        if not self._timer_manager.all_timers().get("refresh_instances"):
            self._timer_manager.add_timer(
                NacosTimer("refresh_instances", self.refresh_instances, interval=7)
            )
            self._timer_manager.execute()
        self._subscribed = True
        self.refresh_instances()

    def unsubscribe(self):
        self._subscribed = False


def _init_nacos_client(url: URL) -> NacosClient:
    server_address = f"{url.host}:{url.port if url.port else 8848}"
    parameters = url.parameters

    endpoint = parameters.get("endpoint")
    namespace = parameters.get(registry_constants.NAMESPACE_KEY)
    username = url.username
    password = url.password

    return NacosClient(
        server_addresses=server_address,
        endpoint=endpoint,
        namespace=namespace,
        username=username,
        password=password,
    )


def _build_nacos_service_name(url: URL):
    service_name = url.parameters.get(common_constants.SERVICE_KEY)
    return f"providers:{service_name}::"


class NacosRegistry(Registry):

    def __init__(self, url: URL):
        self._url = url
        self._nacos_client: NacosClient = _init_nacos_client(url)
        self._service_subscriber_mapping = {}

    def _service_subscriber(
        self, service_name: str, listener: NotifyListener
    ) -> NacosSubscriber:
        if service_name not in self._service_subscriber_mapping:
            self._service_subscriber_mapping[service_name] = NacosSubscriber(
                self._nacos_client, service_name=service_name, listener=listener
            )

        return self._service_subscriber_mapping[service_name]

    def register(self, url: URL) -> None:
        ip = url.host
        port = url.port

        nacos_service_name = _build_nacos_service_name(url)

        metadata = {
            "side": "provider",
            "release": f"{dubbo.__version__}_py",
            "protocol": "tri",
            "application": DEFAULT_APPLICATION,
            "category": "providers",
            "enabled": "true",
            "disabled": "false",
        }
        self._nacos_client.add_naming_instance(
            nacos_service_name,
            ip,
            port,
            DEFAULT_APPLICATION,
            metadata=metadata,
            heartbeat_interval=1,
        )

    def unregister(self, url: URL) -> None:
        ip = url.host
        port = url.port
        nacos_service_name = _build_nacos_service_name(url)

        self._nacos_client.remove_naming_instance(
            nacos_service_name, ip=ip, port=port, cluster_name=DEFAULT_APPLICATION
        )

    def subscribe(self, url: URL, listener: NotifyListener) -> None:
        nacos_service_name = _build_nacos_service_name(url)

        subscriber = self._service_subscriber(nacos_service_name, listener)
        subscriber.subscribe()

    def unsubscribe(self, url: URL, listener: NotifyListener) -> None:
        nacos_service_name = _build_nacos_service_name(url)

        subscriber = self._service_subscriber(nacos_service_name, listener)
        subscriber.unsubscribe()
        listener.notify([])

    def lookup(self, url: URL):
        pass

    def get_url(self) -> URL:
        return self._url

    def is_available(self) -> bool:
        return self._nacos_client is not None

    def destroy(self) -> None:
        pass


class NacosRegistryFactory(RegistryFactory):

    def get_registry(self, url: URL) -> Registry:
        return NacosRegistry(url)
