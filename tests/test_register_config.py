# coding=utf-8

"""
 Licensed to the Apache Software Foundation (ASF) under one or more
 contributor license agreements.  See the NOTICE file distributed with
 this work for additional information regarding copyright ownership.
 The ASF licenses this file to You under the Apache License, Version 2.0
 (the "License"); you may not use this file except in compliance with
 the License.  You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.

"""
import time

from dubbo_client import ApplicationConfig
from dubbo_client import DubboClient, DubboClientError
from dubbo_client import ZookeeperRegistry


def test_config_init():
    config = ApplicationConfig('test_register_config')
    service_interface = 'com.ofpay.demo.api.UserProvider'
    registry = ZookeeperRegistry('172.19.66.49:2181', config)
    user_provider = DubboClient(service_interface, registry, version='1.0.0')
    for i in range(10000):
        try:
            print user_provider.findOne()
        except DubboClientError, client_error:
            print client_error
        time.sleep(1)

if __name__ == '__main__':
    test_config_init()
