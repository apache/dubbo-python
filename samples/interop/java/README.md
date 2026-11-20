# Java

Most Dubbo services are written in Java. A Python service joins them in the
same registry: Java consumers call it as they call a Java service, and it
calls Java services, over both protocols. This sample runs a provider and a
consumer in each language, which find each other in Nacos.

## What you will learn

- how Python and Java share a contract: a `.proto` file over Triple, and a
  Java interface with its classes over Dubbo;
- how a Python class stands for a Java class in Hessian 2, and a Python int
  for a Java `long`;
- how exceptions cross between the languages;
- how attachments, such as a trace id, cross between them;
- how each side finds the other through a registry, with no addresses in
  the code.

## Before you start

You need a JDK 17 or later and Maven, and Nacos, as in
[04_registry](../../basics/04_registry):

```console
$ pip install "apache-dubbo[nacos]"
$ docker compose -f ../../compose.yaml up -d --wait
```

## The files

| File | Role |
|---|---|
| `proto/greeter.proto` | The contract of `Greeter`, which both languages generate code from |
| `greeter_pb2.py`, `greeter_pb2.pyi`, `greeter_dubbo.py` | The Python code generated from it, as in [02_protobuf](../../basics/02_protobuf) |
| `users.py` | The contract of `UserService` in Python, with the `User` class |
| `python_server.py`, `python_client.py` | The Python provider and consumer |
| `java/` | A Maven project: `UserService` and `User` in Java, the Java provider and consumer; Maven generates the Java code of `greeter.proto` |

## Run it

### Python calls Java

From this directory, start the Java server:

```console
$ mvn -q -f java/pom.xml compile exec:java -Dexec.mainClass=org.apache.dubbo.samples.JavaServer
Serving Greeter on port 50052 and UserService on port 20881; press Ctrl+C to stop
```

The first run downloads the dependencies, which takes a while. In another
terminal, run the Python client:

```console
$ python python_client.py
Hello, Alice, from Java!
Hello #1, Bob, from Java!
Hello #2, Bob, from Java!
Hello #3, Bob, from Java!
User(id=1, name='Alice', email='alice@example.com')
java.lang.IllegalArgumentException: no user has ID 42
```

The Java server prints each call it serves, with the trace id that the
Python client attached:

```console
[py-4bf9] sayHello(Alice)
[py-4bf9] getUser(1)
[py-4bf9] getUser(42)
```

Stop the Java server with Ctrl+C. Its Nacos client may log interrupted
threads as it stops; they do no harm.

### Java calls Python

Start the Python server:

```console
$ python python_server.py
Serving Greeter on port 50051 and UserService on port 20880; press Ctrl+C to stop
```

In another terminal, run the Java client:

```console
$ mvn -q -f java/pom.xml compile exec:java -Dexec.mainClass=org.apache.dubbo.samples.JavaClient
Hello, Alice, from Python!
Hello #1, Bob, from Python!
Hello #2, Bob, from Python!
Hello #3, Bob, from Python!
User(id=1, name=Alice, email=alice@example.com)
java.lang.IllegalArgumentException: no user has ID 42
```

The Python server prints the trace id that the Java client attached:

```console
[java-7f3a] say_hello(Alice)
[java-7f3a] get_user(1)
[None] get_user(42)
```

With both servers running, each client finds the services of both and
spreads its calls over them, whatever their language.

## How it works

### Finding each other

Both sides use Nacos and their defaults: a provider registers per
application and per service, and a consumer finds providers per application
while there are any, as [04_registry](../../basics/04_registry) explains.
Neither knows the language of the other: a consumer looks a service up by
its name, and reads from the metadata of each instance which protocol and
port to call it on.

So a service must have the same name on both sides, and so must its
methods.

### Triple and Protobuf

`Greeter` is defined once, in `proto/greeter.proto`. protoc generates the
Python code, and the `dubbo-maven-plugin` of the Maven project the Java code,
from the same file. Each language calls and serves it as its own code:
`StreamObserver` in Java, `async for` in Python.

Its name is the package and service of the `.proto` file,
`org.apache.dubbo.samples.Greeter`. Dubbo Java registers a service under the
name of its Java interface, though, which `option java_package` would
change. So the file sets no `java_package`, and the Java interface has the
same name as the service.

### Dubbo and Hessian 2

`UserService` is a Java interface, the most common kind of Dubbo service.
Python declares the same contract in `users.py`, with the Java names:

- `@dubbo.service("org.apache.dubbo.samples.UserService")` names the
  interface, and `@dubbo.method("getUser")` the method;
- `@hessian2.java_class("org.apache.dubbo.samples.User")` makes the
  dataclass `User` travel as the Java class `User`, field by field; a field
  such as `user_id` would travel as `userId`, as Java names it;
- `hessian2.Long` marks an int that Java declares `long`. Java tells methods
  apart by the types of their parameters as well as by name, so the types
  must match.

### Exceptions

An exception a Java provider throws reaches Python as a `dubbo.RemoteError`,
an `RpcError` that names the Java class. A Python provider throws a Java
exception the same way, with
`RemoteError("java.lang.IllegalArgumentException", message)`, which Java
catches as an `IllegalArgumentException`. An `RpcError` of a Python
provider reaches Java as an `RpcException`, as a failure of the call rather
than of the service.

### Attachments

Attachments travel with a call in both protocols, as headers over Triple
and as a map over Dubbo, so each language reads what another attached:

| | Attach to calls | Read in a handler |
|---|---|---|
| Python | `with dubbo.outgoing({"trace-id": ...}):` | `dubbo.incoming().attachments` |
| Java | `RpcContext.getClientAttachment().setAttachment("trace-id", ...)` | `RpcContext.getServerAttachment().getAttachment("trace-id")` |

Python attaches to every call in the block. Java attaches to the next call
only: the Java client attaches the trace id before `sayHello` and
`getUser(1)`, and `getUser(42)` arrives without one.

## Next

- [interop/go](../go): call Go services from Python, and Python services
  from Go.
