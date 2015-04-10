# coding=utf-8
import timeit

from pyjsonrpc import HttpClient


__author__ = 'caozupeng'


def test_client_every_new():
    user_provider = HttpClient(url="http://{0}{1}".format('172.19.3.111:38081/', 'com.ofpay.demo.api.UserProvider'))
    user_provider.getUser('A003')
    user_provider.queryUser(
        {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
    # user_provider.queryAll()
    user_provider.isLimit('MAN', 'Joe')
    user_provider('getUser', 'A005')


def test_client():
    user_provider = HttpClient(url="http://{0}{1}".format('172.19.3.111:38081/', 'com.ofpay.demo.api.UserProvider'))
    for x in range(10000):
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
    number = 10000
    print u'test_client_every_new 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client_every_new, number=number))
    print u'test_client 运行{0}次， 耗时{1}'.format(number, timeit.timeit(test_client, number=1))