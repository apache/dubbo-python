# Errors, timeouts and retries

Calls fail: the request is wrong, the data is missing, the provider is busy
or slow. This sample fails calls in each of these ways and handles them.

## What you will learn

- how a provider fails a call with a status;
- how a consumer tells failures apart by their status;
- which failures are attempted again, and which are not;
- how to set timeouts per method, and bound a call further.

## Run it

From this directory, start the server:

```console
$ python server.py
Serving on port 50051; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
User 1: Alice
User 2: Bob
No user 42
Failed: INVALID_ARGUMENT: a user ID is not negative: -1
Exported 2 users
Gave up exporting after 1 second
```

The server prints the attempts it rejected as too busy.

## How it works

### Failing a call

A handler fails its call by raising `dubbo.RpcError` with a `Status`, the
codes gRPC defines, such as `NOT_FOUND` or `INVALID_ARGUMENT`, and a message.
The caller receives an `RpcError` of the same status and message, and checks
`error.status` to decide what to do. Any other exception that a handler
raises reaches the caller as `UNKNOWN`, and the provider logs it with its
traceback.

### Retries

Each call goes through a cluster, `failover` by default. When an attempt
fails with `UNAVAILABLE`, meaning that the provider could not take the call,
the cluster attempts it again, on another provider when there is one, up
to `retries` more times, 2 by default. Here the only provider rejects every
other attempt, and every call still succeeds.

Other statuses are not attempted again: the provider did take the call, and
it may have done part of the work. `DEADLINE_EXCEEDED` is not attempted
again either.

### Timeouts

A unary call may take 1 second by default; past that it fails with
`DEADLINE_EXCEEDED`. The client gives `ExportUsers` 5 seconds with a
`MethodConfig` in the `ReferenceConfig` it gives `refer`, keyed by the name
of the method in the proto file. The
timeout also applies per service, per reference or to all references, in
code or in [configuration files](../05_configuration).

`anyio.fail_after()` bounds the calls in its block further. Over Triple its
deadline travels with the call, so the provider stops working on a call
that its caller has given up on.

### Statuses and other languages

Over Triple, statuses are those of gRPC, and Java, Go and gRPC programs read
them as such. Over the Dubbo protocol, an `RpcError` travels as a Java
`org.apache.dubbo.rpc.RpcException`, which has codes for only some
statuses; the others arrive as `UNKNOWN`, with their message, in Python
consumers too. A service whose callers tell failures apart by their status
is served over Triple.

## Next

- [09_context](../09_context): send data along with calls, such as a trace
  ID or a user.
