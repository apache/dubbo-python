# coding=utf-8
import time

from dubbo_client import ZookeeperRegistry, DubboClient, DubboClientError, ApplicationConfig

__author__ = 'caozupeng'

if __name__ == '__main__':
    config = ApplicationConfig('test_rpclib')
    service_interface = 'com.ofpay.demo.api.UserProvider'
    # 该对象较重，有zookeeper的连接，需要保存使用
    registry = ZookeeperRegistry('115.28.74.185:2181', config)
    # registry = MulticastRegistry('224.5.6.7:1234', config)
    user_provider = DubboClient(service_interface, registry, version='2.0')
    for i in range(1000):
        try:
            print user_provider.getUser('A003')
            # print user_provider.getUser(123)
            # print user_provider.queryUser(
            #     {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
            # datas = user_provider.queryAll()
            # for key, user in datas.items():
            #     print user['name']
            # print user_provider.isLimit('MAN', 'Joe')
            # print user_provider('getUser', 'A005')
            # print user_provider.notFunc()
            # print user_provider.gotException()
        except DubboClientError, client_error:
            print client_error.message
            print client_error.data
        time.sleep(5)
