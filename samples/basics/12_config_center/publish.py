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

# Writes to the configuration center what an operator, or a console such as
# Dubbo Admin, writes there. It uses kazoo, which the zookeeper extra
# installs, directly.
#
#   python publish.py config   the configuration that applications read at start
#   python publish.py rule     a rule that gives calls of the Greeter 3 seconds
#   python publish.py clear    removes both

import sys

from kazoo.client import KazooClient

# The entries are under /dubbo/config/{group}/{key}; the group is "dubbo".
CONFIG = "/dubbo/config/dubbo/dubbo.yaml"
RULE = "/dubbo/config/dubbo/org.apache.dubbo.samples.Greeter::.configurators"

SHARED_CONFIG = """\
# Configuration shared by every application that reads this center.
registries:
  zookeeper:
    address: zookeeper://127.0.0.1:2181
protocols:
  dubbo:
    port: 20880
provider:
  accesslog: true
"""

# A rule in the format of Dubbo's override rules, which Dubbo Java and Go read
# too. The parameters are those of URLs, so the timeout is in milliseconds.
TIMEOUT_RULE = """\
configVersion: v3.0
scope: service
key: org.apache.dubbo.samples.Greeter
enabled: true
configs:
  - side: consumer
    parameters:
      timeout: 3000
"""


def main(command: str) -> None:
    zookeeper = KazooClient("127.0.0.1:2181")
    zookeeper.start()
    try:
        if command == "config":
            write(zookeeper, CONFIG, SHARED_CONFIG)
        elif command == "rule":
            write(zookeeper, RULE, TIMEOUT_RULE)
        elif command == "clear":
            for path in (CONFIG, RULE):
                if zookeeper.exists(path):
                    zookeeper.delete(path)
            print("Cleared")
        else:
            raise SystemExit(f"unknown command {command!r}; use config, rule or clear")
    finally:
        zookeeper.stop()


def write(zookeeper: KazooClient, path: str, content: str) -> None:
    zookeeper.ensure_path(path)
    zookeeper.set(path, content.encode())
    print(f"Published {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
