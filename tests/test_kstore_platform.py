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

from dubbo_client import ZookeeperRegistry, DubboClient, DubboClientError, ApplicationConfig


if __name__ == '__main__':
    config = ApplicationConfig('test_rpclib')
    service_interface = 'com.qianmi.kstore.provider.CustomerAddressProvider'
    # 该对象较重，有zookeeper的连接，需要保存使用
    registry = ZookeeperRegistry('zookeeper:2181', config)
    # registry = MulticastRegistry('224.5.6.7:1234', config)
    user_provider = DubboClient(service_interface, registry, version='1.0')
    for i in range(1000):
        try:
            print user_provider.findAddressByCustomerId(1)
            # print user_provider.save(1, 3)

        except DubboClientError, client_error:
            print client_error.message
            print client_error.data
        time.sleep(5)
