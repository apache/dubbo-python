# Go

Dubbo Go serves Triple with Protobuf, as Dubbo for Python does. A Python
service and a Go service share a `.proto` file and find each other in the
same registry. This sample runs a provider and a consumer in each language,
which find each other in Nacos.

## What you will learn

- how Python and Go share a contract in a `.proto` file, and generate their
  code from it;
- how statuses and attachments, such as a trace id, cross between the
  languages;
- how each side finds the other through a registry, with no addresses in
  the code.

## Before you start

You need Go 1.25 or later, and Nacos, as in
[04_registry](../../basics/04_registry):

```console
$ pip install "apache-dubbo[nacos]"
$ docker compose -f ../../compose.yaml up -d --wait
```

## The files

| File | Role |
|---|---|
| `proto/greeter.proto` | The contract of `Greeter`, which both languages generate code from |
| `greeter_pb2.py`, `greeter_pb2.pyi`, `greeter_dubbo.py` | The Python code generated from it, as in [02_protobuf](../../basics/02_protobuf) |
| `python_server.py`, `python_client.py` | The Python provider and consumer |
| `go/greeter/` | The Go code generated from it |
| `go/server/`, `go/client/` | The Go provider and consumer, in a Go module |

## Run it

### Python calls Go

From this directory, start the Go server:

```console
$ go -C go run ./server
Serving Greeter on port 50052; press Ctrl+C to stop
```

The first run downloads the dependencies, which takes a while. In another
terminal, run the Python client:

```console
$ python python_client.py
Hello, Alice, from Go!
Hello #1, Bob, from Go!
Hello #2, Bob, from Go!
Hello #3, Bob, from Go!
INVALID_ARGUMENT: a name is required
```

The Go server prints each call it serves, with the trace id that the Python
client attached:

```console
[py-4bf9] SayHello(Alice)
[py-4bf9] SayHello()
```

### Go calls Python

Stop the Go server with Ctrl+C, and start the Python server:

```console
$ python python_server.py
Serving Greeter on port 50051; press Ctrl+C to stop
```

In another terminal, run the Go client:

```console
$ go -C go run ./client
Hello, Alice, from Python!
Hello #1, Bob, from Python!
Hello #2, Bob, from Python!
Hello #3, Bob, from Python!
```

The Python server prints the trace id that the Go client attached:

```console
[go-1c9d] say_hello(Alice)
```

## How it works

### Finding each other

A consumer looks a service up by its name, and reads from the metadata of
each instance which protocol and port to call it on; neither side knows the
language of the other.

By default, Dubbo Go registers and finds providers per application only.
Python registers both per application and per service, and finds providers
per application while there are any, as
[04_registry](../../basics/04_registry) explains, so the two meet per
application with their defaults.

### One contract

`Greeter` is defined once, in `proto/greeter.proto`, and its name is the
package and service of the file: `org.apache.dubbo.samples.Greeter`.
`option go_package` only says where the Go code goes. Each language calls
and serves it as its own code: a `Recv()` loop in Go, `async for` in
Python.

The generated code of both languages is included. To generate the Go code
again, install the two plugins of protoc for Go, and run protoc from the Go
module, since `protoc-gen-go-triple` writes its file into the module of the
current directory:

```console
$ go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
$ go install github.com/dubbogo/protoc-gen-go-triple/v3@v3.0.3
$ cd go
$ protoc -I../proto --go_out=. --go_opt=module=interop --go-triple_out=. ../proto/greeter.proto
```

`python -m grpc_tools.protoc` from the `protoc` extra can stand for
`protoc`.

### Statuses

A Go handler fails with a status by returning
`triple_protocol.NewError(triple_protocol.CodeInvalidArgument, err)`, which
reaches Python as an `RpcError` of `INVALID_ARGUMENT`. An `RpcError` of a
Python handler reaches Go as an error with the same code.

Dubbo Go retries a failed call, by default twice, whatever its status;
Python retries only calls that fail as `UNAVAILABLE`.

### Attachments

Over Triple, attachments travel as headers of the call, so each language
reads what the other attached:

| | Attach to calls | Read in a handler |
|---|---|---|
| Python | `with dubbo.outgoing({"trace-id": ...}):` | `dubbo.incoming().attachments` |
| Go | `triple_protocol.AppendToOutgoingContext(ctx, "trace-id", ...)` | `triple_protocol.FromIncomingContext(ctx)` |

Both attach to every call made in their block or with their context. Header
names are case-insensitive, so keys in lower case read the same in both.

## Next

- [interop/grpc](../grpc): call Dubbo services from gRPC, and gRPC services
  from Dubbo.
