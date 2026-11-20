# Context

Some data belongs to a whole request rather than to one method: a trace ID,
the user it acts for, a tenant. Attachments carry it beside the arguments,
as headers do in HTTP, along a chain of services. This sample sends a trace
ID and a user through two services.

## What you will learn

- how a consumer attaches data to its calls with `dubbo.outgoing()`;
- how a provider reads the call it serves with `dubbo.incoming()`;
- how attachments pass along a chain of calls on their own;
- how a provider attaches data to its reply.

## The files

| File | Role |
|---|---|
| `services.py` | The contracts of the two services |
| `inventory_server.py` | The inventory provider, on port 20881 |
| `order_server.py` | The order provider, on port 20880, which calls the inventory |
| `client.py` | The consumer, which places an order |

## Run it

From this directory, start the inventory server, then the order server, each
in its own terminal:

```console
$ python inventory_server.py
Serving on port 20881; press Ctrl+C to stop
```

```console
$ python order_server.py
Serving on port 20880; press Ctrl+C to stop
```

Then run the client:

```console
$ python client.py
Ordered 2 x book
Served by order-server
```

Both servers print the trace ID and the user, though only the client set
them:

```console
[trace 4bf92f35] Order from alice at 127.0.0.1:49515
```

```console
[trace 4bf92f35] Reserving 2 x book for alice
```

## How it works

`with dubbo.outgoing({...}) as call:` adds attachments to every call made in
the block. Keys are text; values are printable ASCII text, or bytes under a
key that ends in `-bin`. After the block, `call.response_attachments` holds
what the provider of the last call attached to its reply.

In a handler, `dubbo.incoming()` returns the call being served:
`attachments` holds what the caller sent, `peer` where it called from, and
`response_attachments` what goes back with the reply.

While a handler serves a call, the calls it makes send on the attachments
it received, so the trace ID reaches the inventory service without the order
service passing it. Attachments that concern one call only are not passed
on: the identity of the service called, `timeout`, `token`, `dubbo.tag`, and
HTTP fields such as `authorization`. `dubbo.outgoing(..., inherit=False)`
starts a block from nothing.

Attachments are part of the Dubbo protocols, so Java and Go services read and
send them too: they are what Dubbo Java calls the attachments of
`RpcContext`, and over Triple they travel as gRPC metadata.

## Next

- [10_group_version](../10_group_version): run several versions of a service
  side by side.
