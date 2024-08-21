## Streaming Calls

Dubbo-python supports streaming calls, including `ClientStream`, `ServerStream`, and `BidirectionalStream`. The key difference in these calls is the use of iterators: passing an iterator as a parameter for `ClientStream`, receiving an iterator for `ServerStream`, or both passing and receiving iterators for `BidirectionalStream`.

When using `BidirectionalStream`, the client needs to pass an iterator as a parameter to send multiple data points, while also receiving an iterator to handle multiple responses from the server.

Here’s an example of the client-side code:

```python
class ChatServiceStub:

    def __init__(self, client: dubbo.Client):
        self.chat = client.bidi_stream(
            method_name="chat",
            request_serializer=chat_pb2.ChatMessage.SerializeToString,
            response_deserializer=chat_pb2.ChatMessage.FromString,
        )

    def chat(self, values):
        return self.chat(values)


if __name__ == "__main__":
    reference_config = ReferenceConfig.from_url(
        "tri://127.0.0.1:50051/org.apache.dubbo.samples.stream"
    )
    dubbo_client = dubbo.Client(reference_config)

    chat_service_stub = ChatServiceStub(dubbo_client)

    # Iterator of request
    def request_generator():
        for item in ["hello", "world", "from", "dubbo-python"]:
            yield chat_pb2.ChatMessage(user=item, message=str(uuid.uuid4()))

    result = chat_service_stub.chat(request_generator())

    for i in result:
        print(f"Received response: user={i.user}, message={i.message}")
```

And here’s the server-side code:

```python
def chat(request_stream):
    for request in request_stream:
        print(f"Received message from {request.user}: {request.message}")
        yield chat_pb2.ChatMessage(user=request.message, message=request.user)


if __name__ == "__main__":
    # build a method handler
    method_handler = RpcMethodHandler.bi_stream(
        chat,
        request_deserializer=chat_pb2.ChatMessage.FromString,
        response_serializer=chat_pb2.ChatMessage.SerializeToString,
    )
    # build a service handler
    service_handler = RpcServiceHandler(
        service_name="org.apache.dubbo.samples.stream",
        method_handlers={"chat": method_handler},
    )

    service_config = ServiceConfig(service_handler)

    # start the server
    server = dubbo.Server(service_config).start()

    input("Press Enter to stop the server...\n")

```

