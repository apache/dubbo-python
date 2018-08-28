# Python Dubbo Client
## Implement the load balancing in the client and   discover service function with Zookeeper automatically
### Python calls the jsonrpc protocol of the Dubbo interface
Please use dubbo-rpc-jsonrpc and configure the protocol as the jsonrpc protocol in dubbo, referring to [https://github.com/apache/incubator-dubbo-rpc-jsonrpc](https://github.com/apache/incubator-dubbo-rpc-jsonrpc).
### Install
Download code
python setup.py install
Install <span data-type="color" style="color:rgb(36, 41, 46)"><span data-type="background" style="background-color:rgb(255, 255, 255)">pip</span></span>
<span data-type="color" style="color:rgb(36, 41, 46)"><span data-type="background" style="background-color:rgb(255, 255, 255)">pip install dubbo-client==1.0.0b5</span></span>
Install <span data-type="color" style="color:rgb(36, 41, 46)"><span data-type="background" style="background-color:rgb(255, 255, 255)">Git</span></span>
<span data-type="color" style="color:rgb(36, 41, 46)"><span data-type="background" style="background-color:rgb(255, 255, 255)">pip install git+</span></span>[http://git.dev.qianmi.com/tda/dubbo-client-py.git@1.0.0b5](http://git.dev.qianmi.com/tda/dubbo-client-py.git@1.0.0b5)
or
<span data-type="color" style="color:rgb(36, 41, 46)"><span data-type="background" style="background-color:rgb(255, 255, 255)">pip install git+</span></span>[https://github.com/qianmiopen/dubbo-client-py.git@1.0.0b5](https://github.com/qianmiopen/dubbo-client-py.git@1.0.0b5)
### Implement the load balancing on the client and the service discovery
Get the service registration information with the zookeeper in the registration center
.
Dubbo-client-py supports configuring multiple zookeeper service addresses
.
"host": "192.168.1.183:2181,192.168.1.184:2181,192.168.1.185:2181"
Then implement the load balancing algorithm and calling the server through the proxy.
Support Version, Group settings.
#### Example
```xml
config = ApplicationConfig('test_rpclib')
    service_interface = 'com.ofpay.demo.api.UserProvider'
    #registry contains a connection to zookeeper, which needs to be cached
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
#### TODO
Optimize performance and minimize the impact of online and offline service.
Support Retry parameters
.
Support weight call
.
Unit test the coverage ratios.
#### Licenses
Apache License
### Acknowledgment
Thanks to @jingpeicomp' s attempts, and the flow of this function has been running normally in the production environment for several months, thank you!
