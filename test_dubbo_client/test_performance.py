# coding=utf-8
import timeit

from pyjsonrpc import HttpClient
from dubbo_client import ZookeeperRegistry, DubboClient


__author__ = 'caozupeng'

number = 1000

def test_client_every_new():
    for x in range(number):
        user_provider = HttpClient(url="http://{0}{1}".format('172.19.3.111:38080/', 'com.ofpay.demo.api.UserProvider'))
        user_provider.getUser('A003')
        user_provider.queryUser(
            {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
        # user_provider.queryAll()
        user_provider.isLimit('MAN', 'Joe')
        user_provider('getUser', 'A005')


def test_client():
    user_provider = HttpClient(url="http://{0}{1}".format('172.19.3.111:38080/', 'com.ofpay.demo.api.UserProvider'))
    for x in range(number):
        user_provider.getUser('A003')
        user_provider.queryUser(
            {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
        # user_provider.queryAll()
        user_provider.isLimit('MAN', 'Joe')
        user_provider('getUser', 'A005')


def test_dubbo():
    service_interface = 'com.ofpay.demo.api.UserProvider'
    # 该对象较重，有zookeeper的连接，需要保存使用
    registry = ZookeeperRegistry('172.19.65.33:2181')
    user_provider = DubboClient(service_interface, registry, version='2.0')
    for x in range(number):
        user_provider.getUser('A003')
        user_provider.queryUser(
            {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
        # user_provider.queryAll()
        user_provider.isLimit('MAN', 'Joe')
        user_provider('getUser', 'A005')

if __name__ == '__main__':
    #test_client_every_new 运行10000次， 耗时220.188388109
    #test_client 运行10000次， 耗时215.014229059
    #说明每次new HttpClient和保持一个HttpClient的效率相差不大

    print u'test_client_every_new 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client_every_new, number=1))
    print u'test_client 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client, number=1))
    print u'test_dubbo 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_dubbo, number=1))