# Registry

In production, consumers do not know the addresses of providers: providers
register with a registry, and consumers discover them there, following them
as they start and stop. This sample uses ZooKeeper, then Nacos.

## What you will learn

- how a provider registers its services with a registry;
- how a consumer discovers providers without knowing their addresses;
- how calls spread across several providers;
- the two ways Dubbo registers, per service and per application;
- how to switch between ZooKeeper and Nacos.

## Before you start

Install the client of the registry you use:

```console
$ pip install "apache-dubbo[zookeeper]"    # or "apache-dubbo[nacos]"
```

and start the registries, from the `samples` directory:

```console
$ docker compose -f compose.yaml up -d --wait
```

## Run it

From this directory, start two servers on different ports. The second one
sets its port through an environment variable, which overrides the
configuration in the code; [05_configuration](../05_configuration) explains
how.

```console
$ python server.py
Serving and registered; press Ctrl+C to stop
```

```console
$ DUBBO__PROTOCOLS__DUBBO__PORT=20881 python server.py
Serving and registered; press Ctrl+C to stop
```

Then run the client:

```console
$ python client.py
Hello, Alice! (from server 85651)
Hello, Bob! (from server 85652)
Hello, Carol! (from server 85651)
Hello, Dave! (from server 85651)
```

The replies come from both servers; the numbers are their process IDs. Stop
one server and run the client again: all calls go to the other one.

To use Nacos instead, set the registry address the same way for every
process:

```console
$ export DUBBO__REGISTRIES__DEFAULT__ADDRESS=nacos://127.0.0.1:8848
```

## How it works

Both sides add a registry to their configuration. The scheme of its address,
`zookeeper://` or `nacos://`, selects the registry.

When the server starts, it registers its address with the registry. When it
stops, it first removes the address, then keeps serving for 3 seconds, so
that consumers notice and send their calls elsewhere; that is why stopping
takes a moment.

The client calls `app.refer(Greeter)` without a URL, so the application
looks the providers up in the registry and watches them. Starting waits up
to 3 seconds for a provider and fails if none is found. Each call then goes
to one provider, chosen at random by default.

## Two ways to register

Dubbo registers providers in two ways:

- **per service**, or interface level, as Dubbo 2 does: one URL for each
  service of each provider. Simple, but the registry holds as many entries
  as services times instances;
- **per application**, or application level, as Dubbo 3 does: one entry for
  each instance of an application, and a mapping from each service to the
  applications that provide it. Consumers read the services of an instance
  from its metadata. The registry stays small however many services there
  are.

By default a provider registers both ways, so that consumers of either
kind, in any language, find it, and a consumer calls the providers it finds
per application while there are any, else those it finds per service. The
`mode` of a registry selects one way: `"interface"`, `"instance"` or `"all"`.

`show_registry.py` shows what the servers have registered in ZooKeeper.
Start a server in each mode and look:

```console
$ DUBBO__REGISTRIES__DEFAULT__MODE=interface python server.py
```

```console
$ python show_registry.py
Providers of org.apache.dubbo.samples.Greeter, registered per service:
   dubbo://127.0.0.1:20880/org.apache.dubbo.samples.Greeter
Instances of registry-server, registered per application:
Applications that provide org.apache.dubbo.samples.Greeter: registry-server
```

With `instance`, the providers list is empty and the instance
`127.0.0.1:20880` appears instead. The mapping stays after the servers
stop, since it says which applications provide a service rather than which
instances run. The client finds the server in every mode, since it
discovers both ways too. In code, the mode is a field:
`RegistryConfig(address=..., mode=RegistryMode.INSTANCE)`.

### Where the metadata is

Per application, a consumer learns which services an instance provides, and
on which protocols, from its metadata. By default an instance serves its own
metadata through a built-in `MetadataService`, which consumers call:
`metadata_type` `local`. With `remote`, the instance writes its metadata to
the registry, or to a separate metadata report, and consumers read it there:

```console
$ DUBBO__APPLICATION__METADATA_TYPE=remote DUBBO__REGISTRIES__DEFAULT__MODE=instance python server.py
```

The metadata then appears under `/dubbo/metadata/registry-server`, one entry
per revision. `remote` spares consumers a call to each new instance, at the
cost of entries in the registry; `local` keeps the registry small. Dubbo
Java reads both; Dubbo Go 3.3.2 reads only `local`, since it looks for
remote metadata under another path in ZooKeeper.

## Next

- [05_configuration](../05_configuration): keep the configuration in a file
  and override it from the environment.
