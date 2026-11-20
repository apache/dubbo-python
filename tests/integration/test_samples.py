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
"""The samples run as their READMEs say and print what they show."""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

# Samples show the API, whatever the platform; CI runs them on Linux.
pytestmark = pytest.mark.samples

SAMPLES = Path(__file__).parents[2] / "samples"

_TIMEOUT = 20


@contextmanager
def _serving(
    directory: Path,
    port: int,
    *args: str,
    env: dict[str, str] | None = None,
    executable: str = sys.executable,
    stopped_code: int = 0,
) -> Iterator[tuple[subprocess.Popen[str], list[str]]]:
    """Run a server of a sample once its port accepts, and stop it as Ctrl+C does.

    Yields the process, and the lines of its output that remain unread once it
    has stopped, with ``stopped_code``.
    """
    process = subprocess.Popen(
        [executable, *args],
        cwd=directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})},
    )
    output: list[str] = []
    try:
        _wait_for_port(process, port)
        yield process, output
    finally:
        if sys.platform == "win32":
            process.terminate()
        else:
            process.send_signal(signal.SIGINT)
        out, _ = process.communicate(timeout=_TIMEOUT)
        output.extend(out.splitlines())

    assert process.returncode == stopped_code or sys.platform == "win32", out


def _wait_for_port(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(process.communicate()[0])
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        except OSError:
            time.sleep(0.1)
        else:
            return
    raise AssertionError(f"nothing listens on port {port}")


def _run(directory: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        env={**os.environ, **(env or {})},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize(
    ("sample", "port", "server", "client", "printed"),
    [
        pytest.param(
            "basics/01_hello_world",
            20880,
            "server.py",
            "client.py",
            "Hello, Alice!\nHello, Bob!\n",
            id="hello-world",
        ),
        pytest.param("basics/02_protobuf", 50051, "server.py", "client.py", "Hello, Dubbo!\n", id="protobuf"),
        pytest.param(
            "basics/03_streaming",
            50051,
            "server.py",
            "client.py",
            "Server streaming:\n"
            "  Hello #1, Alice!\n"
            "  Hello #2, Alice!\n"
            "  Hello #3, Alice!\n"
            "Client streaming:\n"
            "  Hello, Alice, Bob, Carol!\n"
            "Bidirectional streaming:\n"
            "  Nice to meet you, Alice\n"
            "  Nice to meet you, Bob\n",
            id="streaming",
        ),
        pytest.param(
            "basics/08_errors_and_timeouts",
            50051,
            "server.py",
            "client.py",
            "User 1: Alice\n"
            "User 2: Bob\n"
            "No user 42\n"
            "Failed: INVALID_ARGUMENT: a user ID is not negative: -1\n"
            "Exported 2 users\n"
            "Gave up exporting after 1 second\n",
            id="errors-and-timeouts",
        ),
        pytest.param(
            "basics/14_filters",
            20880,
            "server.py",
            "client.py",
            "With the key: Hello, Alice!\nWithout: PERMISSION_DENIED: a valid API key is required\n",
            id="filters",
        ),
        pytest.param(
            "basics/17_generic",
            20880,
            "server.py",
            "client.py",
            "{'id': 1, 'name': 'Alice', 'email': 'alice@example.com'}\n['Alice']\nUNKNOWN: no user has ID 42\n",
            id="generic",
        ),
        pytest.param(
            "interop/grpc", 50051, "dubbo_server.py", "grpc_client.py", "Hello, gRPC, from Dubbo!\n", id="grpc-to-dubbo"
        ),
        pytest.param(
            "interop/grpc", 50052, "grpc_server.py", "dubbo_client.py", "Hello, Dubbo, from gRPC!\n", id="dubbo-to-grpc"
        ),
    ],
)
def test_the_client_of_a_sample_prints_the_replies_of_its_server(sample, port, server, client, printed):
    directory = SAMPLES / sample

    with _serving(directory, port, server):
        output = _run(directory, client)

    assert output == printed


def test_the_context_sample_passes_attachments_along_its_chain_of_services():
    directory = SAMPLES / "basics/09_context"

    with (
        _serving(directory, 20881, "inventory_server.py") as (_, inventory_output),
        _serving(directory, 20880, "order_server.py") as (_, order_output),
    ):
        output = _run(directory, "client.py")

    assert output == "Ordered 2 x book\nServed by order-server\n"
    assert order_output[-1].startswith("[trace 4bf92f35] Order from alice at 127.0.0.1:")
    assert inventory_output[-1] == "[trace 4bf92f35] Reserving 2 x book for alice"


def test_the_load_balancing_sample_spreads_and_fails_over_as_each_setting_says():
    directory = SAMPLES / "basics/11_load_balancing"

    with _serving(directory, 20882, "server.py"):
        output = _run(directory, "client.py").splitlines()

    leastactive = dict(item.split(" ") for item in output[1].removeprefix("leastactive: ").split(", "))
    assert [output[0], output[2], output[3]] == [
        "roundrobin: fast 3, slow 3",
        "failover: fast 6",
        "failfast: UNAVAILABLE 3, fast 3",
    ]
    assert int(leastactive["fast"]) > int(leastactive["slow"])


@pytest.mark.parametrize(
    "registry",
    [pytest.param("zookeeper", marks=pytest.mark.zookeeper), pytest.param("nacos", marks=pytest.mark.nacos)],
)
def test_the_registry_sample_finds_its_server_through_the_registry(registry, request):
    directory = SAMPLES / "basics/04_registry"
    env = {"DUBBO__REGISTRIES__DEFAULT__ADDRESS": f"{registry}://{request.getfixturevalue(registry)}"}

    with _serving(directory, 20880, "server.py", env=env):
        output = _run(directory, "client.py", env=env)

    assert re.fullmatch(r"(Hello, \w+! \(from server \d+\)\n){4}", output), output


@pytest.mark.zookeeper
def test_the_configuration_sample_calls_with_the_settings_of_its_files(zookeeper):
    directory = SAMPLES / "basics/05_configuration"
    env = {"DUBBO__REGISTRIES__ZOOKEEPER__ADDRESS": f"zookeeper://{zookeeper}"}

    with _serving(directory, 20880, "server.py", env=env) as (_, server_output):
        output = _run(directory, "client.py", env=env)

    assert output == "Hello, Alice!\nHello... Bob!\n"
    assert [line.split(" OK ")[0] for line in server_output if "dubbo.accesslog" in line] == [
        "INFO dubbo.accesslog: org.apache.dubbo.samples.Greeter greet",
        "INFO dubbo.accesslog: org.apache.dubbo.samples.Greeter greet_slowly",
    ]


@pytest.mark.parametrize("args", [(), ("--structlog",)], ids=["json", "structlog"])
def test_the_logging_sample_logs_each_call_as_a_json_line_with_its_trace_id(args):
    if args:
        pytest.importorskip("structlog")
    directory = SAMPLES / "basics/06_logging"

    with _serving(directory, 20880, "server.py", *args) as (_, server_output):
        output = _run(directory, "client.py")

    assert output == "Hello, Alice!\nHello, Bob!\n"
    calls = [line for line in map(json.loads, server_output) if line["logger"] == "dubbo.accesslog"]
    assert [(line["method"], line["status"], line["trace_id"]) for line in calls] == [
        ("greet", "OK", "4bf92f35"),
        ("greet", "OK", "a3ce929d"),
    ]


@pytest.mark.zookeeper
def test_the_group_version_sample_calls_the_version_its_client_names(zookeeper):
    directory = SAMPLES / "basics/10_group_version"
    env = {"DUBBO__REGISTRIES__DEFAULT__ADDRESS": f"zookeeper://{zookeeper}"}

    with _serving(directory, 20880, "server_v1.py", env=env), _serving(directory, 20881, "server_v2.py", env=env):
        outputs = [_run(directory, "client.py", env=env), _run(directory, "client.py", "2.0.0", env=env)]

    assert outputs == ["Version 1.0.0: Hello, Alice!\n", "Version 2.0.0: Good to see you, Alice!\n"]


@pytest.mark.zookeeper
def test_the_config_center_sample_lets_a_rule_lengthen_the_timeout_of_running_calls(zookeeper):
    if zookeeper != "127.0.0.1:2181":
        pytest.skip("the sample uses the ZooKeeper at 127.0.0.1:2181")
    directory = SAMPLES / "basics/12_config_center"
    _run(directory, "publish.py", "config")

    try:
        with _serving(directory, 20880, "server.py"):
            client = subprocess.Popen(
                [sys.executable, "client.py"],
                cwd=directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            assert client.stdout.readline().startswith("DEADLINE_EXCEEDED: ")
            _run(directory, "publish.py", "rule")
            output, _ = client.communicate(timeout=_TIMEOUT)
    finally:
        _run(directory, "publish.py", "clear")

    assert output.splitlines()[-3:] == ["Hello, Alice!"] * 3


@pytest.mark.zookeeper
def test_the_routing_sample_routes_by_tags_and_conditions_as_rules_change(zookeeper):
    if zookeeper != "127.0.0.1:2181":
        pytest.skip("the sample uses the ZooKeeper at 127.0.0.1:2181")
    directory = SAMPLES / "basics/13_routing"

    try:
        with _serving(directory, 20882, "server.py"):
            outputs = [_run(directory, "client.py")]
            for rule in ("condition", "tag"):
                _run(directory, "publish.py", rule)
                outputs.append(_run(directory, "client.py"))
    finally:
        _run(directory, "publish.py", "clear")

    assert [output.splitlines() for output in outputs] == [
        [
            "Bob: stable-1, stable-2",
            "Alice: stable-1, stable-2",
            "Bob, tagged gray: gray",
            "Bob, tagged canary: stable-1, stable-2",
        ],
        [
            "Bob: stable-1, stable-2",
            "Alice: stable-1",
            "Bob, tagged gray: gray",
            "Bob, tagged canary: stable-1, stable-2",
        ],
        ["Bob: stable-1", "Alice: stable-1", "Bob, tagged gray: gray", "Bob, tagged canary: stable-2"],
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="Ctrl+C cannot be sent to one process on Windows")
def test_the_graceful_shutdown_sample_finishes_the_call_it_is_stopped_in():
    directory = SAMPLES / "basics/07_graceful_shutdown"

    with _serving(directory, 20880, "server.py") as (server, server_output):
        client = subprocess.Popen(
            [sys.executable, "client.py"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        # The call takes 5 seconds; the server is stopped once it has started.
        for line in server.stdout:
            if line == "Greeting Watson...\n":
                break
    client_output, _ = client.communicate(timeout=_TIMEOUT)

    assert client_output.splitlines()[-1] == "Hello, Dr. Watson!"
    assert server_output == [
        "Stopping; running calls finish first",
        "Greeted Watson",
        "Database closed",
        "Stopped",
    ]


def test_the_extensions_sample_reads_its_configuration_with_the_installed_plugin():
    pytest.importorskip("dubbo_toml", reason="pip install -e samples/basics/15_extensions/dubbo-toml")
    directory = SAMPLES / "basics/15_extensions"

    with _serving(directory, 20880, "server.py") as (_, server_output):
        output = _run(directory, "client.py")

    assert output == "Hello, Alice!\nHello, Bob!\n"
    assert server_output[-1] == "extensions-server serving on port 20880; press Ctrl+C to stop"


def test_the_tls_sample_serves_only_clients_with_a_certificate():
    pytest.importorskip("trustme")
    directory = SAMPLES / "basics/16_tls"
    _run(directory, "make_certificates.py")

    with _serving(directory, 50051, "server.py"):
        output = _run(directory, "client.py")

    assert output == (
        "With a client certificate: Hello, Alice, over TLS!\nWithout: UNAVAILABLE: the HTTP/2 connection is closed\n"
    )


@pytest.mark.zookeeper
def test_the_fastapi_sample_answers_each_order_with_the_status_of_its_calls(zookeeper):
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    directory = SAMPLES / "integrations/fastapi"
    env = {"DUBBO__REGISTRIES__ZOOKEEPER__ADDRESS": f"zookeeper://{zookeeper}"}

    def order(user_id: int, item: str, quantity: int) -> tuple[int, dict[str, object]]:
        body = json.dumps({"user_id": user_id, "item": item, "quantity": quantity}).encode()
        request = urllib.request.Request(
            "http://127.0.0.1:8000/orders", data=body, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    with (
        _serving(directory, 50051, "backend.py", env=env) as (_, backend_output),
        _serving(directory, 50052, "orders.py", env=env),
        _serving(directory, 8000, "-m", "uvicorn", "app:app", env=env),
    ):
        answers = [order(1, "book", 2), order(9, "book", 1), order(1, "lamp", 5), order(2, "piano", 1)]

    assert answers == [
        (200, {"id": 1, "user": "Alice", "item": "book", "quantity": 2, "total": 25.0}),
        (404, {"detail": "no user has ID 9"}),
        (409, {"detail": "only 2 lamp left"}),
        (504, {"detail": "get_item did not complete within 1.0 seconds"}),
    ]
    # The trace id of each order reaches the services that the orders service calls.
    traced = [line.split()[0] for line in backend_output if line.startswith("[")]
    assert len(traced) == 8
    assert len(set(traced)) == 4


@pytest.mark.parametrize(
    ("answer", "printed", "calls"),
    [
        ("y", "Drafted PO-0001", ["draft", "low_stock", "predict", "quotes"]),
        ("n", "Nothing drafted", ["low_stock", "predict", "quotes"]),
    ],
    ids=["agreed", "declined"],
)
def test_the_pydantic_ai_sample_plans_with_the_services_as_tools_and_drafts_only_once_agreed(answer, printed, calls):
    pytest.importorskip("pydantic_ai")
    directory = SAMPLES / "integrations/pydantic_ai"
    # The test model of Pydantic AI calls each tool once, with arguments it makes up, and needs no API key.
    env = {**os.environ, "MODEL": "test", "PYDANTIC_AI_NO_BANNER": "1"}

    with _serving(directory, 20880, "services.py") as (_, served):
        planned = subprocess.run(
            [sys.executable, "planner.py"],
            cwd=directory,
            input=f"{answer}\n",
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env=env,
            check=False,
        )

    assert planned.returncode == 0, planned.stderr
    assert printed in planned.stdout
    assert sorted(line.split("(")[0] for line in served if "(" in line) == calls


def _traced(output: list[str]) -> list[str]:
    """The lines of ``output`` that a server of an interoperability sample prints for each call, with its trace id."""
    return [line for line in output if re.match(r"\[[\w-]+\] \w+\(", line)]


_MAVEN = shutil.which("mvn")


@pytest.mark.nacos
@pytest.mark.skipif(_MAVEN is None, reason="needs Maven and a JDK")
def test_the_java_sample_calls_java_from_python_and_python_from_java_through_nacos(nacos):
    if nacos != "127.0.0.1:8848":
        pytest.skip("the sample uses the Nacos at 127.0.0.1:8848")
    assert _MAVEN is not None
    directory = SAMPLES / "interop/java"
    maven = ["-q", "-f", "java/pom.xml"]
    subprocess.run([_MAVEN, *maven, "compile"], cwd=directory, check=True, timeout=600)

    with _serving(
        directory,
        50052,
        *maven,
        "exec:java",
        "-Dexec.mainClass=org.apache.dubbo.samples.JavaServer",
        executable=_MAVEN,
        stopped_code=130,
    ) as (_, java_server):
        from_python = _run(directory, "python_client.py")
    with _serving(directory, 50051, "python_server.py") as (_, python_server):
        java = subprocess.run(
            [_MAVEN, *maven, "exec:java", "-Dexec.mainClass=org.apache.dubbo.samples.JavaClient"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    # Newer JDKs warn on the output about the libraries of the client.
    from_java = [line for line in java.stdout.splitlines() if not line.startswith("WARNING: ")]

    assert from_python.splitlines() == [
        "Hello, Alice, from Java!",
        "Hello #1, Bob, from Java!",
        "Hello #2, Bob, from Java!",
        "Hello #3, Bob, from Java!",
        "User(id=1, name='Alice', email='alice@example.com')",
        "java.lang.IllegalArgumentException: no user has ID 42",
    ]
    assert from_java == [
        "Hello, Alice, from Python!",
        "Hello #1, Bob, from Python!",
        "Hello #2, Bob, from Python!",
        "Hello #3, Bob, from Python!",
        "User(id=1, name=Alice, email=alice@example.com)",
        "java.lang.IllegalArgumentException: no user has ID 42",
    ]
    # Each server prints the trace id that the client of the other language attached.
    assert _traced(java_server) == [
        "[py-4bf9] sayHello(Alice)",
        "[py-4bf9] getUser(1)",
        "[py-4bf9] getUser(42)",
    ]
    assert _traced(python_server) == [
        "[java-7f3a] say_hello(Alice)",
        "[java-7f3a] get_user(1)",
        "[None] get_user(42)",
    ]


_GO = shutil.which("go")


@pytest.mark.nacos
@pytest.mark.skipif(_GO is None, reason="needs Go")
def test_the_go_sample_calls_go_from_python_and_python_from_go_through_nacos(nacos, tmp_path):
    if nacos != "127.0.0.1:8848":
        pytest.skip("the sample uses the Nacos at 127.0.0.1:8848")
    assert _GO is not None
    directory = SAMPLES / "interop/go"
    # Built rather than run with go run, which leaves the server running when it is stopped alone.
    server = tmp_path / "server"
    subprocess.run([_GO, "-C", "go", "build", "-o", str(server), "./server"], cwd=directory, check=True, timeout=600)

    with _serving(directory, 50052, executable=str(server)) as (_, go_server):
        from_python = _run(directory, "python_client.py")
    with _serving(directory, 50051, "python_server.py") as (_, python_server):
        from_go = subprocess.run(
            [_GO, "-C", "go", "run", "./client"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout

    assert from_python.splitlines() == [
        "Hello, Alice, from Go!",
        "Hello #1, Bob, from Go!",
        "Hello #2, Bob, from Go!",
        "Hello #3, Bob, from Go!",
        "INVALID_ARGUMENT: a name is required",
    ]
    assert from_go.splitlines() == [
        "Hello, Alice, from Python!",
        "Hello #1, Bob, from Python!",
        "Hello #2, Bob, from Python!",
        "Hello #3, Bob, from Python!",
    ]
    # Each server prints the trace id that the client of the other language attached.
    assert _traced(go_server) == ["[py-4bf9] SayHello(Alice)", "[py-4bf9] SayHello()"]
    assert _traced(python_server) == ["[go-1c9d] say_hello(Alice)"]
