from dubbo_client import ZookeeperRegistry, MulticastRegistry

__author__ = 'caozupeng'

def multicat():
    registry = MulticastRegistry('224.5.6.7:1234')
    registry.subscribe('com.ofpay.demo.api.UserProvider')
    print registry.get_provides('com.ofpay.demo.api.UserProvider')

def zookeeper():
    registry = ZookeeperRegistry('172.19.65.33:2181')
    registry.subscribe('com.ofpay.demo.api.UserProvider')
    print registry.get_provides('com.ofpay.demo.api.UserProvider')

if __name__ == '__main__':
    multicat()