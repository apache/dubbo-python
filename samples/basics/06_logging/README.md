# Logging

Turn the logs of Dubbo into the ones your application wants: one JSON line
per record, with the fields of each call and the trace id it carries,
written without holding up the event loop.

## What you will learn

- which loggers Dubbo logs to, and how to turn them up or down;
- the fields of each line of the access log;
- how to give each record the trace id of the call it was logged in;
- how to write logs from a thread instead of the event loop;
- how to render the same records with structlog or loguru.

## Before you start

```console
$ pip install apache-dubbo
```

Rendering with structlog also needs it:

```console
$ pip install structlog
```

## Run it

From this directory, start the server:

```console
$ python server.py
{"time": "2026-11-20T03:44:25.665+00:00", "level": "INFO", "logger": "greeter", "message": "Serving on port 20880; press Ctrl+C to stop", "trace_id": null}
```

In another terminal, run the client:

```console
$ python client.py
Hello, Alice!
Hello, Bob!
```

The server logs a line for each greeting and one for each call, each with
the trace id that the client attached:

```console
{"time": "...", "level": "INFO", "logger": "greeter", "message": "Greeting Alice", "user": "Alice", "trace_id": "4bf92f35"}
{"time": "...", "level": "INFO", "logger": "dubbo.accesslog", "message": "org.apache.dubbo.samples.Greeter greet OK 0.1ms", "service": "org.apache.dubbo.samples.Greeter", "group": null, "version": null, "method": "greet", "status": "OK", "duration_ms": 0.10, "trace_id": "4bf92f35"}
```

Start the server with `--structlog` to render the same records with
structlog.

## How it works

### The loggers of Dubbo

Dubbo logs through the standard `logging` module, to loggers under `dubbo`,
and leaves their handlers to the application: whatever the application sets
up for its own records applies to those of Dubbo. A level set on a logger
applies to those under it:

```python
logging.getLogger("dubbo").setLevel(logging.WARNING)  # only what goes wrong
logging.getLogger("dubbo.registry").setLevel(logging.DEBUG)  # more of one part
```

`accesslog=True`, of `ProviderConfig` or of one service, logs each call
that a provider serves, at INFO to `dubbo.accesslog`.

### Fields

Each record of the access log holds the values of its call as fields, so
that a formatter writes them as they are rather than parsing the message:

| Field | Value |
|---|---|
| `service` | The interface, such as `org.apache.dubbo.samples.Greeter` |
| `group`, `version` | Those of the service, `None` when it has none |
| `method` | The method called |
| `status` | The name of the status the call ended with: `OK`, `NOT_FOUND`, `CANCELLED`, ... |
| `duration_ms` | How long it took, in milliseconds |

Your own records get fields the same way, with `extra=`:
`logger.info("Greeting %s", name, extra={"user": name})`.

`JsonFormatter` in `logs.py` writes the attributes that every record has as
`time`, `level`, `logger` and `message`, and then every other attribute
of the record: those that `extra=` and filters gave it.

### The trace id

`TraceIdFilter` reads the attachments of the call being served with
`dubbo.incoming()`, and gives each record the `trace-id` the caller attached.
It runs on the handler, in the code that logs, and so inside the call; the
records of the access log are logged inside the call too. Outside a call,
the trace id is `None`.

### Off the event loop

A handler that writes to a terminal or a file writes as the code logs, and a
slow write holds up every call that the event loop runs. `logs.configure()`
puts a `QueueHandler` in front instead: it formats each record and puts it
on a queue, and a `QueueListener` writes the queue from a thread of its own.
Stop the listener at exit, so that it writes what the queue still holds.

Formatting still happens in the code that logs, and the filter must run
there to see the call; keep both cheap. When the access log is too much at
full load, turn `dubbo.accesslog` down to WARNING, or give the handler a
filter that keeps one record in a hundred.

### structlog

`structlog_logs.py` renders the same records with structlog's
`ProcessorFormatter`, which formats the records of the logging module, those
of Dubbo among them, as it formats its own; `ExtraAdder` adds their fields.
It takes the place of `JsonFormatter`, behind the same queue and filter.

### loguru

loguru receives the records of the logging module through a handler that
passes each on, with its fields bound:

```python
from loguru import logger

import logs


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        fields = {key: value for key, value in vars(record).items() if key not in logs._STANDARD}
        logger.bind(**fields).opt(exception=record.exc_info).log(record.levelname, record.getMessage())


handler = InterceptHandler()
handler.addFilter(logs.TraceIdFilter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger.remove()
logger.add(sys.stderr, serialize=True, enqueue=True)
```

`serialize=True` writes JSON with the fields under `extra`, and
`enqueue=True` writes from a thread, as the queue above does.

## Next

- [07_graceful_shutdown](../07_graceful_shutdown): open resources with the
  application, and stop without losing calls.
