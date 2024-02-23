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

from urlparse import urlparse, parse_qsl


class ServiceURL(object):
    protocol = 'jsonrpc'
    interface = ''
    location = ''  # ip+port
    path = ''  # like /com.qianmi.dubbo.UserProvider
    ip = '127.0.0.1'
    port = '9090'
    version = ''
    group = ''
    disabled = False
    weight = 100
    has_disable_value = False
    has_weight_value = False

    def __init__(self, url):
        result = urlparse(url)
        self.protocol = result[0]
        self.location = result[1]
        self.path = result[2]
        if self.location.find(':') > -1:
            self.ip, self.port = result[1].split(':')
        params = parse_qsl(result[4])
        for key, value in params:
            # url has a default.timeout property, but it can not add in python object
            # so keep the last one
            pos = key.find('.')
            if pos > -1:
                key = key[pos + 1:]
            # print key
            if key == 'disabled':
                value = value.lower() == 'true' if value else False
                self.has_disable_value = True
            elif key == 'weight':
                value = int(value) if value else 100
                self.has_weight_value = True
            self.__dict__[key] = value

    def __repr__(self):
        return str(self.__dict__)

    def init_default_config(self):
        """
        恢复默认设置，dubbo配置是覆盖形式，如果恢复默认值，那么configurators下的配置会被清空
        :return:
        """
        self.disabled = False
        self.weight = 100

    def set_config(self, url_list):
        """
        设置自定义dubbo配置
        :param url_list:
        :return:
        """
        if not url_list:
            return

        param_list = []
        for configuration_url in url_list:
            result = urlparse(configuration_url)
            params = parse_qsl(result[4])
            param_list.extend(params)
        has_disable_value = False
        has_weight_value = False
        for key, value in param_list:
            if key == 'disabled':
                self.disabled = value.lower() == 'true' if value else False
                has_disable_value = True
            if key == 'weight':
                self.weight = int(value) if value else 100
                has_weight_value = True

        if not has_disable_value:
            self.disabled = False
        if not has_weight_value:
            self.weight = 100
