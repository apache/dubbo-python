# Extensions

Every protocol, registry, load balance, router, filter and configuration
format of the framework is an extension, found by name among the installed
packages. A package of your own can add one. This sample adds a format,
TOML, as a plugin that any application can install.

## What you will learn

- how the framework finds extensions through entry points;
- how to package an extension so that installing it is enough;
- which extension points there are.

## The files

| File | Role |
|---|---|
| `dubbo-toml/dubbo_toml.py` | The extension: a configuration parser for TOML |
| `dubbo-toml/pyproject.toml` | The package, which declares the extension as an entry point |
| `server.toml` | The configuration of the server, in TOML |
| `server.py`, `client.py`, `greeter.py` | The provider, which reads `server.toml`, its consumer, and their contract |

## Run it

Before the plugin is installed, the server cannot read its configuration:

```console
$ python server.py
dubbo.config.exceptions.ConfigReadError: cannot load configuration parser 'toml' for '.../server.toml'
```

From this directory, install the plugin, then start the server:

```console
$ pip install -e ./dubbo-toml
$ python server.py
extensions-server serving on port 20880; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
Hello, Alice!
Hello, Bob!
```

## How it works

An extension point is a contract of the framework, such as `ConfigParser`,
with an entry point group, such as `apache_dubbo.config.parser`. An
extension is a class that implements the contract, installed under that
group with a name:

```toml
[project.entry-points."apache_dubbo.config.parser"]
toml = "dubbo_toml:TomlParser"
```

When the configuration needs the parser for a `.toml` file, the framework
looks up the name `toml` in the group, imports `dubbo_toml`, and creates a
`TomlParser`. Nothing else names the plugin: installing the package is
enough, and the plugin is imported only when it is first needed.

The other extension points work the same way:

| Group | Contract | Selected by |
|---|---|---|
| `apache_dubbo.filter` | `dubbo.filter.Filter` | `filters` of a provider, service, consumer or reference |
| `apache_dubbo.loadbalance` | `dubbo.cluster.LoadBalance` | `loadbalance` |
| `apache_dubbo.cluster` | `dubbo.cluster.Cluster` | `cluster` |
| `apache_dubbo.router` | `dubbo.cluster.Router` | `routers` of a consumer or reference |
| `apache_dubbo.interface_registry`, `apache_dubbo.instance_registry` | `dubbo.registry` contracts | the scheme of a registry address |
| `apache_dubbo.config_center` | `dubbo.config_center.ConfigCenter` | the scheme of a configuration center address |
| `apache_dubbo.metadata_report` | `dubbo.metadata` contract | the scheme of a metadata report address |
| `apache_dubbo.protocol` | `dubbo.protocol.Protocol` | the name of a protocol |
| `apache_dubbo.serialization` | `dubbo.serialization.Serialization` | `serialization` |
| `apache_dubbo.compression` | `dubbo.compression.Compressor` | the compressor of Triple |
| `apache_dubbo.config.parser` | `dubbo.config.ConfigParser` | the suffix of a configuration file |
| `apache_dubbo.transport.*` | The clients of ZooKeeper, Nacos and HTTP/2 under the extensions above | a parameter of their URL, else the default |

The docstring of each contract says what an implementation does. For one
application, `dubbo.extension.extensions.register()` registers an extension
in code instead, as [14_filters](../14_filters) does.

## Next

- [16_tls](../16_tls): secure calls with TLS, and compress them.
