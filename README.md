Python Dubbo Client
=====================================  
实现客户端的负载均衡、配合Zookeeper自动发现服务功能
-------------------------------------


### Python调用Dubbo接口的jsonrpc协议  
请使用dubbo-rpc-jsonrpc 并在dubbo中配置protocol为jsonrpc协议
参考 https://github.com/ofpay/dubbo-rpc-jsonrpc

### 安装
下载代码   
python setup.py install
pip安装
pip install dubbo-client==1.0.0b5
Git安装   
pip install git+http://git.dev.qianmi.com/tda/dubbo-client-py.git@1.0.0b5   
或者   
pip install git+https://github.com/ofpay/dubbo-client-py.git@1.0.0b5

### 在客户端实现负载均衡，服务发现  
通过注册中心的zookeeper，获取服务的注册信息
然后通过代理实现负载均衡算法，调用服务端
支持Version、Group设置

### Example
```python   
    config = ApplicationConfig('test_rpclib')
    service_interface = 'com.ofpay.demo.api.UserProvider'
    #registry包含了和zookeeper的连接，该对象需要缓存
    registry = ZookeeperRegistry('192.168.59.103:2181', config)
    user_provider = DubboClient(service_interface, registry, version='1.0')
    for i in range(1000):
        try:
            print user_provider.getUser('A003')
            print user_provider.queryUser(
                {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
            print user_provider.queryAll()
            print user_provider.isLimit('MAN', 'Joe')
            print user_provider('getUser', 'A005')

        except DubboClientError, client_error:
            print client_error
        time.sleep(5)
```

### TODO
优化性能，将服务上下线的影响降到最小  
支持Retry参数    
支持权重调用    
单元测试覆盖率

### Licenses
MIT License