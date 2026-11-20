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

import subprocess
import sys
import typing
from importlib.metadata import EntryPoint, EntryPoints
from pathlib import Path

import pytest

from dubbo import DubboError
from dubbo.extension import ExtensionError, Extensions, extension_point, loader

_GROUP = "apache_dubbo.test_renderer"


class Renderer(typing.Protocol):
    def __init__(self, *, prefix: str) -> None: ...

    def render(self, text: str) -> str: ...


class OtherRenderer(typing.Protocol):
    def __init__(self, *, prefix: str) -> None: ...

    def render(self, text: str) -> str: ...


class PrefixRenderer:
    def __init__(self, *, prefix: str) -> None:
        self.prefix = prefix

    def render(self, text: str) -> str:
        return self.prefix + text


@pytest.fixture
def catalogue(monkeypatch):
    entries = []
    monkeypatch.setattr(loader, "_POINTS", {Renderer: _GROUP, OtherRenderer: _GROUP + "_other"})
    monkeypatch.setattr(loader.metadata, "entry_points", lambda: EntryPoints(entries))
    return entries


def test_register_returns_class_function_and_bound_method_without_calling(catalogue) -> None:
    calls = []

    def factory(*, prefix: str) -> Renderer:
        calls.append(prefix)
        return PrefixRenderer(prefix=prefix)

    class Container:
        def resolve(self, *, prefix: str) -> Renderer:
            return factory(prefix=prefix)

    extensions = Extensions()
    extensions.register(Renderer, "class", PrefixRenderer)
    extensions.register(Renderer, "function", factory)
    extensions.register(Renderer, "container", Container().resolve)

    cls = extensions.get(Renderer, "class")
    function = extensions.get(Renderer, "function")
    method = extensions.get(Renderer, "container")
    assert cls is PrefixRenderer
    assert function is factory
    assert calls == []
    assert function(prefix="a").render("b") == "ab"
    assert method(prefix="c").render("d") == "cd"
    assert calls == ["a", "c"]
    assert cls(prefix="x") is not cls(prefix="x")


def test_registrations_are_isolated_by_instance_and_extension_point(catalogue) -> None:
    first, second = Extensions(), Extensions()
    first.register(Renderer, "same", PrefixRenderer)
    first.register(OtherRenderer, "same", PrefixRenderer)
    assert first.get(Renderer, "same") is PrefixRenderer
    assert first.get(OtherRenderer, "same") is PrefixRenderer
    with pytest.raises(ExtensionError, match="unknown extension 'same'"):
        second.get(Renderer, "same")


def test_duplicate_registration_never_replaces_existing_factory(catalogue) -> None:
    extensions = Extensions()
    extensions.register(Renderer, "builtin", PrefixRenderer)
    with pytest.raises(ExtensionError, match="duplicate extension 'builtin'"):
        extensions.register(Renderer, "builtin", lambda **kwargs: None)
    assert extensions.get(Renderer, "builtin") is PrefixRenderer


def test_names_list_installed_and_registered_implementations_without_loading(catalogue) -> None:
    catalogue.append(EntryPoint("installed", "_dubbo_test_missing_module:Renderer", _GROUP))
    extensions = Extensions()
    extensions.register(Renderer, "registered", PrefixRenderer)

    assert extensions.names(Renderer) == ["installed", "registered"]
    assert extensions.names(OtherRenderer) == []
    with pytest.raises(ExtensionError, match="unknown extension point"):
        extensions.names(str)


def test_unknown_point_cannot_be_registered(catalogue) -> None:
    extensions = Extensions()
    with pytest.raises(ExtensionError, match="unknown extension point"):
        extensions.register(str, "custom", str)
    with pytest.raises(ExtensionError, match="unknown extension point"):
        extensions.get(str, "custom")


def test_non_callable_registration_is_an_argument_error(catalogue) -> None:
    extensions = Extensions()
    with pytest.raises(TypeError, match="must be callable"):
        extensions.register(Renderer, "bad", object())
    with pytest.raises(ExtensionError, match="unknown extension 'bad'"):
        extensions.get(Renderer, "bad")


