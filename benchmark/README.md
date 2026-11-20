# Benchmarks

End-to-end benchmarks of Dubbo Python: what a call costs its server and its
consumer, beside Dubbo Java, Dubbo Go and the gRPC libraries of Python, over
the same service and under the same load.

## What is measured

Every implementation serves one service: an echo of bytes, as the `Bench`
service of `proto/bench.proto` over Triple, whose messages are Protobuf, and
as `BenchService.echo(byte[])` over Dubbo, whose bytes travel in Hessian 2.

| Scenario | What runs | The load |
|---|---|---|
| `one-core` | Dubbo Python, Java and Go, grpcio and grpclib, each on one core | ghz over Triple; the Go load of `go/load` over Dubbo |
| `multi-core` | Dubbo Python, Java and Go, each on eight cores, of which a Python process uses one | the same, on the other cores |
| `client` | One Dubbo Python consumer on one core | it calls Dubbo Java over Triple and Dubbo Go over Dubbo, on the other cores; Dubbo Go would compress its Triple responses |

Each scenario measures every payload size and number of calls in flight of
`scenarios.toml`, with a new server for each point, in each of the rounds:
64 points a round, about 80 minutes in all. The Python programs run on uvloop
when it is installed, else on asyncio, and the results say which.
A scenario with `cores` holds the side it measures to that many cores with
`taskset`, and the load to the others; Go to `GOMAXPROCS` and Java to
`ActiveProcessorCount` as many. Without `taskset`, as on macOS, only those
two settings hold, and the results say the server was not pinned.

Each point counts:

- **calls per second**;
- **CPU time per call** of the side measured, in microseconds: the CPU time
  of its process over the counted calls, divided by their number, and the
  **cores** it used meanwhile;
- **latency** percentiles, counted in buckets about 1% wide by the Python and
  Go loads, and by ghz;
- the **RSS** of the server: its peak on Linux, its last value elsewhere;
- the **cores the load used**, of those it may use. A load that used most of
  them may be what limits the throughput, and the charts mark its points.

### The loads

- **ghz** loads Triple, and waits for the calls in flight when the time is
  up, so that none fails as its connections close.
- **`go/load`** loads Dubbo: a closed loop that sends a request body that
  Hessian 2 encodes once, as Dubbo Python sends it, and counts a response
  whose status is OK and which holds a value. Each connection writes the
  requests queued together in one write, as clients do. It decodes nothing,
  so that it adds next to nothing to what it measures.
- Each load opens `connections` connections, at most one for each call in
  flight. Every implementation of a protocol takes the same load.

## Layout

| Path | What it holds |
|---|---|
| `scenarios.toml` | What `run.py` measures |
| `run.py` | Runs the scenarios into a directory of `results/` |
| `plot.py` | Charts and tabulates one or more runs |
| `proto/bench.proto` | The service over Triple, which every implementation and ghz read |
| `python/` | The Python servers, `dubbo_server.py`, `grpcio_server.py` and `grpclib_server.py`; `client.py`, the Python consumers; the code generated from `bench.proto` |
| `java/` | A Maven project: the Dubbo Java server |
| `go/` | A Go module: the Dubbo Go server in `server/`, the load over Dubbo in `load/` |

## Set up

From the root of the repository:

```console
$ uv sync --inexact --extra uvloop --group benchmark
```

The other tools are optional; a point whose tools are missing is skipped,
and `env.json` says why:

- **Go** 1.25 or later builds Dubbo Go, which the `client` scenario calls
  over Dubbo, and the load over Dubbo. Without it, Python consumers in
  `load_processes` processes load the Dubbo servers, and may run out of CPU
  before a fast server does.
- **ghz** loads the Triple servers:
  `go install github.com/bojand/ghz/cmd/ghz@latest`. Without it, Python
  consumers load them, and Dubbo Go compresses its responses to them.
- **JDK** 17 or later and **Maven** build Dubbo Java, which the `client`
  scenario calls over Triple. Without them, it calls Dubbo Go there.
- **taskset**, of util-linux on Linux, holds each side to its cores.

## Run

```console
$ python benchmark/run.py
$ python benchmark/plot.py benchmark/results/20261120-101500
```

`run.py --scenario one-core` runs one scenario, and `--warmup`,
`--duration` and `--rounds` change its times; `--rounds 1` takes about
25 minutes. The rounds run one after
another over every point. A run writes, in its directory:

- `results.jsonl`, a line for each point of each round;
- `env.json`: the machine, the commit, and the versions of everything that ran;
- `logs/`, the output of each server.

`plot.py` writes into the directory of the first run, as SVG and as PNG,
each chart for one protocol and its serialization, `triple-protobuf` or
`dubbo-hessian2`; each shows the median of the rounds:

| Chart | What it shows |
|---|---|
| `*-throughput-one-core` | The headline: the peak throughput of each server on one core, over the numbers of calls in flight; a group of bars per payload, one bar per implementation, with the range of the rounds |
| `*-latency` | The P99 latency of each server on one core at 64 calls in flight |
| `*-throughput-multi-core` | The peak throughput of each Dubbo server on eight cores, as the headline |
| `*-consumer` | The peak throughput of the Dubbo Python consumer on one core |
| `report.html` | Every chart, with the numbers of each bar on hover, the environment and every point; it opens with nothing else |
| `summary.md` | Every point, with all its numbers |

## Compare two changes

Run the scenarios on each, then give both runs to `plot.py`, the baseline
first: the charts show the baseline, and `summary.md` and `report.html` list
every point of both:

```console
$ python benchmark/plot.py benchmark/results/before benchmark/results/after --out benchmark/results/compared
```

Alternate the runs of the two, so that a drift of the machine does not pass
for a change.

## Publish

Publish only numbers measured on Linux with `taskset`, on a machine that runs
nothing else, with the times of `scenarios.toml`, and give `env.json` with them.
On one core, Java runs its compiler and collector on the core it serves on:
say so beside its numbers, and give the multi-core ones with them. A laptop throttles
and runs other work: use it to compare two changes, not to quote.

## Find where the time goes

The benchmarks tell how much a call costs; a profiler tells where. Run a
server under load and record it with [py-spy](https://github.com/benfred/py-spy):

```console
$ cd benchmark/python
$ python dubbo_server.py --protocol tri --port 50051 & server=$!
$ ghz --insecure --proto ../proto/bench.proto --call org.apache.dubbo.benchmark.Bench.Echo \
    --data '{"data":"aGk="}' --concurrency 64 --duration 30s 127.0.0.1:50051 &
$ py-spy record --pid $server --duration 20 --output profile.svg
```

## Generate the code again

The generated code is included. After changing `proto/bench.proto`, from
`benchmark/`, with the `proto` group installed and the protoc plugins of Go on
`PATH`:

```console
$ python -m grpc_tools.protoc -Iproto --python_out=python --pyi_out=python proto/bench.proto
$ cd go && python -m grpc_tools.protoc -I../proto --go_out=. --go_opt=module=bench --go-triple_out=. ../proto/bench.proto
```

Maven generates the Java code as it builds.
