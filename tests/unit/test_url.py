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

import attrs
import pytest

from dubbo import URL
from dubbo.extension import ApplicationScope
from dubbo.url import APPLICATION_SCOPE
from dubbo.utils.converters import comma_separated, milliseconds


def test_components_are_decoded_and_round_trip() -> None:
    url = URL.parse(
        "TRI://us%40er:p%3Aa%2Bss@LOCALHOST:50051/example.Greeter"
        "?tag=a&timeout=3000&tag=b&empty=&bare&token=a%2Bb+c%26d%3D%25"
    )

    assert (url.protocol, url.host, url.port, url.path) == ("tri", "localhost", 50051, "example.Greeter")
    assert (url.username, url.password) == ("us@er", "p:a+ss")
    # A repeated key keeps its last value, in the position of its first.
    assert list(url.parameters.items()) == [
        ("tag", "b"),
        ("timeout", "3000"),
        ("empty", ""),
        ("bare", ""),
        ("token", "a+b c&d=%"),
    ]
    assert URL.parse(url.render_as_string(hide_secrets=False)) == url


def test_password_is_hidden_unless_rendered_on_request() -> None:
    url = URL.parse("nacos://user:p%3Ass@host:8848")

    assert "p:ss" not in repr(url)
    assert str(url) == url.render_as_string() == "nacos://user:***@host:8848"
    assert url.render_as_string(hide_secrets=False) == "nacos://user:p%3Ass@host:8848"


def test_secret_parameters_are_hidden_unless_rendered_on_request() -> None:
    url = URL.parse("nacos://host:8848?token=t0k&accessKey=ak&secretKey=sk&group=a")

    assert str(url) == "nacos://host:8848?token=%2A%2A%2A&accessKey=%2A%2A%2A&secretKey=%2A%2A%2A&group=a"
    assert not {"t0k", "ak", "sk"} & set(repr(url).replace("'", " ").split())
    assert url.parameters["token"] == "t0k"
    assert "token=t0k" in url.render_as_string(hide_secrets=False)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("zookeeper://alice:hunter2@host/#fragment", "fragments", id="fragment"),
        pytest.param("nacos://alice:hunter2@bad\uff03host:8848", "invalid host", id="host-under-nfkc"),
    ],
)
def test_rejected_text_is_not_echoed(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message) as caught:
        URL.parse(text)

    assert "hunter2" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_render_escapes_what_the_components_hold() -> None:
    url = URL(protocol="tri", host="2001:DB8::1", port=50051, path="中文 空格/x?y#z", parameters={"中文": "a+b &c"})

    assert url.host == "2001:db8::1"
    assert str(url) == (
        "tri://[2001:db8::1]:50051/%E4%B8%AD%E6%96%87%20%E7%A9%BA%E6%A0%BC/x%3Fy%23z?%E4%B8%AD%E6%96%87=a%2Bb+%26c"
    )
    assert URL.parse(str(url)) == url


@pytest.mark.parametrize(
    "text",
    [
        "tri://192.168.1.6:50051/com.foo.HelloService?timeout=3000&group=a",
        "consumer://192.168.1.2/com.foo.HelloService?check=false",
        "empty://0.0.0.0/com.foo.HelloService?category=providers",
        "zookeeper://10.20.153.10:2181?backup=10.20.153.11:2181,10.20.153.12:2181",
        "nacos://user:secret@[::1]:8848/path",
        "file:///home/user1/router.js?type=script",
        "memory:center",
    ],
    ids=["provider", "consumer", "empty", "ensemble", "ipv6", "file", "opaque"],
)
def test_dubbo_url_forms_round_trip(text: str) -> None:
    url = URL.parse(text)

    assert URL.parse(url.render_as_string(hide_secrets=False)) == url


def test_parameters_are_a_read_only_copy_and_fields_are_frozen() -> None:
    source = {"tag": "a"}
    url = URL(protocol="tri", parameters=source)
    source["tag"] = "changed"

    assert url.parameters == {"tag": "a"}
    with pytest.raises(TypeError):
        url.parameters["tag"] = "changed"
    with pytest.raises(attrs.exceptions.FrozenInstanceError):
        url.path = "changed"


