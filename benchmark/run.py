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

"""Measure the scenarios of scenarios.toml, writing each result as a line of results.jsonl beside env.json.

Each point starts a server, loads it, and reads the CPU time and memory of
the server process at the start and at the end of the counted calls. A
point whose tools are missing is skipped, and env.json lists why.
"""

import argparse
import base64
import datetime
import importlib.metadata
import importlib.util
import itertools
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import hessian2

HERE = Path(__file__).resolve().parent
PYTHON = HERE / "python"
# The protocols each implementation serves.
SERVES = {
    "python": {"tri", "dubbo"},
    "java": {"tri", "dubbo"},
    "go": {"tri", "dubbo"},
    "grpcio": {"tri"},
    "grpclib": {"tri"},
}
# ghz names the method by its full name, with a dot before it.
GHZ_CALL = "org.apache.dubbo.benchmark.Bench.Echo"
BENCH_SERVICE = "org.apache.dubbo.benchmark.BenchService"
# The event loop of the Python programs.
LOOP = "uvloop" if importlib.util.find_spec("uvloop") else "asyncio"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenarios", type=Path, default=HERE / "scenarios.toml")
    parser.add_argument("--scenario", action="append", help="the name of a scenario to run; all by default")
    parser.add_argument("--warmup", type=float, help="seconds before counting, over that of scenarios.toml")
    parser.add_argument("--duration", type=float, help="seconds counted, over that of scenarios.toml")
    parser.add_argument("--rounds", type=int, help="rounds of every point, over those of scenarios.toml")
    parser.add_argument("--out", type=Path, help="the directory of the results; a new one in results/ by default")
    args = parser.parse_args()

    settings = tomllib.loads(args.scenarios.read_text())
    warmup = args.warmup if args.warmup is not None else settings["warmup"]
    duration = args.duration if args.duration is not None else settings["duration"]
    rounds = args.rounds if args.rounds is not None else settings.get("rounds", 1)
    scenarios = [each for each in settings["scenario"] if not args.scenario or each["name"] in args.scenario]
    out = args.out or HERE / "results" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / "logs").mkdir(parents=True, exist_ok=True)

    servers = {each for scenario in scenarios if scenario["side"] == "server" for each in scenario["implementations"]}
    # Go builds the load of Dubbo servers; Go and Java are the servers the Python consumer calls.
    peers = {"go", "java"} if any(scenario["side"] == "client" for scenario in scenarios) else set()
    tools = Tools(out, servers | {"go"} | peers)
    (out / "env.json").write_text(json.dumps(environment(tools, warmup, duration, rounds), indent=2) + "\n")

    points = [point for scenario in scenarios for point in scenario_points(scenario)]
    with (out / "results.jsonl").open("a") as results:
        # Each round measures every point, so that a drift of the machine spreads over all of them.
        for round_, point in itertools.product(range(1, rounds + 1), points):
            missing = tools.missing(point["implementation"])
            if missing:
                if round_ == 1:
                    print(f"Skipping {point['implementation']} {point['protocol']}: {missing}", file=sys.stderr)
                continue
            result = measure(point, tools, settings, warmup, duration, out, round_)
            results.write(json.dumps({**point, "round": round_, **result}) + "\n")
            results.flush()
            print(summary(point, round_, result), file=sys.stderr)

    print(f"Wrote {out}", file=sys.stderr)


