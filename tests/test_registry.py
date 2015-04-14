from dubbo_client import ZookeeperRegistry

__author__ = 'caozupeng'

if __name__ == '__main__':
    registry = ZookeeperRegistry('172.19.65.33:2181')
    registry.subscribe('com.ofpay.demo.api.UserProvider')
    print registry.get_provides('com.ofpay.demo.api.UserProvider')