def test_update_parameters_adds_and_replaces_keys() -> None:
    url = URL.parse("tri://host/service?timeout=1000&group=a")

    updated = url.update_parameters({"timeout": "3000", "version": "1"})

    assert updated.parameters == {"timeout": "3000", "group": "a", "version": "1"}
    assert url.parameters == {"timeout": "1000", "group": "a"}


def test_urls_are_hashable_values_regardless_of_parameter_order() -> None:
    first = URL(protocol="tri", host="host", parameters={"a": "1", "b": "2"})
    second = URL(protocol="tri", host="host", parameters={"b": "2", "a": "1"})

    assert first == second
    assert {first: "value"}[second] == "value"
    assert first != first.update_parameters({"a": "changed"})


def test_nested_url_decodes_exactly_one_layer() -> None:
    inner = "tri://host/service?token=a%2Bb&timeout=1000"
    outer = URL(protocol="example", host="host", parameters={"target": inner})

    recovered = URL.parse(str(outer)).parameters["target"]

    assert recovered == inner
    assert URL.parse(recovered).parameters["token"] == "a+b"


def test_empty_host_is_no_host_and_whitespace_is_ignored() -> None:
    assert URL(protocol="file", host="", path="a").host is None
    assert URL.parse(" \ttri://host/service\r\n") == URL.parse("tri://host/service")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "needs a scheme"),
        ("host/path", "needs a scheme"),
        ("1tri://host", "scheme"),
        ("tri://host/path#fragment", "fragments"),
        ("tri://host:65536/", "[Pp]ort"),
        ("tri://host:no/", "[Pp]ort"),
        ("tri://%FF@host/", "utf-8"),
        ("tri://host/?x=%FF", "utf-8"),
        ("tri://:50051/", "require host"),
    ],
)
def test_invalid_text_is_rejected(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        URL.parse(text)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"protocol": ""}, "URL scheme"),
        ({"protocol": "bad scheme"}, "URL scheme"),
        ({"host": "host", "port": 65536}, "port must"),
        ({"port": 50051}, "require host"),
        ({"username": "user"}, "require host"),
        ({"host": "host", "password": "secret"}, "requires username"),
    ],
)
def test_invalid_fields_are_rejected(fields: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        URL(**{"protocol": "tri", **fields})


def test_get_parameter_converts_a_present_parameter_and_defaults_an_absent_one() -> None:
    url = URL.parse("tri://host/?timeout=3000&retries=2&backup=a:1,%20b:2,")

    assert url.get_parameter("timeout", milliseconds, 1.0) == 3.0
    assert url.get_parameter("retries", int, 0) == 2
    assert url.get_parameter("backup", comma_separated, ()) == ("a:1", "b:2")
    assert url.get_parameter("weight", float, None) is None


def test_get_parameter_names_the_key_of_a_rejected_value() -> None:
    url = URL.parse("tri://host/?timeout=fast")

    with pytest.raises(ValueError, match="'timeout': must be whole milliseconds, not 'fast'"):
        url.get_parameter("timeout", milliseconds, 1.0)


def test_the_scope_travels_with_derived_urls_outside_text_equality_and_repr() -> None:
    scope = ApplicationScope()
    url = URL.parse("zookeeper://zk:2181?group=a").replace(attributes={APPLICATION_SCOPE: scope})

    assert url.update_parameters({"group": "b"}).scope is scope
    assert url == URL.parse("zookeeper://zk:2181?group=a")
    assert hash(url) == hash(URL.parse("zookeeper://zk:2181?group=a"))
    assert str(url) == "zookeeper://zk:2181?group=a"
    assert "scope" not in repr(url)


def test_address_and_userinfo_join_their_components() -> None:
    assert URL.parse("zookeeper://user:p%40ss@[::1]:2181").address == "[::1]:2181"
    assert URL.parse("zookeeper://user:p%40ss@[::1]:2181").userinfo == "user:p@ss"
    assert URL.parse("zookeeper://user@zk").address == "zk"
    assert URL.parse("zookeeper://user@zk").userinfo == "user"
    assert URL.parse("zookeeper://zk:2181").userinfo is None
