## Streaming Calls

Dubbo-python supports streaming calls, including `ClientStream`, `ServerStream`, and `BidirectionalStream`. The key difference in these calls is the use of iterators: passing an iterator as a parameter for `ClientStream`, receiving an iterator for `ServerStream`, or both passing and receiving iterators for `BidirectionalStream`.

When using `BidirectionalStream`, the client needs to pass an iterator as a parameter to send multiple data points, while also receiving an iterator to handle multiple responses from the server.

Here’s an example of the client-side code:

```python
class GreeterServiceStub:
    def __init__(self, client: dubbo.Client):
        self.bidi_stream = client.bidi_stream(
            method_name="biStream",
            request_serializer=greeter_pb2.GreeterRequest.SerializeToString,
            response_deserializer=greeter_pb2.GreeterReply.FromString,
        )

    def bi_stream(self, values):
        return self.bidi_stream(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.proto.Greeter"
    )
    dubbo_client = dubbo.Client(reference_config)

    stub = GreeterServiceStub(dubbo_client)

    # Iterator of request
    def request_generator():
        for item in ["hello", "world", "from", "dubbo-python"]:
            yield greeter_pb2.GreeterRequest(name=str(item))

    result = stub.bi_stream(request_generator())

    for i in result:
        print(f"Received response: {i.message}")
```

And here’s the server-side code:

```python
def bi_stream(request_stream):
    for request in request_stream:
        print(f"Received message from {request.name}")
        yield greeter_pb2.GreeterReply(message=request.name)


if __name__ == "__main__":
    # build a method handler
    method_handler = RpcMethodHandler.bi_stream(
        bi_stream,
        request_deserializer=greeter_pb2.GreeterRequest.FromString,
        response_serializer=greeter_pb2.GreeterReply.SerializeToString,
    )
    # build a service handler
    service_handler = RpcServiceHandler(
        service_name="org.apache.dubbo.samples.proto.Greeter",
        method_handlers={"biStream": method_handler},
    )

    service_config = ServiceConfig(service_handler)

    # start the server
    server = dubbo.Server(service_config).start()

    input("Press Enter to stop the server...\n")
```

