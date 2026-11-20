# Filters

A filter runs code around every call, on the consumer, the provider, or
both: authentication, metrics, logging, rate limits. This sample checks an
API key and times the calls a provider serves.

## What you will learn

- how to write a filter, and register it by name;
- how a service and a reference choose their filters, and in which order
  they run;
- how a filter reads its settings, changes a call, and fails it.

## Run it

From this directory, start the server:

```console
$ python server.py
Serving on port 20880; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
With the key: Hello, Alice!
Without: PERMISSION_DENIED: a valid API key is required
```

The server logs both calls, timed by its filter:

```console
INFO filters: org.apache.dubbo.samples.Greeter.greet succeeded in 0.0 ms
INFO filters: org.apache.dubbo.samples.Greeter.greet failed in 0.0 ms
```

## How it works

### Writing a filter

A filter, in `filters.py`, is a class with two methods:

- `__init__(url)`, called with the URL of the service or reference it runs
  around. It reads its settings there once, such as the `api-key` parameter;
- `async invoke(call_next, invocation)`, called for each call. It may change
  the invocation, such as its attachments, then call `call_next` to go on,
  and change the result it returns. To fail the call, it returns
  `Result(error=RpcError(...))` without going on.

A filter keeps no state across calls of its own, since it may be created
again when rules change the URL.

`extensions.register(Filter, "timing", TimingFilter)` gives the filter a
name, which configuration then uses; the sample does it in
`filters.register()`, which the client and the server call before they
configure the filters. A filter meant for many applications is
installed as a package instead; [15_extensions](../15_extensions) shows how.

### Choosing filters

| Where | Setting | Runs around |
|---|---|---|
| Provider | `ProviderConfig(filters=...)`, or `ServiceConfig` for one service | Each call it serves, where `dubbo.incoming()` works |
| Consumer | `ConsumerConfig(filters=...)`, or `ReferenceConfig` for one service | Each call, once whatever the retries |
| Consumer | `attempt_filters` of the same | Each attempt, on the provider it goes to |

The first filter of a list is the outermost, so `("timing", "api-key-check")`
times the check as well. `parameters` reach the URL the filters are created
with.

### Built in

The framework has filters of its own, which settings turn on: `token` for a
shared secret like the one here, `accesslog`, `executes` and `tps` for
limits on a provider, and `actives` on a consumer. Use those when they fit.

## Next

- [15_extensions](../15_extensions): add an extension of your own as an
  installable plugin.
