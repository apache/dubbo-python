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

"""The protoc plugin ``protoc-gen-python-dubbo``, which generates the Dubbo service contracts of proto files.

``protoc --python_out=. --pyi_out=. --python-dubbo_out=. greeter.proto``,
or ``python -m grpc_tools.protoc`` with the same options after installing
``apache-dubbo[protoc]``, writes ``greeter_dubbo.py`` beside ``greeter_pb2.py``. For each
service, named ``{package}.{Service}`` as in every language, it holds two
contracts: ``{Service}``, a ``typing.Protocol`` that callers refer to, and
``{Service}Servicer``, an abstract class that implementations subclass.
Their methods take Python names, such as ``say_hello`` for ``SayHello``,
and the message classes of the ``_pb2`` modules, imported by their
absolute names, as protoc names them.
"""

import keyword
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping

from google.protobuf.compiler.plugin_pb2 import CodeGeneratorRequest, CodeGeneratorResponse
from google.protobuf.descriptor_pb2 import FileDescriptorProto, MethodDescriptorProto, ServiceDescriptorProto

__all__ = ["generate", "main"]

# Returns the Python expression of a message class from its full name, as in ``.pkg.Message``.
_Reference = Callable[[str], str]
# Where a lowercase letter or digit meets an uppercase one, or an acronym meets the next word, as in GetHTTPStatus.
_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def main() -> None:
    """Read a ``CodeGeneratorRequest`` from standard input and write the ``CodeGeneratorResponse`` to standard output."""
    request = CodeGeneratorRequest.FromString(sys.stdin.buffer.read())
    sys.stdout.buffer.write(generate(request).SerializeToString())


def generate(request: CodeGeneratorRequest) -> CodeGeneratorResponse:
    """Return the ``_dubbo.py`` module of each file of ``request`` to generate that has services.

    A file whose services cannot become contracts, such as one whose
    methods share a Python name, sets the error of the response instead.
    """
    response = CodeGeneratorResponse(supported_features=CodeGeneratorResponse.FEATURE_PROTO3_OPTIONAL)
    files = {file.name: file for file in request.proto_file}
    messages = _messages(request.proto_file)
    for name in request.file_to_generate:
        file = files[name]
        if not file.service:
            continue
        try:
            content = _module(file, messages)
        except ValueError as error:
            response.error = f"{name}: {error}"
            return response
        module = _pb2_module(name).removesuffix("_pb2")
        response.file.add(name=module.replace(".", "/") + "_dubbo.py", content=content)

    return response


def _messages(files: Iterable[FileDescriptorProto]) -> dict[str, tuple[str, str]]:
    """Return the file and the Python name, such as ``Outer.Inner``, of each message by its full name, as in ``.pkg.Outer.Inner``."""
    messages = {}
    for file in files:
        prefix = f".{file.package}." if file.package else "."
        pending = [(message, message.name) for message in file.message_type]
        while pending:
            message, name = pending.pop()
            messages[prefix + name] = (file.name, name)
            pending.extend((nested, f"{name}.{nested.name}") for nested in message.nested_type)

    return messages


def _module(file: FileDescriptorProto, messages: Mapping[str, tuple[str, str]]) -> str:
    used = {
        _pb2_module(messages[name][0])
        for service in file.service
        for method in service.method
        for name in (method.input_type, method.output_type)
    }
    aliases = _aliases(used)
    # The names the module imports, which a contract or a method of the same name would hide.
    imported = {"abc", "typing", "dubbo", *aliases.values()}

    names = [name for service in file.service for name in (service.name, f"{service.name}Servicer")]
    if len(set(names)) < len(names):
        raise ValueError("the contracts of two services share a Python name")
    if hidden := sorted(imported.intersection(names)):
        raise ValueError(f"a contract would hide the imported name {hidden[0]!r}")
    exported = ", ".join(f'"{name}"' for name in names)

    def reference(name: str) -> str:
        proto, qualified = messages[name]
        expression = aliases[_pb2_module(proto)]
        for part in qualified.split("."):
            expression = f'getattr({expression}, "{part}")' if keyword.iskeyword(part) else f"{expression}.{part}"
        return expression

    comments = {tuple(location.path): location.leading_comments for location in file.source_code_info.location}
    lines = [
        "# Generated by protoc-gen-python-dubbo. DO NOT EDIT!",
        f"# source: {file.name}",
        f'"""Dubbo service contracts of {file.name}."""',
        "",
        "import abc",
        "import typing",
        "",
        "import dubbo",
        "",
    ]
    if aliases:
        lines += [*sorted(_import(module, alias) for module, alias in aliases.items()), ""]
    lines.append(f"__all__ = [{exported}]")
    for index, service in enumerate(file.service):
        lines += ["", "", *_contracts(file, index, service, comments, reference, imported)]

    return "\n".join(lines) + "\n"


def _pb2_module(proto: str) -> str:
    return proto.removesuffix(".proto").replace("-", "_").replace("/", ".") + "_pb2"


