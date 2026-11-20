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

# Writes or removes routing rules in the configuration center, as an operator,
# or a console such as Dubbo Admin, would.
#
#   python publish.py tag         tags the instance on port 20881 "canary"
#   python publish.py condition   sends the calls for Alice to stable-1 only
#   python publish.py clear       removes both rules

import sys

from kazoo.client import KazooClient

# The tag rule of the provider application, under
# /dubbo/config/dubbo/{application}.tag-router. It tags instances by address,
# while they run, without changing their configuration.
TAG_RULE = "/dubbo/config/dubbo/routing-server.tag-router"
TAGS = """\
configVersion: v3.0
key: routing-server
enabled: true
force: false
tags:
  - name: canary
    addresses: ["127.0.0.1:20881"]
"""

# The condition rule of one service, under
# /dubbo/config/dubbo/{service}:{version}:{group}.condition-router. Each
# condition reads "which calls => which providers".
CONDITION_RULE = "/dubbo/config/dubbo/org.apache.dubbo.samples.Greeter::.condition-router"
CONDITIONS = """\
configVersion: v3.0
scope: service
key: org.apache.dubbo.samples.Greeter
enabled: true
force: true
conditions:
  - arguments[0] = Alice => port = 20880
"""


def main(command: str) -> None:
    zookeeper = KazooClient("127.0.0.1:2181")
    zookeeper.start()
    try:
        if command == "tag":
            write(zookeeper, TAG_RULE, TAGS)
        elif command == "condition":
            write(zookeeper, CONDITION_RULE, CONDITIONS)
        elif command == "clear":
            for path in (TAG_RULE, CONDITION_RULE):
                if zookeeper.exists(path):
                    zookeeper.delete(path)
            print("Cleared")
        else:
            raise SystemExit(f"unknown command {command!r}; use tag, condition or clear")
    finally:
        zookeeper.stop()


def write(zookeeper: KazooClient, path: str, content: str) -> None:
    zookeeper.ensure_path(path)
    zookeeper.set(path, content.encode())
    print(f"Published {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
