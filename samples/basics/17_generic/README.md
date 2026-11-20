# Generic calls

A generic call names a service and a method as text, and passes plain data,
without the contract of the service. Gateways, consoles and test tools use
it to call any service, including services written later or in other
languages. This sample calls a user service that way.

## What you will learn

- how to refer to a service by its name, without its contract;
- how to call its methods by name with plain data;
- how generic calls reach Java providers.

## Run it

From this directory, start the server:

```console
$ python server.py
Serving on port 20880; press Ctrl+C to stop
```

In another terminal, run the client:

```console
$ python client.py
{'id': 1, 'name': 'Alice', 'email': 'alice@example.com'}
['Alice']
UNKNOWN: no user has ID 42
```

## How it works

`app.refer_generic("org.apache.dubbo.samples.Users", url=...)` returns a
`GenericService` for the service of that name. Its `call(method, *arguments)`
calls a unary method by its name on the wire, with the arguments in order,
and returns the result. Arguments and results are plain data: strings,
numbers, lists, and dicts for objects.

The provider needs nothing special: it serves generic calls of any of its
services. Settings, such as timeouts or a registry, apply as to a reference
of a contract.

The failure arrives as `UNKNOWN` rather than `NOT_FOUND`, since the Dubbo
protocol carries failures as Java's `RpcException`, which has no code for
it; [08_errors_and_timeouts](../08_errors_and_timeouts) explains why.

### Calling Java providers

A generic call is how Dubbo calls services across languages without shared
code. For a Java provider, an object is a dict that names its Java class
under `"class"`, and `types` names the Java type of each parameter, which a
Java provider needs to tell apart methods of one name:

```python
user = await users.call(
    "updateUser",
    {"class": "com.example.User", "id": 1, "name": "Alice"},
    types=["com.example.User"],
)
```

`refer_generic(..., generic=...)` chooses other forms of arguments and
results, such as `"protobuf-json"` for services defined in proto files, or
`"gson"` for JSON.

## Next

- [interop/java](../../interop/java): call Java services from Python, and
  Python services from Java.
