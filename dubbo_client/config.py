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




class ApplicationConfig(object):
    # 应用名称
    name = 'default'
    # 模块版本
    version = '1.0.0'
    # 应用负责人
    owner = ''
    # 组织名(BU或部门)
    organization = ''
    # 分层
    architecture = 'web'
    # 环境，如：dev/test/run
    environment = 'run'

    def __init__(self, name, **kwargs):
        self.name = name
        object_property = dir(ApplicationConfig)
        for key, value in kwargs.items():
            if key in object_property:
                setattr(self, key, value)

    def __str__(self):
        return 'ApplicationConfig is {0}'.format(",".join(k + ':' + v for k, v in vars(self).iteritems()))


class ReferenceConfig(object):
    registry = None
    interface = ''
    version = ''


if __name__ == '__main__':
    application_config = ApplicationConfig('test_app', version='2.0.0', owner='caozupeng', error='ssd')
    print application_config
