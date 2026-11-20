# Contributing to Apache Dubbo for Python

Thank you for helping. This guide covers how to set up a development
environment, the checks a change passes, and the conventions of the code and
its tests.

## Before you start

- Report bugs and propose features in the
  [Apache Dubbo issue tracker](https://github.com/apache/dubbo/issues),
  saying that they concern Dubbo for Python; this repository has no issue
  tracker of its own. Discuss larger topics on the
  [dev@dubbo.apache.org](mailto:dev@dubbo.apache.org) mailing list; the
  [subscription guide](https://github.com/apache/dubbo/wiki/Mailing-list-subscription-guide)
  explains how to join it.
- Report security vulnerabilities privately to
  [security@dubbo.apache.org](mailto:security@dubbo.apache.org), never in
  public; the [Apache security process](https://www.apache.org/security/)
  describes what follows.
- Discuss first, in an issue or on the mailing list, any change to the
  public API, the boundaries between packages, protocol or serialization
  behavior, dependencies, or the repository tooling and layout.
- Before a non-trivial contribution is accepted, you need to sign the
  [Individual Contributor License Agreement](https://www.apache.org/licenses/contributor-agreements.html#clas).

## Development setup

You need Python 3.11 to 3.14, [uv](https://docs.astral.sh/uv/), and Docker
for the registry tests.

```shell
git clone https://github.com/apache/dubbo-python.git
cd dubbo-python
uv sync --all-extras
uv run pre-commit install
```

## Checks

CI runs these on every pull request; run them before you push:

```shell
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest tests/unit tests/integration
```

The registry tests need a real ZooKeeper and Nacos. Start the versions CI
uses, and point the tests at them:

```shell
docker compose -f tests/integration/compose.yaml up -d --wait
DUBBO_TEST_ZOOKEEPER=127.0.0.1:2181 DUBBO_TEST_NACOS=127.0.0.1:8848 \
    uv run pytest tests/integration -m "zookeeper or nacos or samples"
```

A test marked `zookeeper` or `nacos` is skipped while its variable is
unset. CI runs the samples, marked `samples`, with these, on Linux.

Two scripts cover what tests cannot:

- `uv run --group proto python scripts/generate_protos.py` regenerates the
  modules of the protos in `src/dubbo/_proto`;
- `python scripts/check_install.py` checks that a fresh install with the
  default dependencies serves and calls over each built-in protocol.

## Code conventions

### Scope

- Derive behavior from Dubbo contracts and the needs of Python users. What
  crosses languages, such as wire formats, registry data, metadata and rule
  formats, follows Dubbo Java and Go exactly; everything else follows
  mainstream Python practice.
- When a change follows Dubbo Java or Go, a specification or a library
  contract, link the source it follows in the pull request.
- Prefer the standard library and existing dependencies. Add a dependency
  only for a current need.
- While the project is in beta, an incorrect design is replaced directly,
  without compatibility aliases or shims.

### Layout

- Packages follow Dubbo domains: `rpc` for the call model, `application.py`
  for the application, then `registry`, `metadata`, `cluster`, `protocol`,
  `transport` and the other extension domains. The code that connects a
  domain to the application lives in that domain, such as provider
  registration in `registry`.
- An `__init__.py` only re-exports. An extension point keeps its contract in
  `base.py` and its implementations in sibling modules named after them,
  such as `kazoo.py`; a package's exceptions live in `exceptions.py`. An
  implementation of several extension points of one domain is a package
  named after it, with a module per extension point, such as
  `registry/zookeeper/interface.py`.
- Module names have no leading underscore; private names inside a module
  do. Only generated code, such as `_proto`, keeps one on its package.

### Naming

Name a function by what the caller gets and who closes it, as the standard
library does:

- a `get` method looks up something that exists, such as `extensions.get`;
- `get_` or a noun returns what its arguments determine: an equal value, such
  as `inspect.signature`, or the same instance for the same arguments, such
  as `logging.getLogger`, which its owner opens on first use and closes;
- `create_` builds a new resource that the caller closes, such as
  `anyio.create_task_group`;
- `connect` or `open_` is a context manager holding a connection or a stream
  until it exits, such as `anyio.open_file`;
- a verb names a context manager that keeps a state while its block runs and
  returns no handle, such as `contextlib.suppress`;
- a `from_` class method is an alternate constructor, and a `replace` method
  returns a changed copy of an immutable value.

The function that returns an instance of an extension point lives in that
point's `base.py`, such as `get_serialization`. A hook that only subclasses
implement has a leading underscore. Names and errors that users see use
plain Python vocabulary.

### Concurrency

- The framework runs on asyncio, with uvloop optional; trio is not a target.
- Use AnyIO for task groups, timeouts, cancel scopes, shielding, events,
  locks, sleeping and thread offload. Use asyncio directly only for the I/O
  layer AnyIO does not cover, such as protocols, transports and servers, and
  on per-call paths where a measurement shows the cost of AnyIO; say so where
  it is used.
- Wait for one condition with one kind of primitive. Keep runtime types such
  as futures, tasks and events out of extension contracts.

### Lifetimes

Nothing outlives its owner, as in AnyIO structured concurrency:

- Each thing with a lifetime, such as a connection, server, task, watch,
  session or worker thread, has one owner that closes it. It is entered with
  `async with`, or registered on the owner's exit stack as soon as it is
  acquired.
- A lifetime is entered and exited in one task, so a public lifetime is a
  context manager, never a `start` and `stop` pair. Background work runs
  only in a task group that such a lifetime owns. A pool may close a pooled
  resource from another task when the resource holds no task group or cancel
  scope of the tasks that use it, as httpcore and asyncpg pools do.
- Opening is all or nothing: a failure or a cancellation part way releases
  what was acquired.
- Closing has two phases. The graceful waits, such as draining calls or
  waiting for a peer, stay cancellable and are bounded by configuration or a
  module constant. Once cancelled, release at once by what waits on no peer,
  such as cancelling tasks and aborting transports, under a short, bounded
  shield. Never shield a graceful wait.
- Stop gracefully only when asked, by leaving `async with` normally; a
  cancellation means stop now.

### Data, configuration and constants

- Declarative data models use attrs, declared with `attrs.define` and
  explicit options, such as `@attrs.define(frozen=True, kw_only=True)`.
  Ordinary classes need no model decorator.
- Only the configuration layer reads environment variables. A variable
  shared with other languages, such as `DUBBO_IP_TO_REGISTRY`, sets a
  configuration field that names it in its metadata; components read the
  field or the URL it becomes.
- `dubbo.constants` holds only Dubbo vocabulary shared with other languages,
  such as URL parameter keys named `*_KEY`, and the values that
  configuration fields left as `None` stand for, named `DEFAULT_*`.
  Constants private to one module stay in it.

### Logging

Log as the Python logging HOWTO advises libraries:

- each module logs through `_logger = logging.getLogger(__name__)`, and the
  framework never adds handlers or configures logging;
- pass the arguments of `%` placeholders instead of formatting the message;
- write a sentence without a final period that says what happened and, when
  the reader cannot tell, what follows, such as
  `"Cannot read the rule %s; the one before stays"`;
- use `debug` for detail, `info` for lifecycle events, `warning` for a
  failure the framework recovers from, and `error` or `exception` for one
  that loses work;
- attach the traceback when it helps, and never log secrets; the `str` of a
  URL hides its password.

### Style

- Ruff formats and lints the code; ty checks types.
- Order the members of a class: class attributes, `__init__` and the `from_`
  constructors, properties, public methods, protocol methods such as
  `__aenter__` and `__repr__`, then private methods.
- Separate the logical steps of a function with a single blank line: after a
  guard clause, and between setup, processing and returning. Formatters keep
  these lines but never add them.
- Comments state what the code does, or why when the code cannot show it.
  They do not discuss alternatives, history or other implementations.
  Docstrings state the contract: what a function returns, raises and owns.

## Tests

A test states one claim about a contract and fails when that claim breaks.

### What to test

- Start from a contract the code owns: a public docstring, a cross-language
  format such as wire bytes, registry nodes, metadata JSON or rule YAML, a
  lifecycle promise, or an error the caller can act on.
- Name the plausible wrong implementation the test would catch; if no
  realistic bug fails it, do not write it.
- Test at the layer that owns the claim, once, and end to end only where the
  wiring itself can break.
- Take edge cases from the input domain and the states the contract defines:
  boundaries, lifecycle states, the interleavings the contract promises, the
  failures the layer owns, and values that other Dubbo languages produce. Do
  not invent inputs the public path cannot produce.
- Do not test library behavior, private helpers, annotation spelling, or log
  text that is not a contract.

### Tests never justify defensive code

Do not add guards, `isinstance` checks or fallback branches to `src` so that
a test passes with an impossible input. Validate once where data enters from
outside: network bytes, files, environment variables, registry and
configuration center content, and the arguments of public entry points.
Inside, trust the value.

### How to write a test

- Name the test as its claim: `test_failover_retries_another_provider_after_unavailable`.
- Separate arrange, act and assert with single blank lines, and assert the
  whole observable result with equality where possible.
- Use `pytest.raises` with the specific exception and a `match` on the part
  the caller relies on, and `pytest.mark.parametrize` with readable ids for
  one rule over many inputs.
- Prefer small fakes that implement an extension contract over patching
  internals. Use real loopback sockets for connection semantics, and real
  ZooKeeper or Nacos for registry semantics.
- Async tests use the AnyIO pytest plugin on asyncio. Synchronize on events,
  never on a delay that guesses whether another task is ready, and bound
  waits with `anyio.fail_after`.
- Async tests run on a virtual clock that starts at 0 and, while every task
  waits, jumps to the next timer. Assert exactly the time a deadline, timeout
  or grace period promises, such as
  `assert anyio.current_time() - started == pytest.approx(0.2)`, and step
  through time with `anyio.sleep`, never by looping until the clock passes a
  point. The clock holds still while a thread of AnyIO or of the event loop
  works, so a test never waits in a thread for the event loop: it reads raw
  sockets with `loop.sock_recv`. A test that waits for other threads, a
  process or the operating system is marked `real_clock` and runs in real
  time.
- Close every resource. Warnings are errors, and a test asserts that the
  tasks, watches and listeners its subject owns have exited.
- Interoperability evidence captured from a Java or Go peer becomes a golden
  file under the test package's `data` directory, with a note giving the
  peer, its version, and the commands that produced it.
- For a contract whose failure is costly, such as a lifecycle or a wire
  format, break the code once by hand and confirm that a test fails.

### Layout

- `tests/unit/<domain>/test_<module>.py` mirrors `src/dubbo`, with no
  network and no external processes.
- `tests/integration/` uses loopback sockets, subprocesses, and real
  ZooKeeper or Nacos behind markers.
- Shared fixtures live in the nearest `conftest.py`. Tests share one registry
  server per run, so each keeps what it creates under a unique ZooKeeper
  root or Nacos service and group.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make one change per pull request, with its tests and documentation.
3. Run the checks above. CI also runs the tests on Linux, macOS and
   Windows, against the oldest and newest supported ZooKeeper and Nacos,
   and checks the license headers.
4. Open the pull request against `main`. Its title summarizes the change in
   one line, and its description says why; link the issue it resolves, such
   as `Fixes apache/dubbo#12345`.

Pull requests are squash-merged, so the title becomes the commit message on
`main`.

As the Apache Software Foundation requires:

- every new source file starts with the Apache License header, copied from
  an existing file; the license check of CI lists any that lack it;
- files carry no author names, such as `__author__`; the history records
  who contributed;
- code from another project may be included only under a license
  compatible with the Apache License, as the
  [ASF third-party license policy](https://www.apache.org/legal/resolved.html)
  defines; discuss it first;
- a contribution written with generative AI tools follows the
  [ASF Generative Tooling Guidance](https://www.apache.org/legal/generative-tooling.html),
  which recommends naming the tool in the commit message, such as
  `Generated-by: <tool> <version>`.
