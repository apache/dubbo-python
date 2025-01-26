# Apache Dubbo for Python

![License](https://img.shields.io/github/license/apache/dubbo-python?logo=apache&logoColor=red&label=LICENSE)
![GitHub last commit](https://img.shields.io/github/last-commit/apache/dubbo-python)
![GitHub branch check runs](https://img.shields.io/github/check-runs/apache/dubbo-python/main)
![PyPI - Version](https://img.shields.io/pypi/v/apache-dubbo?logo=pypi&logoColor=gold&label=PyPI&color=blue)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/apache-dubbo?logo=python&logoColor=gold&label=Python)

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


## Installation

Before you start, make sure you have **`python 3.9+`** installed.

1. Install Directly

   ```sh
   pip install apache-dubbo
   ```
2. Install from source

   ```sh
   git clone https://github.com/apache/dubbo-python.git
   cd dubbo-python && pip install .
   ```

## Getting started

Get up and running with Dubbo-Python in just 5 minutes by following our [Quick Start Guide](https://github.com/apache/dubbo-python/tree/main/samples).

It's as simple as the code snippet below. With just a few lines of code, you can launch a fully functional point-to-point RPC service:

1. Build and start the server

   ```python
   import dubbo
   from dubbo.configs import ServiceConfig
   from dubbo.proxy.handlers import RpcMethodHandler, RpcServiceHandler
   
   
   class UnaryServiceServicer:
       def say_hello(self, message: bytes) -> bytes:
           print(f"Received message from client: {message}")
           return b"Hello from server"
   
   
   def build_service_handler():
       # build a method handler
       method_handler = RpcMethodHandler.unary(
           method=UnaryServiceServicer().say_hello, method_name="unary"
       )
       # build a service handler
       service_handler = RpcServiceHandler(
           service_name="org.apache.dubbo.samples.HelloWorld",
           method_handlers=[method_handler],
       )
       return service_handler
   
   
   if __name__ == "__main__":
       # build service config
       service_handler = build_service_handler()
       service_config = ServiceConfig(
           service_handler=service_handler, host="127.0.0.1", port=50051
       )
       # start the server
       server = dubbo.Server(service_config).start()
   
       input("Press Enter to stop the server...\n")
   ```

1. Build and start the Client

   ```python
   import dubbo
   from dubbo.configs import ReferenceConfig
   
   
   class UnaryServiceStub:
       def __init__(self, client: dubbo.Client):
           self.unary = client.unary(method_name="unary")
   
       def say_hello(self, message: bytes) -> bytes:
           return self.unary(message)
   
   
   if __name__ == "__main__":
       # Create a client
       reference_config = ReferenceConfig.from_url(
           "tri://127.0.0.1:50051/org.apache.dubbo.samples.HelloWorld"
       )
       dubbo_client = dubbo.Client(reference_config)
       unary_service_stub = UnaryServiceStub(dubbo_client)
   
       # Call the remote method
       result = unary_service_stub.say_hello(b"Hello from client")
       print(result)
   
   ```

## Contributing

We are excited to welcome contributions to the Dubbo-Python project! Whether you are fixing bugs, adding new features, or improving documentation, your input is highly valued.

To ensure a smooth collaboration, please review our [Contributing Guide](https://github.com/apache/dubbo-python/blob/main/CONTRIBUTING.md) for detailed instructions on how to get started, adhere to coding standards, and submit your contributions effectively.

## License

Apache Dubbo-python software is licensed under the Apache License Version 2.0. See
the [LICENSE](https://github.com/apache/dubbo-python/blob/main/LICENSE) file for details.
