# Hello world

Your first Dubbo service in Python: a contract, a server that implements it,
and a client that calls it, with no registry.

## What you will learn

- how a service contract is declared as a `typing.Protocol`;
- how a provider exports an implementation and serves it;
- how a consumer refers to a contract and calls it like a local object.

## The files

| File | Role |
|---|---|
| `greeter.py` | The contract that both sides import |
| `server.py` | The provider: implements `Greeter` and serves it on port 20880 |
| `client.py` | The consumer: calls the provider at `dubbo://127.0.0.1:20880` |

## Run it

From this directory, start the server:

```console
$ python server.py
Serving on port 20880; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
Hello, Alice!
Hello, Bob!
```

The server prints each name it greets. Stop it with Ctrl+C.

## How it works

`@dubbo.service` gives the contract its service name,
`org.apache.dubbo.samples.Greeter`. The type hints of its methods say what
travels on the wire.

The server creates a `Dubbo` application with one protocol, exports
`GreeterImpl`, and runs inside `async with app`. Leaving the block stops the
application gracefully.

The client creates its own application and calls `app.refer(Greeter, url=...)`,
which returns an object with the methods of `Greeter`. Each call goes over
the network to the server.

The Dubbo protocol carries Python values, such as `str`, `int`, `list` and
`dict`, in the Hessian 2 format, which Dubbo Java services read as well.

## Next

- [02_protobuf](../02_protobuf): define the contract in a `.proto` file and
  use the Triple protocol, which gRPC also speaks.
- [04_registry](../04_registry): let the client find the server through a
  registry instead of its address.
