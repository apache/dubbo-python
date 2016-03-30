# coding=utf-8
import time

from dubbo_client import ZookeeperRegistry, DubboClient, DubboClientError, ApplicationConfig

__author__ = 'caozupeng'

if __name__ == '__main__':
    config = ApplicationConfig('test_rpclib')
    service_interface = 'com.qianmi.kstore.provider.CustomerAddressProvider'
    # 该对象较重，有zookeeper的连接，需要保存使用
    registry = ZookeeperRegistry('zookeeper:2181', config)
    # registry = MulticastRegistry('224.5.6.7:1234', config)
    user_provider = DubboClient(service_interface, registry, version='1.0')
    for i in range(1000):
        try:
            print user_provider.findAddressByCustomerId(1)
            # print user_provider.save(1, 3)

        except DubboClientError, client_error:
            print client_error.message
            print client_error.data
        time.sleep(5)
