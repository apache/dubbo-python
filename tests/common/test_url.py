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

import unittest
from dubbo.common import url as dubbo_url


class TestURL(unittest.TestCase):

    def test_parse_url_with_params(self):
        url = "registry://192.168.1.7:9090/org.apache.dubbo.service1?param1=value1&param2=value2"
        parsed = dubbo_url.parse_url(url)
        self.assertEqual(parsed.protocol, "registry")
        self.assertEqual(parsed.host, "192.168.1.7")
        self.assertEqual(parsed.port, 9090)
        self.assertEqual(parsed.path, "/org.apache.dubbo.service1")
        self.assertEqual(parsed.params, {"param1": "value1", "param2": "value2"})
        self.assertEqual(parsed.username, "")
        self.assertEqual(parsed.password, "")
        self.assertEqual(parsed.to_str(), url)

    def test_parse_url_with_auth(self):
        url = "http://username:password@10.20.130.230:8080/list?version=1.0.0"
        parsed = dubbo_url.parse_url(url)
        self.assertEqual(parsed.protocol, "http")
        self.assertEqual(parsed.host, "10.20.130.230")
        self.assertEqual(parsed.port, 8080)
        self.assertEqual(parsed.path, "/list")
        self.assertEqual(parsed.params, {"version": "1.0.0"})
        self.assertEqual(parsed.username, "username")
        self.assertEqual(parsed.password, "password")
        self.assertEqual(parsed.to_str(), url)

    def test_to_str_with_encoded(self):
        url = "http://username:password@10.20.130.230:8080/list?version=1.0.0"
        parsed = dubbo_url.parse_url(url)
        encoded_url = parsed.to_str(encoded=True)
        self.assertNotEqual(encoded_url, url)
        self.assertTrue('%3F' in encoded_url)

    def test_to_str_without_params(self):
        url = "http://www.example.com"
        parsed = dubbo_url.parse_url(url)
        self.assertEqual(parsed.protocol, "http")
        self.assertEqual(parsed.host, "www.example.com")
        self.assertEqual(parsed.path, "")
        self.assertEqual(parsed.params, {})
        self.assertEqual(parsed.username, "")
        self.assertEqual(parsed.password, "")
        self.assertEqual(parsed.to_str(), "http://www.example.com")

    def test_parse_url_encoded(self):
        encoded_url = "http%3A%2F%2Fwww.facebook.com%2Ffriends%3Fparam1%3Dvalue1%26param2%3Dvalue2"
        parsed = dubbo_url.parse_url(encoded_url, encoded=True)
        self.assertEqual(parsed.protocol, "http")
        self.assertEqual(parsed.host, "www.facebook.com")
        self.assertEqual(parsed.path, "/friends")
        self.assertEqual(parsed.params, {"param1": "value1", "param2": "value2"})
        self.assertEqual(parsed.username, "")
        self.assertEqual(parsed.password, "")
        self.assertEqual(parsed.to_str(), "http://www.facebook.com/friends?param1=value1&param2=value2")


if __name__ == '__main__':
    unittest.main()
