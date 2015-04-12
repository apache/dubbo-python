# coding=utf-8

__author__ = 'caozupeng'
import urllib

from kazoo.protocol.states import KazooState
from kazoo.client import KazooClient

from dubbo_client.common import ServiceURL


class Registry(object):
    def subscribe(self, provide_name):
        """
        监听注册中心的服务上下线
        :param provide_name: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :return: 无返回
        """
        pass

    def get_provides(self, provide_name, default=None, **kwargs):
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
    interface=com.ofpay.demo.DemoService
    location = ip:port/url 比如 172.19.20.111:38080/com.ofpay.demo.DemoService2
    providername = servicename|version|group
    dict 格式为{interface:{providername:{ip+port:service_url}}}

    """
    __service_provides = {}
    __connect_state = 'UNCONNECT'

    def __init__(self, zk_hosts):
        self.__zk = KazooClient(hosts=zk_hosts, read_only=True)
        self.__zk.add_listener(self.__state_listener)
        self.__zk.start()

    def __state_listener(self, state):
        if state == KazooState.LOST:
            # Register somewhere that the session was lost
            self.__connect_state = state
        elif state == KazooState.SUSPENDED:
            # Handle being disconnected from Zookeeper
            # print 'disconnect from zookeeper'
            self.__connect_state = state
        else:
            # Handle being connected/reconnected to Zookeeper
            # print 'connected'
            self.__connect_state = state

    def __event_listener(self, event):
        """
        node provides上下线的监听回调函数
        :param event:
        :return:
        """
        self.__do_event(event)

    def __to_key(self, interface, versioin, group):
        return '{0}|{1}|{2}'.format(interface, versioin, group)

    def __handler_nodes(self, interface, nodes):
        """
        将zookeeper中查询到的服务节点列表加入到一个dict中
        :param nodes: 节点列表
        :return: 不需要返回
        """
        # 如果已经存在，首先删除原有的服务的集合
        if interface in self.__service_provides:
            del self.__service_provides[interface]
        for child_node in nodes:
            node = urllib.unquote(child_node).decode('utf8')
            if node.startswith('jsonrpc'):
                service_url = ServiceURL(node)
                key = self.__to_key(service_url.interface, service_url.version, service_url.group)
                second_dict = self.__service_provides.get(interface)
                if second_dict:
                    # 获取最内层的nest的dict
                    inner_dict = second_dict.get(key)
                    if inner_dict:
                        inner_dict[service_url.location] = service_url
                    else:
                        second_dict[key] = {service_url.location: service_url}
                else:
                    # create the second dict
                    self.__service_provides[interface] = {key: {service_url.location: service_url}}

    def __do_event(self, event):
        # event.path 是类似/dubbo/com.ofpay.demo.api.UserProvider/providers 这样的
        # 如果要删除，必须先把/dubbo/和最后的/providers去掉
        provide_name = event.path[7:event.path.rfind('/')]
        if event.state == 'CONNECTED':
            children = self.__zk.get_children(event.path, watch=self.__event_listener)
            self.__handler_nodes(provide_name, children)
        if event.state == 'DELETED':
            children = self.__zk.get_children(event.path, watch=self.__event_listener)
            self.__handler_nodes(provide_name, children)

    def subscribe(self, interface, **kwargs):
        """
        监听注册中心的服务上下线
        :param interface: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :return: 无返回
        """
        version = kwargs.get('version', '')
        group = kwargs.get('group', '')
        children = self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', interface, 'providers'),
                                          watch=self.__event_listener)
        # 全部重新添加
        self.__handler_nodes(interface, children)

    def get_provides(self, interface, **kwargs):
        """
        获取已经注册的服务URL对象
        :param interface: com.ofpay.demo.api.UserProvider
        :param default:
        :return: 返回一个dict的服务集合
        """
        group = kwargs.get('group', '')
        version = kwargs.get('version', '')
        key = self.__to_key(interface, version, group)
        second = self.__service_provides.get(interface, {})
        return second.get(key, {})


if __name__ == '__main__':
    pass

