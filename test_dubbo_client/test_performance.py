# coding=utf-8
import profile
import pstats
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
    """
    在我的mac 4c8g笔记本上，同时启动服务端和客户端（忽略网络开销）
    test_client_every_new 运行1000次，13.380 seconds
    test_client 运行1000次， 12.851 seconds
    test_dubbo运行1000次 13.559 seconds
    说明
    1、加上Dubbo的封装，和原生的jsonrpclib差距很小，可以忽略不计
    2、每次new HttpClient和保持一个HttpClient句柄复用的效率相差不大
    3、每秒接近300次的调用，对一个业务系统来说绰绰有余
    大量的应用程序不需要这么快的运行速度，因为用户根本感觉不出来。
    例如开发一个下载MP3的网络应用程序，C程序的运行时间需要0.001秒，
    而Python程序的运行时间需要0.1秒，慢了100倍，但由于网络更慢，需要等待1秒，
    你想，用户能感觉到1.001秒和1.1秒的区别吗？
    这就好比F1赛车和普通的出租车在北京三环路上行驶的道理一样，
    虽然F1赛车理论时速高达400公里，但由于三环路堵车的时速只有20公里，
    因此，作为乘客，你感觉的时速永远是20公里。

    """
    # print u'test_client_every_new 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client_every_new, number=1))
    # print u'test_client 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client, number=1))
    # print u'test_dubbo 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_dubbo, number=1))
    # profile.run("test_dubbo()", 'test_dubbo.txt')
    p = pstats.Stats('test_dubbo.txt')
    p.sort_stats('time').print_stats()
    # profile.run('test_client_every_new()', 'test_client_every_new.txt')
    np = pstats.Stats('test_client_every_new.txt')
    np.sort_stats('time').print_stats()
    # profile.run('test_client()', 'test_client.txt')
    cp = pstats.Stats('test_client.txt')
    cp.sort_stats('time').print_stats()