def _aliases(modules: Iterable[str]) -> dict[str, str]:
    """Return the name each ``_pb2`` module is imported as: its own, unless two modules share it."""
    modules = sorted(modules)
    counts = Counter(module.rpartition(".")[2] for module in modules)
    aliases = {}
    for module in modules:
        name = module.rpartition(".")[2]
        aliases[module] = name if counts[name] == 1 else module.replace("_", "__").replace(".", "_dot_")

    return aliases


def _import(module: str, alias: str) -> str:
    package, _, name = module.rpartition(".")
    statement = f"from {package} import {name}" if package else f"import {name}"
    return statement if alias == name else f"{statement} as {alias}"


def _contracts(
    file: FileDescriptorProto,
    index: int,
    service: ServiceDescriptorProto,
    comments: Mapping[tuple[int, ...], str],
    reference: _Reference,
    imported: set[str],
) -> list[str]:
    """Return the lines of the caller's contract of ``service``, then of its servicer."""
    path = (FileDescriptorProto.SERVICE_FIELD_NUMBER, index)
    interface = f"{file.package}.{service.name}" if file.package else service.name
    docstring = _docstring(comments.get(path), "    ")
    caller = [f'@dubbo.service("{interface}")', f"class {service.name}(typing.Protocol):", *docstring]
    servicer = [f'@dubbo.service("{interface}")', f"class {service.name}Servicer(abc.ABC):", *docstring]
    if not service.method and not docstring:
        caller.append("    ...")
        servicer.append("    ...")

    attributes: set[str] = set()
    for number, method in enumerate(service.method):
        attribute = _attribute(method.name)
        if attribute.startswith("_"):
            raise ValueError(f"method {service.name}.{method.name} would be private in Python")
        if attribute in attributes:
            raise ValueError(f"methods of {service.name} share the Python name {attribute!r}")
        if attribute in imported:
            raise ValueError(f"method {service.name}.{method.name} would hide the imported name {attribute!r}")
        attributes.add(attribute)

        comment = _docstring(comments.get((*path, ServiceDescriptorProto.METHOD_FIELD_NUMBER, number)), " " * 8)
        request, response = reference(method.input_type), reference(method.output_type)
        caller += ["", f'    @dubbo.method("{method.name}")']
        caller += _body(_signature(attribute, *_called(method, request, response)), comment)
        servicer += ["", f'    @dubbo.method("{method.name}")', "    @abc.abstractmethod"]
        servicer += _body(_signature(attribute, *_served(method, request, response)), comment)

    return [*caller, "", "", *servicer]


def _called(method: MethodDescriptorProto, request: str, response: str) -> tuple[str, list[str], str]:
    """Return the keyword, the parameters and the return type of ``method`` as callers hold it."""
    match method.client_streaming, method.server_streaming:
        case False, False:
            return "async def", ["self", f"request: {request}"], response
        case False, True:
            return "def", ["self", f"request: {request}"], f"dubbo.ServerStream[{response}]"
        case True, False:
            return "def", ["self"], f"dubbo.ClientStream[{request}, {response}]"
        case _:
            return "def", ["self"], f"dubbo.BidiStream[{request}, {response}]"


def _served(method: MethodDescriptorProto, request: str, response: str) -> tuple[str, list[str], str]:
    """Return the keyword, the parameters and the return type of ``method`` as implementations serve it."""
    match method.client_streaming, method.server_streaming:
        case False, False:
            return "async def", ["self", f"request: {request}"], response
        case False, True:
            return "async def", ["self", f"request: {request}", f"stream: dubbo.SendStream[{response}]"], "None"
        case True, False:
            return "async def", ["self", f"stream: dubbo.ReceiveStream[{request}]"], response
        case _:
            return "async def", ["self", f"stream: dubbo.Stream[{response}, {request}]"], "None"


def _signature(attribute: str, keyword: str, parameters: list[str], returns: str) -> str:
    return f"    {keyword} {attribute}({', '.join(parameters)}) -> {returns}:"


def _body(signature: str, docstring: list[str]) -> list[str]:
    return [signature, *docstring] if docstring else [f"{signature} ..."]


def _attribute(name: str) -> str:
    """Return the Python name of the method ``name``: in snake case, with ``_`` after a keyword."""
    attribute = _WORD_BOUNDARY.sub("_", name).lower()
    return f"{attribute}_" if keyword.iskeyword(attribute) else attribute


def _docstring(comment: str | None, indent: str) -> list[str]:
    """Return the lines of a docstring holding the proto comment ``comment``, if any."""
    if not comment or not comment.strip():
        return []

    text = comment.replace("\\", "\\\\").strip("\n").rstrip()
    if text.endswith('"'):
        text = text[:-1] + '\\"'
    text = text.replace('"""', '\\"\\"\\"')
    lines = [line.removeprefix(" ").rstrip() for line in text.split("\n")]
    if len(lines) == 1:
        return [f'{indent}"""{lines[0].strip()}"""']
    return [
        f'{indent}"""{lines[0].strip()}',
        *(f"{indent}{line}" if line else "" for line in lines[1:]),
        f'{indent}"""',
    ]
