Python Dubbo Client
=====================================  
实现客户端的负载均衡、自动发现服务功能
-------------------------------------


### Python调用Dubbo接口的jsonrpc协议  
请使用dubbo-rpc-jsonrpc 并在dubbo中配置protocol为jsonrpc协议
参考 https://github.com/ofpay/dubbo-rpc-jsonrpc

### 安装
下载代码   
python setup.py install
Git安装   
pip install git+http://git.dev.qianmi.com/tda/dubbo-client-py.git   
或者   
pip install git+https://github.com/ofpay/dubbo-client-py.git

### 在客户端实现负载均衡，服务发现  
通过注册中心的zookeeper，获取服务的注册信息
然后通过代理实现负载均衡算法，调用服务端
支持Version、Group设置

### Example
```python   
    service_interface = 'com.ofpay.demo.api.UserProvider'
    registry = ZookeeperRegistry('172.19.65.33:2181')
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
优化性能  
支持Retry参数  
支持RoundRobin的调用  

### Licenses
MIT License