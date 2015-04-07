### Python Dubbo Client

##Python调用Dubbo接口的jsonrpc协议  
请使用dubbo-rpc-jsonrpc

##在客户端实现负载均衡，服务发现  
通过注册中心的zookeeper，获取服务的注册信息
然后通过代理实现负载均衡算法，调用服务端