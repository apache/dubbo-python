# Configuration center

A configuration center keeps configuration in one place for many
applications, and lets operators change how services are called while they
run. This sample reads an application's configuration from ZooKeeper, then
changes a timeout with a rule, without restarting anything.

## What you will learn

- how an application reads its configuration from a configuration center;
- how override rules change calls while applications run;
- where the configuration center keeps its entries.

## Before you start

```console
$ pip install "apache-dubbo[zookeeper]"
$ docker compose -f ../../compose.yaml up -d --wait
```

## Run it

From this directory, publish the shared configuration:

```console
$ python publish.py config
Published /dubbo/config/dubbo/dubbo.yaml
```

Start the server:

```console
$ python server.py
Serving; registered with zookeeper from the configuration center
```

In another terminal, start the client. Its calls take 1.5 seconds, longer
than the 1 second a call may take, so they fail:

```console
$ python client.py
DEADLINE_EXCEEDED: greet did not complete within 1.0 seconds
DEADLINE_EXCEEDED: greet did not complete within 1.0 seconds
```

While it runs, publish a rule that gives calls of the Greeter 3 seconds, in
a third terminal:

```console
$ python publish.py rule
Published /dubbo/config/dubbo/org.apache.dubbo.samples.Greeter::.configurators
```

The next calls succeed, and the client stops after three:

```console
Hello, Alice!
Hello, Alice!
Hello, Alice!
```

Remove the entries with `python publish.py clear`.

## How it works

### Configuration from the center

The code of both applications names only their own name and the
configuration center, with `ConfigCenterConfig(address=...)`. At start, an
application reads the entry `dubbo.yaml` of the group `dubbo` from the
center, and takes the registry, the protocol and the provider settings from
it. The entry ranks above configuration files and below environment
variables and code, as [05_configuration](../05_configuration) shows.

A registry can serve as the configuration center too: an application with
a ZooKeeper or Nacos registry and no `config_center` uses its registry,
unless `use_as_config_center` is false.

### Rules

Override rules change the settings of calls while applications run. Each is
a YAML entry in the center, under the key `{service}:{version}:{group}.configurators`
for one service, or `{application}.configurators` for every service of an
application. Applications watch these keys and apply a rule as soon as it
changes. The rule here sets the `timeout` of consumers of the Greeter to
3000 milliseconds; others change the weight of a provider, disable it, or
apply only to some addresses.

The rules are in the format of Dubbo's override rules, so the same entry
applies to Java and Go applications, and consoles such as Dubbo Admin write
it. In ZooKeeper, the entries are under `/dubbo/config/{group}/{key}`; with
Nacos, they are configurations of the same group and data ID.

`publish.py` writes the entries with kazoo directly, as an operator's tool
would; the framework only reads them.

## Next

- [13_routing](../13_routing): route calls to some providers by rules.
