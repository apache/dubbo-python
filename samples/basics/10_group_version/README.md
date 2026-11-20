# Group and version

One service may run in several forms at once: a new version beside the old
one while consumers move over, or one implementation per tenant or region.
The version and the group tell them apart. This sample runs two versions of
a service side by side.

## What you will learn

- how a provider registers a version of its services;
- how a consumer chooses the version it calls;
- what groups are for.

## Before you start

```console
$ pip install "apache-dubbo[zookeeper]"
$ docker compose -f ../../compose.yaml up -d --wait
```

## Run it

From this directory, start both versions, each in its own terminal:

```console
$ python server_v1.py
Serving version 1.0.0 on port 20880; press Ctrl+C to stop
```

```console
$ python server_v2.py
Serving version 2.0.0 on port 20881; press Ctrl+C to stop
```

Then call each version:

```console
$ python client.py
Version 1.0.0: Hello, Alice!
$ python client.py 2.0.0
Version 2.0.0: Good to see you, Alice!
```

A version that no provider registered fails at start:

```console
$ python client.py 3.0.0
dubbo.exceptions.RpcError: UNAVAILABLE: no provider of org.apache.dubbo.samples.Greeter is available; set check to false to start without one
```

## How it works

A service is identified by its name, its group and its version together.
`ProviderConfig(version=...)` sets the version of every service of a
provider, and `ServiceConfig(version=...)`, given to `export`, that of one
service. A consumer sets the version it calls with
`ConsumerConfig(version=...)`, or `ReferenceConfig(version=...)`, given to
`refer`, for one service, and discovers only the providers of that version.

So version 2.0.0 can be deployed while every consumer still calls 1.0.0,
then consumers move to it one by one, and version 1.0.0 stops once none
calls it.

The group works the same way, with `group=` beside `version=`, and keeps
apart implementations of one contract that are not versions of each other,
such as one per region or per tenant, or one for tests.

An application refers to a service once, so one application calls one
version of it. Over Triple, the group and the version travel with each call
in the `tri-service-group` and `tri-service-version` headers.

## Next

- [11_load_balancing](../11_load_balancing): choose how calls spread across
  providers, and what happens when one fails.
