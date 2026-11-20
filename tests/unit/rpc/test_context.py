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

import pytest
from multidict import MultiDict

import dubbo
from dubbo.rpc.context import attachments_to_send, record_response, serving


def test_incoming_outside_a_handler() -> None:
    with pytest.raises(LookupError, match="only while a service handler runs"):
        dubbo.incoming()


def test_outgoing_blocks_nest() -> None:
    with dubbo.outgoing({"a": "1", "b": "1"}):
        with dubbo.outgoing({"b": "2"}) as inner:
            assert dict(inner.attachments) == {"a": "1", "b": "2"}
        with dubbo.outgoing({"c": "3"}, inherit=False) as fresh:
            assert dict(fresh.attachments) == {"c": "3"}


def test_outgoing_keeps_repeated_values_and_replaces_them_by_key() -> None:
    with dubbo.outgoing(MultiDict([("tag", "a"), ("tag", "b"), ("user", "u")])):
        with dubbo.outgoing() as inherited:
            assert inherited.attachments.getall("tag") == ["a", "b"]
        with dubbo.outgoing({"tag": "c"}) as inner:
            assert list(inner.attachments.items()) == [("tag", "c"), ("user", "u")]


def test_serving_preserves_received_attachments_but_does_not_forward_credentials_or_routing():
    received = {
        "tenant": "t1",
        "token": "secret",
        "timeout": "3000",
        "_TO": "3000",
        "dubbo.tag": "gray",
        "Authorization": "Bearer x",
        "cookie": "c",
    }

    with serving(received, peer=None):
        assert dict(dubbo.incoming().attachments) == received
        assert dict(attachments_to_send()) == {"tenant": "t1"}
        with dubbo.outgoing({"token": "own"}):
            assert dict(attachments_to_send()) == {"tenant": "t1", "token": "own"}


@pytest.mark.parametrize(
    ("additions", "inherit", "expected"),
    [
        ({}, True, {"tenant": "t1", "operator": "alice"}),
        ({"hop": "middle", "tenant": "t2"}, True, {"tenant": "t2", "operator": "alice", "hop": "middle"}),
        ({"key": "x"}, False, {"key": "x"}),
    ],
    ids=["forward", "override", "cut-inheritance"],
)
def test_calls_inherit_the_served_attachments_unless_their_block_starts_fresh(additions, inherit, expected):
    with serving({"tenant": "t1", "operator": "alice"}, peer=None), dubbo.outgoing(additions, inherit=inherit):
        assert dict(attachments_to_send()) == expected


def test_serving_uses_the_received_attachments_and_restores_the_callers_block():
    with dubbo.outgoing({"tenant": "caller"}):
        with serving({"tenant": "served", "filtered": "yes"}, peer=None):
            assert dict(attachments_to_send()) == {"tenant": "served", "filtered": "yes"}

        assert dict(attachments_to_send()) == {"tenant": "caller"}


def test_response_attachments_belong_to_the_innermost_calling_block():
    with dubbo.outgoing() as caller:
        with serving({}, peer=None):
            with dubbo.outgoing({"key": "x"}, inherit=False) as downstream:
                record_response({"from": "downstream"})
            record_response({"must-not": "leak-to-caller"})
            assert dict(caller.response_attachments) == {}
        record_response({"from": "middle"})

    assert (dict(caller.response_attachments), dict(downstream.response_attachments)) == (
        {"from": "middle"},
        {"from": "downstream"},
    )
