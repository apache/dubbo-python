# FastAPI

A web application often fronts services: it takes HTTP requests and calls
the services behind it, which call others in turn. This sample is a small
shop: a [FastAPI](https://fastapi.tiangolo.com/) gateway takes orders over
HTTP, an orders service checks each with the users and the inventory
services, and each failure along the way becomes the HTTP status that fits it.

```
             HTTP                Triple                Triple
  client ─────────▶ app.py ─────────────▶ orders.py ──────────▶ backend.py
                    gateway               Orders       ├──────▶ Users
                                                       └──────▶ Inventory
```

## What you will learn

- how to run a Dubbo application for as long as a FastAPI application runs;
- how services find each other through a registry;
- how to pass Python dataclasses and several parameters over Triple;
- how one service calls two others at once;
- how a trace id travels from an HTTP request through every service;
- how timeouts at each step and the statuses of failed calls become HTTP
  statuses;
- why a call that changes something is not attempted again.

## Before you start

```console
$ pip install "apache-dubbo[zookeeper]" fastapi uvicorn
$ docker compose -f ../../compose.yaml up -d --wait
```

## The files

| File | Role |
|---|---|
| `shop.py` | The contracts of the three services, their types, and the settings every process shares |
| `backend.py` | The Users and Inventory services, in one application, on port 50051 |
| `orders.py` | The Orders service, on port 50052: it calls Users and Inventory |
| `app.py` | The gateway: a FastAPI application that calls Users and Orders |

## Run it

From this directory, start each in its own terminal, in this order:

```console
$ python backend.py
Serving users and inventory on port 50051; press Ctrl+C to stop
```

```console
$ python orders.py
Serving orders on port 50052; press Ctrl+C to stop
```

```console
$ uvicorn app:app
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Then place an order:

```console
$ curl -i -X POST localhost:8000/orders -H 'content-type: application/json' \
    -d '{"user_id": 1, "item": "book", "quantity": 2}'
HTTP/1.1 200 OK
x-trace-id: 82b25943

{"id":1,"user":"Alice","item":"book","quantity":2,"total":25.0}
```

Each service prints the calls it serves under the trace id of the request:

```console
[82b25943] place_order(1, 'book', 2)
```

```console
[82b25943] get_user(1)
[82b25943] get_item('book')
```

Orders that fail answer with the status that says why:

| Request | Answer |
|---|---|
| `{"user_id": 9, "item": "book", "quantity": 1}` | `404 Not Found`: `no user has ID 9` |
| `{"user_id": 1, "item": "sofa", "quantity": 1}` | `404 Not Found`: `the shop sells no sofa` |
| `{"user_id": 1, "item": "lamp", "quantity": 5}` | `409 Conflict`: `only 2 lamp left` |
| `{"user_id": 1, "item": "book", "quantity": 0}` | `400 Bad Request`: `an order is of one item or more` |
| `{"user_id": 2, "item": "piano", "quantity": 1}` | `504 Gateway Timeout`: `get_item did not complete within 1.0 seconds` |

Stop `backend.py` and place an order again: it fails with `503 Service
Unavailable`, and `orders.py` prints it once.

`GET /users/1` calls the Users service from the gateway directly.

## How it works

### The gateway and its lifespan

A Dubbo application runs while `async with` holds it, and must be entered and
left in the same task. FastAPI's `lifespan` does exactly that: it is entered
when the server starts and left when it stops, in one task, and requests are
served in between. So `lifespan` holds the Dubbo application with
`async with dubbo_app`, and routes call the references created next to it.
When uvicorn stops on Ctrl+C, it exits the lifespan, which stops the Dubbo
application gracefully, as in
[07_graceful_shutdown](../../basics/07_graceful_shutdown).

### Finding each other

Every application registers what it serves in ZooKeeper and finds what it
calls there, so no process names the address of another: `refer(Users)`
names only the service. Start a second backend on another port, with
`DUBBO__PROTOCOLS__TRI__PORT=50061 python backend.py`, and the orders service
spreads its calls over both.

### Python types over Triple

The contracts in `shop.py` are Python classes whose methods take several
parameters and return dataclasses. Protobuf, the default serialization of
Triple, carries one message per call; Hessian 2 carries any of these. The
providers set `serialization="hessian2"`, and publish it in the registry,
where their consumers take it.

Hessian 2 sends an object under a Java class name, which
`@hessian2.java_class` gives each dataclass; Python services only need to
agree on it, and Java or Go services read the object as that class.

Triple rather than the Dubbo protocol, because over Triple the status of a
failed call reaches its caller as it was raised, and its deadline travels
with it. Over the Dubbo protocol, statuses that Java does not know arrive as
`UNKNOWN`, as [08_errors_and_timeouts](../../basics/08_errors_and_timeouts)
tells.

### Two calls at once

`place_order` needs the user and the item, which do not depend on each other,
so it awaits both with `asyncio.gather`. The first to fail fails the order:
its `RpcError`, raised in the handler, reaches the gateway with its status.

### The trace id

A middleware of the gateway takes the `x-trace-id` header of the request, or
makes one, and wraps the request in `dubbo.outgoing({"trace-id": ...})`, so
every Dubbo call made for it attaches the trace id. The orders service reads
it with `dubbo.incoming()`, and the calls it makes while serving pass it on
by themselves, as in [09_context](../../basics/09_context).
[06_logging](../../basics/06_logging) puts it into every log record.

### Timeouts and statuses

Each step has its budget: a request may take 2 seconds at the gateway, and
each call of the orders service 1 second. Counting a piano takes 3, so the
orders service gives up on it, and the gateway answers `504`. Over Triple,
the inventory service learns that its caller gave up, and stops counting.

An exception handler of the gateway turns the status of a failed call into
an HTTP status: `NOT_FOUND` into 404, `FAILED_PRECONDITION` into 409,
`INVALID_ARGUMENT` into 400, `UNAVAILABLE` into 503 and `DEADLINE_EXCEEDED`
into 504; any other into 502.

### Not twice

When a call fails as `UNAVAILABLE`, the default `failover` cluster attempts
it again, as [11_load_balancing](../../basics/11_load_balancing) shows. That
is right for reads such as `get_user`, but an order attempted again may be
placed twice, so the gateway refers to Orders with `retries=0`.

## Next

- [Samples](../..): the other samples.
