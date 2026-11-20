# Streaming

Besides a single request and reply, Triple carries streams of messages, in
either direction or both. This sample makes one call of each kind.

## What you will learn

- how a provider sends, receives, or does both on a stream;
- how a consumer holds a streaming call with `async with` and reads it with
  `async for`;
- when to use each kind of streaming.

## The three kinds

| Kind | Requests | Replies | Typical use |
|---|---|---|---|
| Server streaming | one | many | results as they become ready, progress, live updates |
| Client streaming | many | one | uploads, batches, aggregation |
| Bidirectional | many | many | chat, interactive sessions |

In `greeter.proto`, the keyword `stream` marks the streaming side of each
`rpc`.

## Run it

From this directory, start the server:

```console
$ python server.py
Serving on port 50051; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
Server streaming:
  Hello #1, Alice!
  Hello #2, Alice!
  Hello #3, Alice!
Client streaming:
  Hello, Alice, Bob, Carol!
Bidirectional streaming:
  Nice to meet you, Alice
  Nice to meet you, Bob
```

The generated files are included; [02_protobuf](../02_protobuf) shows how to
generate them again.

## How it works

On the provider, each streaming handler gets a stream argument:

- `greet_many_times` sends replies with `stream.send()`; the call ends when
  the handler returns;
- `greet_everyone` reads requests with `async for` until the caller ends
  them, then returns the reply;
- `chat` reads requests and sends replies on one stream.

On the consumer, a streaming method returns a call to hold with
`async with`. Leaving the block ends the call, and cancels it if it still
runs. A call sends with `send()`, says it has sent everything with `end()`,
and receives with `receive()` or `async for`.

A streaming call has no timeout of its own. Bound it with
`anyio.fail_after()`, whose deadline reaches the provider as well.

## Next

- [04_registry](../04_registry): find providers through a registry.
