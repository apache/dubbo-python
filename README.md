# Apache Dubbo for Python

![License](https://img.shields.io/github/license/apache/dubbo-python)
![GitHub last commit](https://img.shields.io/github/last-commit/apache/dubbo-python)
![GitHub branch check runs](https://img.shields.io/github/check-runs/apache/dubbo-python/main)

---

<p align="center">
  <img src="https://cn.dubbo.apache.org/imgs/nav_logo2.png" alt="Logo" width="40%" />
</p>

Apache Dubbo is an easy-to-use, high-performance WEB and RPC framework with builtin service discovery, traffic management, observability, security features, tools and best practices for building enterprise-level microservices.

Dubbo-python is a Python implementation of the [triple protocol](https://dubbo.apache.org/zh-cn/overview/reference/protocols/triple-spec/) (a protocol fully compatible with gRPC and friendly to HTTP) and various features designed by Dubbo for constructing microservice architectures.

Visit [the official website](https://dubbo.apache.org/) for more information.

### 🚧 Early-Stage Project 🚧

> **Disclaimer:** This project is in the early stages of development. Features are subject to change, and some components may not be fully stable. Contributions and feedback are welcome as the project evolves.

## Features

- **Service Discovery**: Zookeeper
- **Load Balance**: Random, CPU
- **RPC Protocols**: Triple(gRPC compatible and HTTP-friendly)
- **Transport**: asyncio(uvloop)
- **Serialization**: Customizable(protobuf, json...)


## Getting started

Before you begin, ensure that you have **`python 3.11+`**. Then, install Dubbo-Python in your project using the following steps:

```shell
git clone https://github.com/apache/dubbo-python.git
cd dubbo-python && pip install .
```

Get started with Dubbo-Python in just 5 minutes by following our [Quick Start Guide](https://github.com/apache/dubbo-python/tree/main/samples).

It's as simple as the following code snippet. With just a few lines of code, you can launch a fully functional point-to-point RPC service :

1. Build and start the Server

   ```python
   import dubbo
   from dubbo.configs import ServiceConfig
   from dubbo.proxy.handlers import RpcServiceHandler, RpcMethodHandler
   
   
   def handle_unary(request):
       s = request.decode("utf-8")
       print(f"Received request: {s}")
       return (s + " world").encode("utf-8")
   
   
   if __name__ == "__main__":
       # build a method handler
       method_handler = RpcMethodHandler.unary(handle_unary)
       # build a service handler
       service_handler = RpcServiceHandler(
           service_name="org.apache.dubbo.samples.HelloWorld",
           method_handlers={"unary": method_handler},
       )
   
       service_config = ServiceConfig(service_handler)
   
       # start the server
       server = dubbo.Server(service_config).start()
   
       input("Press Enter to stop the server...\n")
   ```

2. Build and start the Client

   ```python
   import dubbo
   from dubbo.configs import ReferenceConfig
   
   
   class UnaryServiceStub:
   
       def __init__(self, client: dubbo.Client):
           self.unary = client.unary(method_name="unary")
   
       def unary(self, request):
           return self.unary(request)
   
   
   if __name__ == "__main__":
       reference_config = ReferenceConfig.from_url(
           "tri://127.0.0.1:50051/org.apache.dubbo.samples.HelloWorld"
       )
       dubbo_client = dubbo.Client(reference_config)
   
       unary_service_stub = UnaryServiceStub(dubbo_client)
   
       result = unary_service_stub.unary("hello".encode("utf-8"))
       print(result.decode("utf-8"))
   ```

   

## License

Apache Dubbo-python software is licensed under the Apache License Version 2.0. See
the [LICENSE](https://github.com/apache/dubbo-python/blob/main/LICENSE) file for details.
