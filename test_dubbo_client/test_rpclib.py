# coding=utf-8
import time

from dubbo_client import ZookeeperRegistry, DubboClient, DubboClientError


__author__ = 'caozupeng'

if __name__ == '__main__':
    service_interface = 'com.ofpay.demo.api.UserProvider'
    # 该对象较重，有zookeeper的连接，需要保存使用
    registry = ZookeeperRegistry('172.19.65.33:2181')
    user_provider = DubboClient(service_interface, registry, version='3.0')
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
