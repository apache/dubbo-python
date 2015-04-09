# coding=utf-8
import time

from dubbo_client import DubboClient, DubboClientError


__author__ = 'caozupeng'

if __name__ == '__main__':
    service_interface = 'com.ofpay.demo.api.UserProvider'
    dubbo_client = DubboClient(service_interface)
    for i in range(1000):
        try:
            print dubbo_client.getUser('A003')
            print dubbo_client.queryUser(
                {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
            print dubbo_client.queryAll()
            print dubbo_client.isLimit('MAN', 'Joe')
            print dubbo_client('getUser', 'A005')

        except DubboClientError, client_e:
            print client_e
        time.sleep(5)
