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

import sys
import types
from pathlib import Path

import pytest
from google.protobuf import descriptor_pb2, wrappers_pb2
from google.protobuf.compiler.plugin_pb2 import CodeGeneratorRequest

from dubbo.protoc import generate
from dubbo.rpc.definition import RpcType, get_contract_methods, get_definition

STRING = ".google.protobuf.StringValue"


GOLDEN = Path(__file__).with_name("data").joinpath("greeter_v1_dubbo.py.txt").read_text()


def _request(*methods: dict[str, object]) -> CodeGeneratorRequest:
    wrappers = descriptor_pb2.FileDescriptorProto()
    wrappers_pb2.DESCRIPTOR.CopyToProto(wrappers)
    greeter = descriptor_pb2.FileDescriptorProto(
        name="demo/greeter-v1.proto", package="demo", dependency=["google/protobuf/wrappers.proto"]
    )
    greeter.message_type.add(name="Outer").nested_type.add(name="Inner")
    service = greeter.service.add(name="Greeter")
    for method in methods:
        service.method.add(**method)
    greeter.service.add(name="Empty")
    greeter.source_code_info.location.add(path=[6, 0], leading_comments=" Greets people.\n")
    greeter.source_code_info.location.add(
        path=[6, 0, 2, 0], leading_comments=' Says hello.\n\n Says it "twice": \\ """ .\n'
    )
    return CodeGeneratorRequest(file_to_generate=[greeter.name], proto_file=[wrappers, greeter])


METHODS = (
    {"name": "SayHello", "input_type": STRING, "output_type": ".demo.Outer.Inner"},
    {"name": "LotsOfReplies", "input_type": STRING, "output_type": STRING, "server_streaming": True},
    {"name": "LotsOfGreetings", "input_type": STRING, "output_type": STRING, "client_streaming": True},
    {
        "name": "BidiHello",
        "input_type": STRING,
        "output_type": STRING,
        "client_streaming": True,
        "server_streaming": True,
    },
    {"name": "GetHTTPStatus", "input_type": STRING, "output_type": STRING},
    {"name": "Import", "input_type": STRING, "output_type": STRING},
)


def test_a_service_becomes_a_contract_with_python_names_and_the_pb2_messages():
    response = generate(_request(*METHODS))

    assert not response.error
    assert [(file.name, file.content) for file in response.file] == [("demo/greeter_v1_dubbo.py", GOLDEN)]


def test_the_generated_contract_defines_the_service(monkeypatch):
    module = types.ModuleType("demo.greeter_v1_pb2")
    module.Outer = type("Outer", (), {"Inner": wrappers_pb2.StringValue})
    package = types.ModuleType("demo")
    package.greeter_v1_pb2 = module
    monkeypatch.setitem(sys.modules, "demo", package)
    monkeypatch.setitem(sys.modules, "demo.greeter_v1_pb2", module)
    namespace: dict[str, object] = {}

    exec(generate(_request(*METHODS)).file[0].content, namespace)

    definition = get_definition(namespace["Greeter"])
    assert definition.interface == "demo.Greeter"
    assert [(method.name, method.rpc_type) for method in definition.methods] == [
        ("SayHello", RpcType.UNARY),
        ("LotsOfReplies", RpcType.SERVER_STREAM),
        ("LotsOfGreetings", RpcType.CLIENT_STREAM),
        ("BidiHello", RpcType.BIDI_STREAM),
        ("GetHTTPStatus", RpcType.UNARY),
        ("Import", RpcType.UNARY),
    ]
    assert list(get_contract_methods(namespace["Greeter"]))[-1] == "import_"
    assert get_definition(namespace["GreeterServicer"]) == definition
    assert definition.method("SayHello").response is wrappers_pb2.StringValue


def test_a_message_named_with_a_keyword_and_a_comment_ending_in_a_quote_generate_valid_python():
    request = _request({"name": "Echo", "input_type": ".demo.Outer.class", "output_type": ".demo.class"})
    greeter = request.proto_file[1]
    greeter.message_type[0].nested_type.add(name="class")
    greeter.message_type.add(name="class")
    greeter.source_code_info.location.add(path=[6, 0, 2, 0], leading_comments=' Returns "ready"\n')

    content = generate(request).file[0].content

    compile(content, "demo/greeter_v1_dubbo.py", "exec")
    assert 'getattr(getattr(greeter_v1_pb2, "Outer"), "class")' not in content
    assert 'getattr(greeter_v1_pb2.Outer, "class")' in content
    assert 'getattr(greeter_v1_pb2, "class")' in content
    assert '"""Returns "ready\\""""' in content


def test_pb2_modules_with_the_same_basename_keep_their_message_types_distinct(monkeypatch):
    generated = _request({"name": "Copy", "input_type": STRING, "output_type": ".other.Value"})
    other = descriptor_pb2.FileDescriptorProto(name="other/wrappers.proto", package="other")
    other.message_type.add(name="Value")
    generated.proto_file.insert(0, other)
    module = types.ModuleType("other.wrappers_pb2")
    module.Value = wrappers_pb2.Int64Value
    package = types.ModuleType("other")
    package.wrappers_pb2 = module
    monkeypatch.setitem(sys.modules, "other", package)
    monkeypatch.setitem(sys.modules, "other.wrappers_pb2", module)
    namespace = {}

    exec(generate(generated).file[0].content, namespace)
    method = get_definition(namespace["Greeter"]).method("Copy")

    assert method.request[0].type is wrappers_pb2.StringValue
    assert method.response is wrappers_pb2.Int64Value


@pytest.mark.parametrize(
    ("names", "error"),
    [
        (["GetUser", "get_user"], "methods of Greeter share the Python name 'get_user'"),
        (["_Hidden"], "method Greeter._Hidden would be private in Python"),
        (["Dubbo"], "method Greeter.Dubbo would hide the imported name 'dubbo'"),
        (["Wrappers_pb2"], "method Greeter.Wrappers_pb2 would hide the imported name 'wrappers_pb2'"),
    ],
)
def test_a_service_that_cannot_be_a_contract_sets_the_error(names, error):
    response = generate(_request(*({"name": name, "input_type": STRING, "output_type": STRING} for name in names)))

    assert response.error == f"demo/greeter-v1.proto: {error}"
    assert not response.file


def test_a_service_named_as_an_import_sets_the_error():
    request = _request({"name": "SayHello", "input_type": STRING, "output_type": STRING})
    request.proto_file[1].service[0].name = "typing"

    assert generate(request).error == "demo/greeter-v1.proto: a contract would hide the imported name 'typing'"


def test_a_file_named_with_dots_generates_beside_its_pb2_module():
    request = _request({"name": "SayHello", "input_type": STRING, "output_type": STRING})
    request.proto_file[1].name = request.file_to_generate[0] = "demo/greeter.v1.proto"

    assert [file.name for file in generate(request).file] == ["demo/greeter/v1_dubbo.py"]
