# Load balancing and fault tolerance

A service usually has several providers. For each call, a load balance
chooses one of them, and a cluster decides what a failed attempt leads to.
This sample calls three providers, a fast one, a slow one and an overloaded
one, with different choices of both.

## What you will learn

- how to choose the load balance of a reference;
- how `roundrobin` and `leastactive` spread calls;
- how the `failover` and `failfast` clusters handle a failing provider.

## Run it

From this directory, start the server, which runs the three providers:

```console
$ python server.py
Serving on ports 20880, 20881 and 20882; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
roundrobin: fast 3, slow 3
leastactive: fast 31, slow 9
failover: fast 6
failfast: UNAVAILABLE 3, fast 3
```

The counts of `leastactive` vary from run to run.

## How it works

The client lists the providers of each reference in `ReferenceConfig(urls=...)`,
given to `refer`;
with a registry, they would come from it. `loadbalance` and `cluster` are
settings of the consumer, of one reference, or, for `loadbalance`, of one
method, in code or in [configuration files](../05_configuration).

### Load balances

| Name | Chooses |
|---|---|
| `random` (default) | At random, in proportion to the weights of the providers |
| `roundrobin` | Each provider in turn, in proportion to their weights |
| `leastactive` | The provider with the fewest calls under way, so slow providers get fewer |
| `consistenthash` | The same provider for the same first argument, as for a cache |

Here `roundrobin` alternates between the fast and the slow provider, while
`leastactive`, with eight calls at a time, sends most calls to the fast one:
calls finish there sooner, so it has fewer under way.

### Clusters

| Name | On a failed attempt |
|---|---|
| `failover` (default) | Attempts the call again on another provider, up to `retries` times, when the attempt failed as `UNAVAILABLE` |
| `failfast` | Fails the call at once |
| `failsafe` | Returns `None` instead of failing, and logs the failure |
| `failback` | Returns `None`, and makes the call again in the background |
| `forking` | Calls several providers at once and takes the first answer |
| `broadcast` | Calls every provider in turn, and fails if any fails |
| `available` | Calls the first available provider, without a load balance |
| `zone-aware` | With several registries, calls through the preferred one, or that of the zone the call names |

Here the overloaded provider rejects every call. With `failover`, each
rejected attempt is made again on the fast provider, and every call
succeeds. With `failfast`, the calls that went to the overloaded provider
fail, and the caller handles the error.

`failover` is right for calls that can be repeated safely, such as reads.
For a call that must not happen twice, such as a payment, use `failfast`, or
set `retries` to 0.

## Next

- [12_config_center](../12_config_center): keep configuration in a
  configuration center, and change it while applications run.