def scenario_points(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the points of ``scenario``: each implementation, protocol it serves, size and calls in flight."""
    points = []
    for implementation, protocol, size, concurrency in itertools.product(
        scenario["implementations"], scenario["protocols"], scenario["sizes"], scenario["concurrency"]
    ):
        if protocol not in SERVES[implementation]:
            continue
        points.append(
            {
                "scenario": scenario["name"],
                "side": scenario["side"],
                "implementation": implementation,
                "protocol": protocol,
                "loop": LOOP if python(implementation) else None,
                "size": size,
                "concurrency": concurrency,
                "cores": scenario.get("cores"),
            }
        )
    return points


def python(implementation: str) -> bool:
    return implementation in ("python", "grpcio", "grpclib")


class Tools:
    """The programs the points need, found once: ghz, taskset, and the builds of Go and Java."""

    def __init__(self, out: Path, implementations: set[str]) -> None:
        self.out = out
        self.ghz = shutil.which("ghz")
        self.taskset = shutil.which("taskset") if sys.platform == "linux" else None
        self.reasons: dict[str, str] = {}
        self.go_server = self.go_load = self.java = self.java_classpath = None
        if "go" in implementations:
            if shutil.which("go"):
                self.go_server, self.go_load = out / "go-server", out / "go-load"
                for program, binary in (("./server", self.go_server), ("./load", self.go_load)):
                    subprocess.run(["go", "build", "-o", str(binary), program], cwd=HERE / "go", check=True)
            else:
                self.reasons["go"] = "go is not installed"
        if "java" in implementations:
            if shutil.which("mvn"):
                classpath = out / "java-classpath.txt"
                subprocess.run(
                    ["mvn", "-q", "compile", "dependency:build-classpath", f"-Dmdep.outputFile={classpath}"],
                    cwd=HERE / "java",
                    check=True,
                )
                self.java_classpath = f"{HERE / 'java' / 'target' / 'classes'}{os.pathsep}{classpath.read_text()}"
                self.java = find_java()
            if self.java is None:
                self.reasons["java"] = "Maven or a Java runtime is not installed"
        for library in ("grpcio", "grpclib"):
            if importlib.util.find_spec("grpc" if library == "grpcio" else library) is None:
                self.reasons[library] = f"{library} is not installed; uv sync --inexact --group benchmark installs it"

    def missing(self, implementation: str) -> str | None:
        return self.reasons.get(implementation)

    def cpu_sets(self, cores: int | None) -> tuple[str | None, str | None, int]:
        """Return the CPUs of the side measured and of the other side for taskset, or none unpinned, and the count of the other's."""
        count = os.cpu_count() or 1
        if cores is None or self.taskset is None or cores >= count:
            return None, None, count
        return f"0-{cores - 1}", f"{cores}-{count - 1}", count - cores

    def request_body(self, size: int) -> Path:
        """Return the file of the body of a request of the Dubbo echo, as Dubbo Python sends it, of ``size`` bytes."""
        path = self.out / f"request-{size}.bin"
        if not path.exists():
            attachments = {"path": BENCH_SERVICE, "interface": BENCH_SERVICE, "version": "0.0.0", "timeout": "30000"}
            values = ("2.0.2", BENCH_SERVICE, "0.0.0", "echo", "[B", os.urandom(size), attachments)
            path.write_bytes(hessian2.dumps_many(values))
        return path


def find_java() -> str | None:
    """Return the java of JAVA_HOME, else of PATH, else the one Maven runs on."""
    home = os.environ.get("JAVA_HOME")
    candidates = [str(Path(home) / "bin" / "java")] if home else []
    candidates.append("java")
    for candidate in candidates:
        if subprocess.run([candidate, "-version"], capture_output=True).returncode == 0:
            return candidate
    version = subprocess.run(["mvn", "-v"], capture_output=True, text=True).stdout
    found = re.search(r"runtime: (.+)", version)
    return str(Path(found.group(1).strip()) / "bin" / "java") if found else None


def measure(
    point: dict[str, Any],
    tools: Tools,
    settings: dict[str, Any],
    warmup: float,
    duration: float,
    out: Path,
    round_: int,
):
    """Load the server of the point, or the server Python calls, and return what the counted calls cost."""
    port = free_port()
    protocol, size, concurrency = point["protocol"], point["size"], point["concurrency"]
    connections = min(settings.get("connections", 8), concurrency)
    measured, others, other_cores = tools.cpu_sets(point["cores"])
    if point["side"] == "server":
        command, env = server_command(point["implementation"], protocol, port, point["loop"], tools, point["cores"])
        command = pin(command, measured)
    else:
        peer = client_peer(protocol, tools)
        command, env = server_command(peer, protocol, port, "asyncio", tools, None)
        command = pin(command, others)
    name = "-".join(str(value) for value in (*point.values(), round_) if value is not None)

    with serving(command, env, port, out / "logs" / f"{name}.log") as server:
        if point["side"] == "client":
            client = python_load(protocol, port, size, concurrency, 1, point["loop"], warmup, duration, measured)
            result, before, after = run_load(client, PYTHON, server, warmup, duration)
            result["peer"] = f"Dubbo {peer.capitalize()}"
        elif protocol == "tri" and tools.ghz is not None:
            run_ghz(tools.ghz, port, size, concurrency, connections, warmup, others)
            before = process_stats(server.pid)
            result = run_ghz(tools.ghz, port, size, concurrency, connections, duration, others)
            after = process_stats(server.pid)
            result["load"] = "ghz"
        elif protocol != "tri" and tools.go_load is not None:
            load = [
                *(str(tools.go_load), "--address", f"127.0.0.1:{port}", "--body", str(tools.request_body(size))),
                *("--concurrency", str(concurrency), "--connections", str(connections)),
                *("--warmup", str(warmup), "--duration", str(duration)),
            ]
            result, before, after = run_load(pin(load, others), HERE, server, warmup, duration)
            result["load"] = "Go"
        else:
            processes = min(settings.get("load_processes", 4), concurrency)
            client = python_load(protocol, port, size, concurrency, processes, LOOP, warmup, duration, others)
            result, before, after = run_load(client, PYTHON, server, warmup, duration)
            result["load"] = f"Dubbo Python x{processes}"
            other_cores = min(other_cores, processes)
        if point["side"] == "server":
            if result.get("load_cores") is None and result["client_cpu_us"] is not None:
                result["load_cores"] = round(result["client_cpu_us"] * result["calls"] / 1e6 / duration, 2)
            # The cores the load may use: a load near them may be what limits the throughput.
            result["load_cores_available"] = other_cores

    calls = result["calls"]
    result["pinned"] = measured is not None
    result["server_cpu_us"] = round((after["cpu"] - before["cpu"]) / calls * 1e6, 2) if calls else None
    result["server_cores"] = round((after["cpu"] - before["cpu"]) / duration, 2)
    result["server_rss_mib"] = round(after["rss"] / 2**20, 1)
    return result


def pin(command: list[str], cpus: str | None) -> list[str]:
    """Return ``command`` run on the CPUs ``cpus`` by taskset, or as it is for none."""
    return command if cpus is None else ["taskset", "-c", cpus, *command]


def client_peer(protocol: str, tools: Tools) -> str:
    """Return the server the Python consumer calls: one that answers uncompressed unless configured otherwise.

    Dubbo Go compresses each Triple response its caller accepts compressed, and the consumer accepts gzip, so over
    Triple the consumer calls Dubbo Java.
    """
    if protocol == "tri" and tools.java is not None:
        return "java"
    return "go" if tools.go_server is not None else "python"


def server_command(
    implementation: str, protocol: str, port: int, loop: str | None, tools: Tools, cores: int | None
) -> tuple[list[str], dict[str, str]]:
    """Return the command of a server, and its environment, holding Go and Java to ``cores`` when given."""
    env = dict(os.environ)
    if implementation == "go":
        assert tools.go_server is not None
        if cores is not None:
            env["GOMAXPROCS"] = str(cores)
        return [str(tools.go_server), "--protocol", protocol, "--port", str(port)], env
    if implementation == "java":
        assert tools.java is not None
        assert tools.java_classpath is not None
        processors = [f"-XX:ActiveProcessorCount={cores}"] if cores is not None else []
        command = [
            *(tools.java, *processors, "-Dorg.slf4j.simpleLogger.defaultLogLevel=warn", "-cp", tools.java_classpath),
            *("org.apache.dubbo.benchmark.JavaServer", protocol, str(port)),
        ]
        return command, env
    script = {"python": "dubbo_server.py", "grpcio": "grpcio_server.py", "grpclib": "grpclib_server.py"}[implementation]
    options = ["--protocol", protocol] if implementation == "python" else []
    return [sys.executable, script, *options, "--port", str(port), "--loop", loop or "asyncio"], env


def python_load(protocol, port, size, concurrency, processes, loop, warmup, duration, cpus) -> list[str]:
    command = [
        *(sys.executable, "client.py", "--protocol", protocol, "--url", f"{protocol}://127.0.0.1:{port}"),
        *("--size", str(size), "--concurrency", str(concurrency), "--processes", str(processes), "--loop", loop),
        *("--warmup", str(warmup), "--duration", str(duration)),
    ]
    return pin(command, cpus)


def run_load(command: list[str], cwd: Path, server, warmup: float, duration: float):
    """Run a load that prints started, then its result, reading the stats of the server when it starts counting and when it stops."""
    with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, text=True) as load:
        assert load.stdout is not None
        if load.stdout.readline().strip() != "started":
            raise RuntimeError(f"{command[0]} did not start")
        time.sleep(warmup)
        before = process_stats(server.pid)
        time.sleep(duration)
        after = process_stats(server.pid)
        result = json.loads(load.stdout.readline())
    if load.returncode:
        raise RuntimeError(f"{command[0]} exited with {load.returncode}")
    return result, before, after


