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

from dubbo.url import URL, create_url


class TestUrl(unittest.TestCase):

    def test_str_to_url(self):
        url_0 = create_url(
            "http://www.facebook.com/friends?param1=value1&param2=value2"
        )
        self.assertEqual("http", url_0.scheme)
        self.assertEqual("www.facebook.com", url_0.host)
        self.assertEqual(None, url_0.port)
        self.assertEqual("friends", url_0.path)
        self.assertEqual("value1", url_0.parameters["param1"])
        self.assertEqual("value2", url_0.parameters["param2"])

        url_1 = create_url("ftp://username:password@192.168.1.7:21/1/read.txt")
        self.assertEqual("ftp", url_1.scheme)
        self.assertEqual("username", url_1.username)
        self.assertEqual("password", url_1.password)
        self.assertEqual("192.168.1.7", url_1.host)
        self.assertEqual(21, url_1.port)
        self.assertEqual("192.168.1.7:21", url_1.location)
        self.assertEqual("1/read.txt", url_1.path)

        url_2 = create_url("file:///home/user1/router.js?type=script")
        self.assertEqual("file", url_2.scheme)
        self.assertEqual("home/user1/router.js", url_2.path)

        url_3 = create_url(
            "http%3A//www.facebook.com/friends%3Fparam1%3Dvalue1%26param2%3Dvalue2",
            encoded=True,
        )
        self.assertEqual("http", url_3.scheme)
        self.assertEqual("www.facebook.com", url_3.host)
        self.assertEqual(None, url_3.port)
        self.assertEqual("friends", url_3.path)
        self.assertEqual("value1", url_3.parameters["param1"])
        self.assertEqual("value2", url_3.parameters["param2"])

    def test_url_to_str(self):
        url_0 = URL(
            scheme="tri",
            host="127.0.0.1",
            port=12,
            username="username",
            password="password",
            path="path",
            parameters={"type": "a"},
        )
        self.assertEqual(
            "tri://username:password@127.0.0.1:12/path?type=a", url_0.to_str()
        )

        url_1 = URL(
            scheme="tri",
            host="127.0.0.1",
            port=12,
            path="path",
            parameters={"type": "a"},
        )
        self.assertEqual("tri://127.0.0.1:12/path?type=a", url_1.to_str())

        url_2 = URL(scheme="tri", host="127.0.0.1", port=12, parameters={"type": "a"})
        self.assertEqual("tri://127.0.0.1:12?type=a", url_2.to_str())
