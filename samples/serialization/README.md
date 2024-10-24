## Custom Serialization

Python is a dynamic language, and its flexibility makes it challenging to design a universal serialization layer for other languages. Therefore, we removed the framework-level serialization layer and instead exposed interfaces, allowing users to implement their own (as they know best the data format they will be passing).

Serialization typically involves two parts: serialization and deserialization. We have defined the types for these functions, and custom serialization/deserialization functions must follow these "formats."

For serialization functions, we specify:

```python
# A function that takes any number of arguments and returns data of type bytes
SerializingFunction = Callable[..., bytes]
```

For deserialization functions, we specify:

```
# A function that takes an argument of type bytes and returns data of any type
DeserializingFunction = Callable[[bytes], Any]
```

Below, I'll demonstrate how to use `protobuf` and `json` for serialization.

### [protobuf](./protobuf)

1. For defining and compiling `protobuf` files, please refer to the [protobuf tutorial](https://protobuf.dev/getting-started/pythontutorial/) for detailed instructions.

2. Set `xxx_serializer` and `xxx_deserializer` in the client and server.

   client

   ```python
   class GreeterServiceStub:
       def __init__(self, client: dubbo.Client):
           self.unary = client.unary(
               method_name="sayHello",
               request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
               response_deserializer=greeter_pb2.GreeterReply.FromString,
           )
   
       def say_hello(self, request):
           return self.unary(request)
   
   
   if __name__ == "__main__":
       reference_config = ReferenceConfig.from_url(
           "tri://127.0.0.1:50051/org.apache.dubbo.samples.data.Greeter"
       )
       dubbo_client = dubbo.Client(reference_config)
   
       stub = GreeterServiceStub(dubbo_client)
       result = stub.say_hello(greeter_pb2.GreeterRequest(name="Dubbo-python"))
       print(f"Received reply: {result.message}")
   ```
   
   server
   
   ```python
   class GreeterServiceServicer:
       def say_hello(self, request):
           print(f"Received request: {request}")
           return greeter_pb2.GreeterReply(message=f"Hello, {request.name}")
   
   
   def build_service_handler():
       # build a method handler
       method_handler = RpcMethodHandler.unary(
           GreeterServiceServicer().say_hello,
           method_name="sayHello",
           request_deserializer=greeter_pb2.GreeterRequest.FromString,
           response_serializer=greeter_pb2.GreeterReply.SerializeToString,
       )
       # build a service handler
       service_handler = RpcServiceHandler(
           service_name="org.apache.dubbo.samples.data.Greeter",
           method_handlers=[method_handler],
       )
       return service_handler
   
   
   if __name__ == "__main__":
       # build a service handler
       service_handler = build_service_handler()
       service_config = ServiceConfig(
           service_handler=service_handler, host="127.0.0.1", port=50051
       )
   
       # start the server
       server = dubbo.Server(service_config).start()
   
       input("Press Enter to stop the server...\n")
   ```



### [Json](./json)

We have already implemented single-parameter serialization and deserialization using `protobuf`. Now, I will demonstrate how to write a multi-parameter `Json` serialization and deserialization function to enable remote calls for methods with multiple parameters.

1. Install `orjson`:

   ```shell
   pip install orjson
   ```

2. Define serialization and deserialization functions:

   client

   ```python
   def request_serializer(name: str, age: int) -> bytes:
       return orjson.dumps({"name": name, "age": age})
   
   
   def response_deserializer(data: bytes) -> str:
       json_dict = orjson.loads(data)
       return json_dict["message"]
   
   
   class GreeterServiceStub:
       def __init__(self, client: dubbo.Client):
           self.unary = client.unary(
               method_name="unary",
               request_serializer=request_serializer,
               response_deserializer=response_deserializer,
           )
   
       def say_hello(self, name: str, age: int):
           return self.unary(name, age)
   
   
   if __name__ == "__main__":
       reference_config = ReferenceConfig.from_url(
           "tri://127.0.0.1:50051/org.apache.dubbo.samples.serialization.json"
       )
       dubbo_client = dubbo.Client(reference_config)
   
       stub = GreeterServiceStub(dubbo_client)
       result = stub.say_hello("dubbo-python", 18)
       print(result)
   ```
   
   server
   
   ```python
   def request_deserializer(data: bytes) -> Tuple[str, int]:
       json_dict = orjson.loads(data)
       return json_dict["name"], json_dict["age"]
   
   
   def response_serializer(message: str) -> bytes:
       return orjson.dumps({"message": message})
   
   
   class GreeterServiceServicer:
       def say_hello(self, request):
           name, age = request
           print(f"Received request: {name}, {age}")
           return f"Hello, {name}, you are {age} years old."
   
   
   def build_service_handler():
       # build a method handler
       method_handler = RpcMethodHandler.unary(
           GreeterServiceServicer().say_hello,
           method_name="unary",
           request_deserializer=request_deserializer,
           response_serializer=response_serializer,
       )
       # build a service handler
       service_handler = RpcServiceHandler(
           service_name="org.apache.dubbo.samples.serialization.json",
           method_handlers=[method_handler],
       )
       return service_handler
   
   
   if __name__ == "__main__":
       # build server config
       service_handler = build_service_handler()
       service_config = ServiceConfig(
           service_handler=service_handler, host="127.0.0.1", port=50051
       )
   
       # start the server
       server = dubbo.Server(service_config).start()
   
       input("Press Enter to stop the server...\n")
   ```
   
   