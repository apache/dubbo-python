# Samples

Small programs that each teach one thing about Apache Dubbo for Python, from a
first call to running beside other frameworks. Each sample has a README that
says what it shows, how to run it, and what you will see.

## Before you start

Install Apache Dubbo for Python:

```console
$ pip install apache-dubbo
```

A sample that needs more, such as an extra, says so in its README. The
samples that use a registry or a configuration center need ZooKeeper or
Nacos; start both with Docker, from this directory:

```console
$ docker compose -f compose.yaml up -d --wait
```

Run every sample from its own directory, the server first, then the client in
another terminal.

## Basics

Using the framework on its own, in order:

| Sample | What it shows |
|---|---|
| [01_hello_world](basics/01_hello_world) | A contract, a provider and a consumer, with Python types over the Dubbo protocol |
| [02_protobuf](basics/02_protobuf) | Contracts generated from a `.proto` file, over the Triple protocol |
| [03_streaming](basics/03_streaming) | Server, client and bidirectional streaming |
| [04_registry](basics/04_registry) | Finding providers through ZooKeeper or Nacos; registering per service and per application; local and remote metadata |
| [05_configuration](basics/05_configuration) | Configuration files from defaults to one method, and environment variables |
| [06_logging](basics/06_logging) | Structured logs with the trace id of each call, written off the event loop |
| [07_graceful_shutdown](basics/07_graceful_shutdown) | Opening resources with the application, and stopping without losing calls |
| [08_errors_and_timeouts](basics/08_errors_and_timeouts) | Statuses, timeouts and retries |
| [09_context](basics/09_context) | Attachments along a chain of services |
| [10_group_version](basics/10_group_version) | Several versions of a service side by side |
| [11_load_balancing](basics/11_load_balancing) | Load balances and clusters: how calls spread, and what a failure leads to |
| [12_config_center](basics/12_config_center) | Configuration from a configuration center, and rules that change running calls |
| [13_routing](basics/13_routing) | Tag and condition routing, by configuration and by rules |
| [14_filters](basics/14_filters) | Code around every call: an API key check and timing |
| [15_extensions](basics/15_extensions) | An extension of your own, installed as a plugin |
| [16_tls](basics/16_tls) | Mutual TLS and compression |
| [17_generic](basics/17_generic) | Calls without the contract of the service |

## Working with other languages

| Sample | What it shows |
|---|---|
| [interop/java](interop/java) | Python and Java calling each other through Nacos, over Triple with Protobuf and over Dubbo with Hessian 2 |
| [interop/go](interop/go) | Python and Go calling each other through Nacos, over Triple with Protobuf |
| [interop/grpc](interop/grpc) | gRPC clients calling Dubbo, Dubbo calling gRPC servers, health and reflection |

## Working with Python libraries

| Sample | What it shows |
|---|---|
| [integrations/fastapi](integrations/fastapi) | A small shop: a FastAPI gateway, services that call each other through a registry, a trace id along the chain, and the statuses of failed calls as HTTP statuses |
| [integrations/pydantic_ai](integrations/pydantic_ai) | An AI agent that plans restocking with the services of a company as its tools, and drafts orders once a person agrees |
