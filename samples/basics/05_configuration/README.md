# Configuration

Keep the configuration out of the code: in files that describe each
application, with defaults for all its services, settings for one service or
one method, and environment variables that override them where the
application is deployed.

## What you will learn

- how an application reads its configuration from a YAML file;
- how the sections of the file map to the configuration classes;
- how settings go from defaults, to one service, to one method;
- how a provider's settings reach its consumers through the registry;
- how environment variables override a file;
- how to see what the framework logs.

## Before you start

YAML files need the `yaml` extra, and the registry the `zookeeper` extra:

```console
$ pip install "apache-dubbo[yaml,zookeeper]"
```

Start ZooKeeper, from the `samples` directory:

```console
$ docker compose -f compose.yaml up -d --wait
```

## Run it

From this directory, start the server:

```console
$ python server.py
INFO dubbo.accesslog: ...
configuration-server serving on port 20880
```

In another terminal, run the client:

```console
$ python client.py
Hello, Alice!
Hello... Bob!
```

The server logs each call:

```console
INFO dubbo.accesslog: org.apache.dubbo.samples.Greeter greet OK 0.0ms
INFO dubbo.accesslog: org.apache.dubbo.samples.Greeter greet_slowly OK 2002.5ms
```

Now stop the server and start it with two environment variables:

```console
$ DUBBO__APPLICATION__NAME=renamed DUBBO__PROTOCOLS__DUBBO__PORT=20881 python server.py
renamed serving on port 20881
```

## How it works

### The file

`Dubbo(HERE / "server.yaml")` reads the file by the parser its suffix selects:
`.yaml` or `.yml`, `.json`, or `.properties` with the `properties` extra.
Each top-level section is a configuration class of `dubbo.config`, and each
key one of its fields:

| Section | Class | Holds |
|---|---|---|
| `application` | `ApplicationConfig` | The identity of the application |
| `protocols` | `ProtocolConfig`, by name | What the application serves on |
| `registries` | `RegistryConfig`, by name | Where it registers and discovers |
| `provider` | `ProviderConfig` | Defaults for the services it provides |
| `consumer` | `ConsumerConfig` | Defaults for the services it calls |
| `shutdown` | `ShutdownConfig` | How it stops |

The same file in code is
`Dubbo(application=ApplicationConfig(name="configuration-server", ...), ...)`.

### From defaults to one method

Settings narrow in three steps. `provider` holds the defaults of every
service; `provider.services` overrides them for one service, by its name;
and `methods` under it for one method. `consumer`, `consumer.references`
and their `methods` do the same on the calling side.

A method is named as it is called on the wire, the name that Java and Go
use too: that of the Python method, unless `@dubbo.method` gives another,
and for a contract generated from a `.proto` file, the name in the file,
such as `ExportUsers` in [08_errors_and_timeouts](../08_errors_and_timeouts).

Here the provider allows every call 1 second, but `greet_slowly` 5. The
client sets no timeout: a consumer takes the timeout the provider registered,
and calls `greet_slowly`, which takes 2 seconds, without failing. A timeout
the consumer sets itself would take precedence. The client does set
`retries: 0` for `greet_slowly`, since a slow call is not worth making again
on another provider.

### Environment variables

An environment variable that starts with `DUBBO__` sets one key: `__`
separates the levels, so `DUBBO__PROTOCOLS__DUBBO__PORT` sets
`protocols.dubbo.port`. A value in JSON, such as `["a", "b"]`, sets a list or
a mapping. Keys that hold dots, such as service names, cannot be written
this way; keep them in files.

### Layers

The configuration is read when the application starts, in layers from low
to high:

1. the sources passed to `Dubbo`, in order: files or mappings;
2. the configuration center, when one is configured;
3. environment variables starting with `DUBBO__`;
4. the keyword arguments of `Dubbo`, and the `url` of `refer()`.

A higher layer overrides only the keys it sets. `app.config` holds the
result once the application has started.

### Logging

The framework logs through the standard `logging` module, under loggers
named `dubbo.*`, and leaves the setup to the application. `server.py` calls
`logging.basicConfig()` to see them; `accesslog: true` logs each call at
INFO under `dubbo.accesslog`. [06_logging](../06_logging) shows how to
write them as structured lines.

## Next

- [06_logging](../06_logging): structured logs with the trace id of each
  call, written off the event loop.
