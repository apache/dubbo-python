<p align="center">
  <img src="https://dubbo.apache.org/imgs/nav_logo2.png" alt="Apache Dubbo" width="40%">
</p>

<h1 align="center">Apache Dubbo for Python</h1>

<p align="center">
  <a href="https://github.com/apache/dubbo-python/actions/workflows/ci.yml"><img src="https://github.com/apache/dubbo-python/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/apache-dubbo/"><img src="https://img.shields.io/pypi/v/apache-dubbo?label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/apache-dubbo/"><img src="https://img.shields.io/pypi/pyversions/apache-dubbo?label=Python" alt="Python versions"></a>
  <a href="https://github.com/apache/dubbo-python/blob/main/LICENSE"><img src="https://img.shields.io/github/license/apache/dubbo-python?label=License" alt="License"></a>
</p>

Apache Dubbo for Python is a Python-native implementation of
[Apache Dubbo](https://dubbo.apache.org/), the RPC and microservice framework.
Python services join the same registries as Dubbo Java and Dubbo Go services
and call them, and are called by them, with the service discovery and
traffic management of Dubbo built in.

> The project is in beta: the API may change.

## Highlights

- **Works with Dubbo Java and Go**: the Triple and Dubbo protocols, Protobuf
  and Hessian 2, ZooKeeper and Nacos registries, and both application-level
  and interface-level service discovery.
- **Compatible with gRPC**: Triple runs over HTTP/2, so gRPC clients and
  servers, `grpcurl`, health checks and reflection work with it.
- **Pythonic**: a service is a `typing.Protocol` with type hints; calls are
  `async`; an application runs inside `async with`, in any asyncio program,
  with uvloop optional.
- **Governance built in**: load balancing, cluster fault tolerance, routing
  rules and dynamic configuration, as in the other Dubbo languages.
- **Extensible**: every protocol, registry, load balancer, router and filter
  is a plugin that a package can add through an entry point.

## Features

From the API down to the transport:

| Layer | What is supported |
|---|---|
| API | Contracts as `typing.Protocol`; unary, server streaming, client streaming and bidirectional streaming calls; generic calls; contracts generated from `.proto` files by `protoc-gen-python-dubbo` |
| Configuration | Code, YAML, JSON, properties files and environment variables, layered; configuration centers on ZooKeeper and Nacos |
| Service discovery | ZooKeeper and Nacos registries; application-level and interface-level discovery; local and remote metadata |
| Traffic management | Load balancing: random, round robin, least active, consistent hash. Cluster fault tolerance: failover, failfast, failsafe, failback, forking, broadcast, available, zone-aware. Routing: condition and tag rules, dynamic configuration rules. Filters |
| Protocols | Triple (HTTP/2, compatible with gRPC), with health checks and reflection; Dubbo. TLS and mutual TLS; gzip, deflate and bzip2 compression |
| Serialization | Protobuf, Hessian 2 |
| Runtime | asyncio, uvloop optional; Python 3.11 to 3.14 on Linux, macOS and Windows |

## Installation

```shell
pip install apache-dubbo
```

Or with [uv](https://docs.astral.sh/uv/):

```shell
uv add apache-dubbo
```

The default installation serves and calls over both protocols. Extras add
optional parts, such as `pip install "apache-dubbo[zookeeper]"`:

| Extra | Adds |
|---|---|
| `zookeeper` | ZooKeeper registry, configuration center and metadata report |
| `nacos` | Nacos registry, configuration center and metadata report |
| `yaml` | YAML configuration files |
| `properties` | `.properties` configuration files |
| `uvloop` | [uvloop](https://github.com/MagicStack/uvloop), which an application runs on with `uvloop.run(main())`; not on Windows |
| `protoc` | `grpcio-tools`, to generate contracts from `.proto` files |

## Quick start

A service is declared once as a contract, which both sides import.
`greeter.py`:

```python
import typing

import dubbo


@dubbo.service("org.apache.dubbo.samples.Greeter")
class Greeter(typing.Protocol):
    async def greet(self, name: str) -> str: ...
```

The provider implements the contract and serves it over the Dubbo protocol.
`server.py`:

```python
import asyncio

from dubbo import Dubbo
from dubbo.config import ApplicationConfig, ProtocolConfig

from greeter import Greeter


class GreeterImpl(Greeter):
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"


async def main() -> None:
    app = Dubbo(
        application=ApplicationConfig(name="greeter-server"),
        protocols={"dubbo": ProtocolConfig(port=20880)},
    )
    app.export(GreeterImpl())

    async with app:
        await app.serve_forever()


asyncio.run(main())
```

The consumer refers to the contract and calls it like a local object.
`client.py`:

```python
import asyncio

from dubbo import Dubbo

from greeter import Greeter


async def main() -> None:
    app = Dubbo()
    greeter = app.refer(Greeter, url="dubbo://127.0.0.1:20880")

    async with app:
        print(await greeter.greet("Dubbo"))


asyncio.run(main())
```

Run `python server.py`, then `python client.py` in another terminal:

```console
$ python client.py
Hello, Dubbo!
```

To discover the provider through a registry instead of its address, install
`apache-dubbo[zookeeper]`, give both applications a name and the registry,
and drop the `url` of `refer`:

```python
from dubbo.config import ApplicationConfig, RegistryConfig

app = Dubbo(
    application=ApplicationConfig(name="greeter-client"),
    registries={"default": RegistryConfig(address="zookeeper://127.0.0.1:2181")},
)
greeter = app.refer(Greeter)
```

## Learn more

- [Samples](https://github.com/apache/dubbo-python/tree/main/samples): step by step, from a first call to streaming,
  registries and traffic management; working with Java, Go and gRPC; and
  using Dubbo with other Python libraries.
- [Dubbo documentation](https://dubbo.apache.org/): the concepts shared by
  every Dubbo language.
- [Contributing](https://github.com/apache/dubbo-python/blob/main/CONTRIBUTING.md): development setup, checks and
  conventions.

## Community

- **Issues and feature requests**: this repository has no issue tracker of
  its own; open them in the
  [Apache Dubbo issue tracker](https://github.com/apache/dubbo/issues) and
  say that they concern Dubbo for Python.
- **Questions and discussion**: the
  [dev@dubbo.apache.org](mailto:dev@dubbo.apache.org) mailing list
  ([how to subscribe](https://github.com/apache/dubbo/wiki/Mailing-list-subscription-guide)).
- **Security vulnerabilities**: report them privately to
  [security@dubbo.apache.org](mailto:security@dubbo.apache.org), not in
  public.

## License

Apache Dubbo for Python is licensed under the [Apache License 2.0](https://github.com/apache/dubbo-python/blob/main/LICENSE).
