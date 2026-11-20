# Graceful shutdown

A provider usually holds resources for its services, such as a database
pool, and must stop without failing the calls it is serving. This sample
opens a resource with the application and stops while a call runs.

## What you will learn

- how `lifespan` opens and closes what the services use, such as a service
  that is an async context manager itself;
- what the application does when it stops;
- how `shutdown.grace` bounds stopping.

## Run it

From this directory, start the server:

```console
$ python server.py
Database opened
Serving on port 20880; press Ctrl+C to stop
```

In another terminal, run the client. Its call takes 5 seconds; press Ctrl+C
in the server window while it runs:

```console
$ python client.py
Calling; press Ctrl+C in the server window now
Hello, Dr. Watson!
```

The server finishes the call before it closes the database:

```console
Greeting Watson...
Stopping; running calls finish first
Greeted Watson
Database closed
Stopped
```

## How it works

`Dubbo(..., lifespan=...)` takes a function that returns an async context
manager. The application enters it once it is ready and before the services
serve, and exits it after they have stopped serving, so services can rely on
what it opens for every call.

Here the service itself is that context manager: `GreeterImpl` opens its
database in `__aenter__` and closes it in `__aexit__`, and `lifespan` returns
it. A function decorated with `contextlib.asynccontextmanager` works as well,
and suits a lifespan that opens several resources for several services.
While the lifespan enters, the references of the application can already
call other applications.

Ctrl+C or SIGTERM ends `serve_forever()`. Leaving `async with app` then stops
the application in order:

1. it leaves the registries, and keeps serving for `shutdown.unregister_wait`
   seconds, 3 by default, so that consumers turn to other providers; without
   registries, as here, there is nothing to wait for;
2. it takes no new calls and waits for the running ones;
3. it exits the lifespan and closes its connections.

All of it takes at most `shutdown.grace` seconds, 10 by default and 15 here;
what still runs then is cancelled. A second Ctrl+C, or cancelling the task
that runs the application, stops at once.

The client sets `consumer.timeout` to 10 seconds, because a call may take 1
second by default and this one takes 5.

## Next

- [08_errors_and_timeouts](../08_errors_and_timeouts): handle failed calls,
  timeouts and retries.