def run_ghz(ghz, port, size, concurrency, connections, seconds, cpus) -> dict[str, Any]:
    data = json.dumps({"data": base64.b64encode(os.urandom(size)).decode()})
    command = [
        *(ghz, "--insecure", "--proto", "bench.proto", "--call", GHZ_CALL, "--data", data),
        *("--concurrency", str(concurrency), "--connections", str(connections)),
        # Waiting for the calls in flight at the end, so that none fails as the connections close.
        *("--duration", f"{seconds}s", "--duration-stop", "wait", "--format", "json"),
        f"127.0.0.1:{port}",
    ]
    used = os.times()
    output = subprocess.run(pin(command, cpus), cwd=HERE / "proto", capture_output=True, text=True, check=True).stdout
    now = os.times()
    report = json.loads(output)
    codes = dict(report.get("statusCodeDistribution") or {})
    latencies = {f"p{each['percentage']:g}": round(each["latency"] / 1000, 1) for each in report["latencyDistribution"]}
    cpu = now.children_user + now.children_system - used.children_user - used.children_system
    return {
        "calls": codes.get("OK", 0),
        "errors": {code: count for code, count in codes.items() if code != "OK"},
        "rps": round(codes.get("OK", 0) / seconds, 1),
        "client_cpu_us": None,
        # Windows counts no CPU time of children.
        "load_cores": None if sys.platform == "win32" else round(cpu / seconds, 2),
        "latency_us": {
            **{name: latencies[name] for name in ("p50", "p90", "p99") if name in latencies},
            "max": round(report["slowest"] / 1000, 1),
        },
    }


