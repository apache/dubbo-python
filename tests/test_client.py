import asyncio
import concurrent.futures


# 定义异步 TCP 客户端任务
class EchoClientProtocol(asyncio.Protocol):
    def __init__(self, message, loop, on_con_lost):
        self.message = message
        self.loop = loop
        self.on_con_lost = on_con_lost

    def connection_made(self, transport):
        self.transport = transport
        self.transport.write(self.message.encode())
        print("Data sent:", self.message)

    def data_received(self, data):
        print("Data received:", data.decode())
        self.transport.close()

    def connection_lost(self, exc):
        print("The server closed the connection")
        self.on_con_lost.set_result(True)


async def tcp_client(loop, message, host, port):
    on_con_lost = loop.create_future()
    transport, protocol = await loop.create_connection(
        lambda: EchoClientProtocol(message, loop, on_con_lost), host, port
    )
    try:
        await on_con_lost
    finally:
        transport.close()


def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def main():
    host = "127.0.0.1"
    port = 8888

    # 使用线程池管理事件循环线程
    with concurrent.futures.ThreadPoolExecutor() as executor:
        new_loop = asyncio.new_event_loop()
        executor.submit(start_loop, new_loop)

        # 创建并提交 TCP 客户端任务到线程池中的事件循环
        future1 = asyncio.run_coroutine_threadsafe(
            tcp_client(new_loop, "Message for server 1", host, port), new_loop
        )
        future2 = asyncio.run_coroutine_threadsafe(
            tcp_client(new_loop, "Message for server 2", host, port), new_loop
        )
        future3 = asyncio.run_coroutine_threadsafe(
            tcp_client(new_loop, "Message for server 3", host, port), new_loop
        )

        # 使用返回的 Future 对象来监视和管理协程任务
        print("Waiting for tasks to complete...")
        for future in [future1, future2, future3]:
            try:
                result = future.result()  # 获取协程的结果（阻塞直到结果可用）
                print(f"Task completed with result: {result}")
            except Exception as e:
                print(f"Task raised an exception: {e}")

        # 等待一段时间以观察任务执行
        import time

        time.sleep(10)  # 根据需要调整等待时间

        print("结束事件循环")
        new_loop.call_soon_threadsafe(new_loop.stop)  # 优雅停止事件循环


if __name__ == "__main__":
    main()
