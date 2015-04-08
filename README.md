Python Dubbo Client
=====================================  
实现客户端的负载均衡、自动发现服务功能
-------------------------------------


### Python调用Dubbo接口的jsonrpc协议  
请使用dubbo-rpc-jsonrpc 并在dubbo中配置protocol为jsonrpc协议

### 在客户端实现负载均衡，服务发现  
通过注册中心的zookeeper，获取服务的注册信息
然后通过代理实现负载均衡算法，调用服务端

### Example
'''python
    service_interface = 'com.ofpay.demo.api.UserProvider'
    dubbo_client = DubboClient(service_interface)
    print dubbo_client.getUser('A003')
    print dubbo_client.queryUser(
        {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
    print dubbo_client.queryAll()
    print dubbo_client.isLimit('MAN', 'Joe')
    print dubbo_client('getUser', 'A005')
'''