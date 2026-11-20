# Routing

Routers narrow the providers a call may go to, before the load balance
chooses one: test traffic to a new release, the calls of some users to some
instances. This sample routes by tags, given by configuration and by a rule,
and by a condition rule, while the applications run.

## What you will learn

- how an instance gets a tag, from its configuration or from a rule, and how
  a call asks for one;
- how a condition rule sends some calls to some providers;
- how routing rules are published in the configuration center, and apply at
  once.

## Before you start

```console
$ pip install "apache-dubbo[zookeeper]"
$ docker compose -f ../../compose.yaml up -d --wait
```

## Run it

From this directory, start the server, which runs three instances of one
application: `stable-1`, `stable-2`, and `gray`, a new release that its
configuration tags `gray`:

```console
$ python server.py
Serving stable-1, stable-2 and gray; press Ctrl+C to stop
```

In another terminal, run the client, which prints the instances that
answered its calls:

```console
$ python client.py
Bob: stable-1, stable-2
Alice: stable-1, stable-2
Bob, tagged gray: gray
Bob, tagged canary: stable-1, stable-2
```

Publish a condition rule that sends the calls for Alice to `stable-1`, and
run the client again:

```console
$ python publish.py condition
$ python client.py
Bob: stable-1, stable-2
Alice: stable-1
Bob, tagged gray: gray
Bob, tagged canary: stable-1, stable-2
```

Publish a tag rule that tags `stable-2` `canary`, and run the client again:

```console
$ python publish.py tag
$ python client.py
Bob: stable-1
Alice: stable-1
Bob, tagged gray: gray
Bob, tagged canary: stable-2
```

Remove the rules with `python publish.py clear`.

## How it works

### Tags

A call asks for a tag with the `dubbo.tag` attachment, as the client does
inside `dubbo.outgoing({"dubbo.tag": "gray"})`, or for all its calls with
`ReferenceConfig(tag=...)`. It goes to the instances of that tag, or, when
none has it, to the untagged ones; a call that asks for none goes to the
untagged only. So a new release runs beside the old one and receives only
the traffic marked for it.

An instance gets a tag in two ways:

- **from its configuration**: `ProviderConfig(tag="gray")`, or
  `ServiceConfig` for one service, publishes the tag with its address. A
  deployment usually sets it outside the code, as with
  `DUBBO__PROVIDER__TAG=gray`, as Dubbo Java does with
  `dubbo.provider.tag`;
- **from a rule**: `{provider application}.tag-router` in the configuration
  center tags instances by address while they run, as `publish.py tag` does
  for `stable-2`. An instance tagged by a rule no longer takes untagged
  calls.

### Conditions

A condition rule reads `which calls => which providers`. The rule in
`publish.py` sends the calls whose first argument is `Alice` to the provider
on port 20880. The left side matches the call, by `method`, `arguments[i]`
or `attachments[key]`; the right side matches the URLs of providers, by
`host`, `port` or their parameters. `force: true` fails a call that no
provider matches, where `false` would ignore the rule for it.

The rule of one service is under `{service}:{version}:{group}.condition-router`;
rules can also apply to all the services of an application.

### Rules

Consumers watch the rules and apply a change at once. The rules are in the
format of Dubbo's routing rules, so the same entries apply to Java and Go
consumers, and consoles such as Dubbo Admin write them; `publish.py` writes
them with kazoo directly.

## Next

- [14_filters](../14_filters): run code around every call.
