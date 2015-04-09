# coding=utf-8
import urllib

from kazoo.protocol.states import KazooState

from dubbo_client.common import ServiceProvider


__author__ = 'caozupeng'
from kazoo.client import KazooClient


class Registry(object):
    def add_provider_listener(self, provide_name):
        """
        监听注册中心的服务上下线
        :param provide_name: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :return: 无返回
        """
        pass

    def get_provides(self, provide_name, default=None):
        """
        获取已经注册的服务URL对象
        :param provide_name: com.ofpay.demo.api.UserProvider
        :param default:
        :return: 返回一个dict的服务集合
        """
        pass


class ZookeeperRegistry(Registry):
    """
    所有注册过的服务端将在这里
    格式为{providername:{ip+port:service}}
    providername = group_version_servicename
    """
    __service_provides = {}
    __connect_state = 'UNCONNECT'

    def __init__(self, hosts):
        self.__zk = KazooClient(hosts=hosts, read_only=True)
        self.__zk.add_listener(self.__state_listener)
        self.__zk.start()

    def __state_listener(self, state):
        if state == KazooState.LOST:
            # Register somewhere that the session was lost
            self.__connect_state = state
        elif state == KazooState.SUSPENDED:
            # Handle being disconnected from Zookeeper
            print 'disconnect from zookeeper'
            self.__connect_state = state
        else:
            # Handle being connected/reconnected to Zookeeper
            print 'connected'
            self.__connect_state = state

    def __event_listener(self, event):
        self.__do_event(event)

    def __handler_urls(self, urls):
        for child_node in urls:
            url = urllib.unquote(child_node).decode('utf8')
            if url.startswith('jsonrpc'):
                provide = ServiceProvider(url)
                service_key = self.__service_provides.get(provide.interface)
                if service_key:
                    service_key[provide.location] = provide
                else:
                    self.__service_provides[provide.interface] = {provide.location: provide}

    def __do_event(self, event):
        # event.path 是类似/dubbo/com.ofpay.demo.api.UserProvider/providers 这样的
        # 如果要删除，必须先把/dubbo/和最后的/providers去掉
        provide_name = event.path[7:event.path.rfind('/')]
        if provide_name in self.__service_provides:
            del self.__service_provides[provide_name]
        if event.state == 'CONNECTED':
            children = self.__zk.get_children(event.path, watch=self.__event_listener)
            self.__handler_urls(children)
        if event.state == 'DELETED':
            children = self.__zk.get_children(event.path, watch=self.__event_listener)
            self.__handler_urls(children)

    def add_provider_listener(self, provide_name):
        """
        监听注册中心的服务上下线
        :param provide_name: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :return: 无返回
        """
        # 如果已经存在，首先删除原有的服务的集合
        if provide_name in self.__service_provides:
            del self.__service_provides[provide_name]
        children = self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', provide_name, 'providers'),
                                          watch=self.__event_listener)
        # 全部重新添加
        self.__handler_urls(children)

    def get_provides(self, provide_name, default=None):
        """
        获取已经注册的服务URL对象
        :param provide_name: com.ofpay.demo.api.UserProvider
        :param default:
        :return: 返回一个dict的服务集合
        """
        return self.__service_provides.get(provide_name, default)


if __name__ == '__main__':
    pass

