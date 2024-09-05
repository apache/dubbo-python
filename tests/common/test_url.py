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

from dubbo.url import URL, create_url


def test_str_to_url():
    url_0 = create_url("http://www.facebook.com/friends?param1=value1&param2=value2")
    assert url_0.scheme == "http"
    assert url_0.host == "www.facebook.com"
    assert url_0.port is None
    assert url_0.path == "friends"
    assert url_0.parameters["param1"] == "value1"
    assert url_0.parameters["param2"] == "value2"

    url_1 = create_url("ftp://username:password@192.168.1.7:21/1/read.txt")
    assert url_1.scheme == "ftp"
    assert url_1.username == "username"
    assert url_1.password == "password"
    assert url_1.host == "192.168.1.7"
    assert url_1.port == 21
    assert url_1.location == "192.168.1.7:21"
    assert url_1.path == "1/read.txt"

    url_2 = create_url("file:///home/user1/router.js?type=script")
    assert url_2.scheme == "file"
    assert url_2.path == "home/user1/router.js"

    url_3 = create_url(
        "http%3A//www.facebook.com/friends%3Fparam1%3Dvalue1%26param2%3Dvalue2",
        encoded=True,
    )
    assert url_3.scheme == "http"
    assert url_3.host == "www.facebook.com"
    assert url_3.port is None
    assert url_3.path == "friends"
    assert url_3.parameters["param1"] == "value1"
    assert url_3.parameters["param2"] == "value2"


def test_url_to_str():
    url_0 = URL(
        scheme="tri",
        host="127.0.0.1",
        port=12,
        username="username",
        password="password",
        path="path",
        parameters={"type": "a"},
    )
    assert url_0.to_str() == "tri://username:password@127.0.0.1:12/path?type=a"

    url_1 = URL(
        scheme="tri",
        host="127.0.0.1",
        port=12,
        path="path",
        parameters={"type": "a"},
    )
    assert url_1.to_str() == "tri://127.0.0.1:12/path?type=a"

    url_2 = URL(scheme="tri", host="127.0.0.1", port=12, parameters={"type": "a"})
    assert url_2.to_str() == "tri://127.0.0.1:12?type=a"
