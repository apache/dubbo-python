# coding = utf-8
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
from pyjsonrpc import HttpClient


def test_client_every_new():
    user_provider = HttpClient(url="http://{0}{1}".format('zookeeper:38081/', 'com.ofpay.demo.api.UserProvider2'))
    print user_provider.getUser('A003')
    print user_provider.queryUser(
        {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
    print user_provider.queryAll()
    print user_provider.isLimit('MAN', 'Joe')
    print user_provider('getUser', 'A005')


if __name__ == '__main__':
    test_client_every_new()