def test_factory_exceptions_belong_to_the_caller(catalogue) -> None:
    failure = ValueError("factory failed")

    def factory(*, prefix: str) -> Renderer:
        raise failure

    extensions = Extensions()
    extensions.register(Renderer, "failing", factory)
    loaded = extensions.get(Renderer, "failing")
    with pytest.raises(ValueError, match="factory failed") as caught:
        loaded(prefix="x")
    assert caught.value is failure


def test_entry_points_are_imported_on_get_and_only_factories_are_cached(catalogue, tmp_path, monkeypatch) -> None:
    module_name = "_dubbo_test_lazy_extension"
    (tmp_path / f"{module_name}.py").write_text(
        "created = 0\n"
        "class Renderer:\n"
        "    def __init__(self, *, prefix):\n"
        "        global created\n"
        "        created += 1\n"
        "        self.prefix = prefix\n"
        "    def render(self, text):\n"
        "        return self.prefix + text\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    catalogue.append(EntryPoint(name="plugin", value=f"{module_name}:Renderer", group=_GROUP))
    try:
        extensions = Extensions()
        assert module_name not in sys.modules
        factory = extensions.get(Renderer, "plugin")
        module = sys.modules[module_name]
        assert module.created == 0
        module.Renderer = None
        assert extensions.get(Renderer, "plugin") is factory
        assert factory(prefix="a").render("b") == "ab"
        factory(prefix="c")
        assert module.created == 2
    finally:
        sys.modules.pop(module_name, None)


def test_direct_registration_cannot_replace_unloaded_entry_point(catalogue) -> None:
    catalogue.append(EntryPoint(name="plugin", value="_missing_dubbo_plugin:Factory", group=_GROUP))
    extensions = Extensions()
    with pytest.raises(ExtensionError, match="duplicate extension 'plugin'"):
        extensions.register(Renderer, "plugin", PrefixRenderer)


def test_duplicate_discovery_fails_before_import(catalogue) -> None:
    catalogue.extend(
        [
            EntryPoint(name="same", value="_first_missing_plugin:Factory", group=_GROUP),
            EntryPoint(name="same", value="_second_missing_plugin:Factory", group=_GROUP),
        ]
    )
    extensions = Extensions()
    with pytest.raises(ExtensionError, match="duplicate extension 'same'"):
        extensions.get(Renderer, "other")


def test_declared_point_is_returned_unchanged_and_resolves_its_group(catalogue, monkeypatch) -> None:
    monkeypatch.setattr(loader, "_POINTS", {})

    class Point(typing.Protocol):
        def __init__(self, *, prefix: str) -> None: ...

        def render(self, text: str) -> str: ...

    assert extension_point(_GROUP)(Point) is Point
    catalogue.append(EntryPoint(name="plugin", value="builtins:None", group=_GROUP))
    with pytest.raises(ExtensionError, match=f"group '{_GROUP}' must be callable"):
        Extensions().get(Point, "plugin")


def test_no_name_selects_the_default_the_point_declares(catalogue, monkeypatch) -> None:
    monkeypatch.setattr(loader, "_POINTS", {})
    monkeypatch.setattr(loader, "_DEFAULTS", {})

    class Point(typing.Protocol):
        def __init__(self, *, prefix: str) -> None: ...

    class Bare(typing.Protocol):
        def __init__(self, *, prefix: str) -> None: ...

    extension_point(_GROUP, default="prefix")(Point)
    extension_point(_GROUP + "_bare")(Bare)
    instance = Extensions()
    instance.register(Point, "prefix", PrefixRenderer)

    assert instance.get(Point, None) is PrefixRenderer
    with pytest.raises(ExtensionError, match="no default"):
        instance.get(Bare, None)


def test_discovery_waits_for_first_use(catalogue, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(loader.metadata, "entry_points", lambda: calls.append(1) or EntryPoints(catalogue))
    extensions = Extensions()
    assert calls == []
    extensions.register(Renderer, "class", PrefixRenderer)
    assert calls == [1]


def test_discovery_happens_once_and_ignores_unrelated_groups(catalogue, monkeypatch) -> None:
    calls = []

    def discover():
        calls.append(1)
        return EntryPoints(catalogue)

    monkeypatch.setattr(loader.metadata, "entry_points", discover)
    catalogue.extend(
        [
            EntryPoint(name="same", value="_missing_plugin:Factory", group="unrelated"),
            EntryPoint(name="same", value="_missing_plugin:Other", group="unrelated"),
        ]
    )
    extensions = Extensions()
    extensions.register(Renderer, "class", PrefixRenderer)
    assert extensions.get(Renderer, "class") is PrefixRenderer
    assert calls == [1]
    catalogue.append(EntryPoint(name="later", value="_missing_plugin:Factory", group=_GROUP))
    with pytest.raises(ExtensionError, match="unknown extension 'later'"):
        extensions.get(Renderer, "later")


@pytest.mark.parametrize(
    ("target", "cause"),
    [("_missing_dubbo_plugin:Factory", ModuleNotFoundError), ("builtins:_missing_dubbo_attribute", AttributeError)],
)
def test_import_failure_preserves_cause_and_context(catalogue, target: str, cause: type[Exception]) -> None:
    catalogue.append(EntryPoint(name="broken", value=target, group=_GROUP))
    extensions = Extensions()
    with pytest.raises(ExtensionError, match="cannot load extension 'broken'") as caught:
        extensions.get(Renderer, "broken")
    assert isinstance(caught.value, DubboError)
    assert isinstance(caught.value.__cause__, cause)
    assert _GROUP in str(caught.value)
    assert target in str(caught.value)


def test_non_callable_entry_point_is_an_extension_error(catalogue) -> None:
    catalogue.append(EntryPoint(name="bad", value="builtins:None", group=_GROUP))
    extensions = Extensions()
    with pytest.raises(ExtensionError, match="must be callable"):
        extensions.get(Renderer, "bad")


def test_ty_preserves_factory_parameters_and_result_interface(tmp_path: Path) -> None:
    source = """import typing
from dubbo.extension import Extensions

class Point(typing.Protocol):
    def __init__(self, *, prefix: str) -> None: ...
    def render(self, text: str) -> str: ...

class Implementation:
    def __init__(self, *, prefix: str) -> None: pass
    def render(self, text: str) -> str: return text

def factory(*, prefix: str) -> Point:
    return Implementation(prefix=prefix)

extensions = Extensions()
extensions.register(Point, "class", Implementation)
extensions.register(Point, "function", factory)
provider = extensions.get(Point, "class")
instance = provider(prefix="x")
instance.render("text")

def parse(text: str, /) -> dict[str, object]:
    raise NotImplementedError

def parse_upper(text: str, /) -> dict[str, object]:
    return {"text": text.upper()}

extensions.register(parse, "upper", parse_upper)
parsed: dict[str, object] = extensions.get(parse, "upper")("text")
"""
    valid = tmp_path / "valid.py"
    valid.write_text(source)
    result = subprocess.run(
        ["ty", "check", "--python-version", "3.10", "--output-format", "concise", str(valid)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    invalid = tmp_path / "invalid.py"
    invalid.write_text(
        source
        + """
class BadConstructor:
    def __init__(self, count: int) -> None: pass
    def render(self, text: str) -> str: return text

extensions.register(Point, "bad", BadConstructor)
provider(count=1)

def parse_number(text: int, /) -> dict[str, object]:
    return {}

extensions.register(parse, "number", parse_number)
extensions.get(parse, "upper")(1)
instance.not_a_method()
"""
    )
    result = subprocess.run(
        ["ty", "check", "--python-version", "3.10", "--output-format", "concise", str(invalid)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "invalid-argument-type" in result.stdout
    assert "unknown-argument" in result.stdout
    assert "missing-attribute" in result.stdout
