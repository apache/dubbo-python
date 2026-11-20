# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

# Shows what the servers have registered in ZooKeeper, in both ways Dubbo
# registers. It reads ZooKeeper directly with kazoo, which the zookeeper extra
# installs, and changes nothing.

from urllib.parse import unquote

from kazoo.client import KazooClient

SERVICE = "org.apache.dubbo.samples.Greeter"
APPLICATION = "registry-server"


def children(zookeeper: KazooClient, path: str) -> list[str]:
    return sorted(zookeeper.get_children(path)) if zookeeper.exists(path) else []


def main() -> None:
    zookeeper = KazooClient("127.0.0.1:2181")
    zookeeper.start()
    try:
        # Interface level, as Dubbo 2 discovers: one URL per service and
        # provider, under the name of the service.
        print(f"Providers of {SERVICE}, registered per service:")
        for url in children(zookeeper, f"/dubbo/{SERVICE}/providers"):
            print("  ", unquote(url).split("?")[0])

        # Application level, as Dubbo 3 discovers: one node per instance of
        # the application, and a mapping from each service to the
        # applications that provide it.
        print(f"Instances of {APPLICATION}, registered per application:")
        for instance in children(zookeeper, f"/services/{APPLICATION}"):
            print("  ", instance)
        mapping = f"/dubbo/mapping/{SERVICE}"
        if zookeeper.exists(mapping):
            print(f"Applications that provide {SERVICE}:", zookeeper.get(mapping)[0].decode())
    finally:
        zookeeper.stop()


if __name__ == "__main__":
    main()