class serving:
    """Run a server until leaving, once its port accepts, logging its output."""

    def __init__(self, command: list[str], env: dict[str, str], port: int, log: Path) -> None:
        self.command, self.env, self.port, self.log = command, env, port, log

    def __enter__(self) -> subprocess.Popen[bytes]:
        with self.log.open("wb") as log:
            cwd = PYTHON if sys.executable in self.command else HERE
            self.process = subprocess.Popen(self.command, cwd=cwd, env=self.env, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while True:
            if self.process.poll() is not None:
                raise RuntimeError(f"the server exited with {self.process.returncode}; see {self.log}")
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=1).close()
                return self.process
            except OSError:
                if time.monotonic() > deadline:
                    self.__exit__()
                    raise
                time.sleep(0.1)

    def __exit__(self, *exc_info: object) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def process_stats(pid: int) -> dict[str, float]:
    """Return the CPU seconds of a process, and its peak RSS on Linux or its RSS elsewhere in bytes."""
    if sys.platform == "linux":
        # The fields after the name, which may hold spaces; utime and stime are the 14th and 15th of the line.
        fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
        cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
        status = Path(f"/proc/{pid}/status").read_text()
        peak = re.search(r"^VmHWM:\s+(\d+) kB", status, re.MULTILINE)
        return {"cpu": cpu, "rss": int(peak.group(1)) * 1024 if peak else 0}
    output = subprocess.run(["ps", "-o", "time=,rss=", "-p", str(pid)], capture_output=True, text=True, check=True)
    elapsed, rss = output.stdout.split()
    seconds = 0.0
    for part in elapsed.split(":"):
        seconds = seconds * 60 + float(part)
    return {"cpu": seconds, "rss": int(rss) * 1024}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def summary(point: dict[str, Any], round_: int, result: dict[str, Any]) -> str:
    loop = f" ({point['loop']})" if point["loop"] else ""
    return (
        f"{point['scenario']} round {round_}: {point['side']} {point['implementation']}{loop} {point['protocol']} "
        f"{point['size']} B x{point['concurrency']}: {result['rps']:,.0f} calls/s, "
        f"server {result['server_cpu_us']} us/call on {result['server_cores']} cores, "
        f"p99 {result['latency_us'].get('p99')} us, errors {sum(result['errors'].values())}"
    )


def environment(tools: Tools, warmup: float, duration: float, rounds: int) -> dict[str, Any]:
    def output(*command: str) -> str | None:
        try:
            done = subprocess.run(command, cwd=HERE, capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        lines = (done.stdout or done.stderr).strip().splitlines()
        return lines[0] if lines else ""

    def version(package: str) -> str | None:
        try:
            return importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            return None

    if sys.platform == "linux":
        names = re.findall(r"^model name\s*:\s*(.+)$", Path("/proc/cpuinfo").read_text(), re.MULTILINE)
        cpu = names[0] if names else None
    else:
        cpu = output("sysctl", "-n", "machdep.cpu.brand_string")
    go_module = (HERE / "go" / "go.mod").read_text()
    pom = (HERE / "java" / "pom.xml").read_text()
    return {
        "time": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "commit": output("git", "rev-parse", "HEAD"),
        "changed": bool(output("git", "status", "--porcelain", "--untracked-files=no")),
        "platform": platform.platform(),
        "cpu": cpu,
        "cpus": os.cpu_count(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "versions": {
            "apache-dubbo": version("apache-dubbo"),
            "uvloop": version("uvloop"),
            "grpcio": version("grpcio"),
            "grpclib": version("grpclib"),
            "dubbo-java": re.search(r"<dubbo.version>(.+)</dubbo.version>", pom).group(1),
            "dubbo-go": re.search(r"^\s*dubbo\.apache\.org/\S+ (v\S+)", go_module, re.MULTILINE).group(1),
            "java": output(tools.java, "-version") if tools.java else None,
            "go": output("go", "version") if tools.go_server else None,
        },
        "ghz": tools.ghz is not None,
        "taskset": tools.taskset is not None,
        "skipped": tools.reasons,
        "warmup": warmup,
        "duration": duration,
        "rounds": rounds,
    }


if __name__ == "__main__":
    main()
