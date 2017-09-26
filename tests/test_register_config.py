# coding=utf-8
import time

from dubbo_client import ApplicationConfig
from dubbo_client import DubboClient, DubboClientError
from dubbo_client import ZookeeperRegistry


def test_config_init():
    config = ApplicationConfig('test_register_config')
    service_interface = 'com.ofpay.demo.api.UserProvider'
    registry = ZookeeperRegistry('172.19.66.49:2181', config)
    user_provider = DubboClient(service_interface, registry, version='1.0.0')
    for i in range(10000):
        try:
            print user_provider.findOne()
        except DubboClientError, client_error:
            print client_error
        time.sleep(1)

if __name__ == '__main__':
    test_config_init()
