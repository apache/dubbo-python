# coding=utf-8
import time
import os
import socket
import struct
from threading import Thread
import urllib
import logging
import logging.config
import os.path

from kazoo.protocol.states import KazooState

from kazoo.client import KazooClient

from dubbo_client.config import ApplicationConfig
from dubbo_client.common import ServiceURL

__author__ = 'caozupeng'

# 创建一个logger
if os.path.exists('logging.conf'):
    logging.config.fileConfig('logging.conf')
else:
    logging.basicConfig()
logger = logging.getLogger('dubbo')


class Registry(object):
    """
    所有注册过的服务端将在这里
    interface=com.ofpay.demo.DemoService
    location = ip:port/url 比如 172.19.20.111:38080/com.ofpay.demo.DemoService2
    providername = servicename|version|group
    dict 格式为{interface:{providername:{ip+port:service_url}}}

    """
    _service_provides = {}

    def _do_event(self, event):
        """
        protect方法，处理回调，留给子类实现
        :param event:
        :return:
        """
        pass

    def _do_config_event(self, event):
        """
        protect方法，处理管理台的禁用，倍权，半权等操作
        :param event:
        :return:
        """
        pass

    def register(self, interface, **kwargs):
        """
        客户端注册到注册中心，亮出自己的身份
        :param interface:
        :param kwargs:
        :return:
        """
        pass

    def subscribe(self, interface, **kwargs):
        """
        监听注册中心的服务上下线
        :param provide_name: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :param kwargs: version , group
        :return: 无返回
        """
        pass

    def get_provides(self, interface, **kwargs):
        """
        获取已经注册的服务URL对象
        :param interface: com.ofpay.demo.api.UserProvider
        :param default:
        :return: 返回一个dict的服务集合
        """
        group = kwargs.get('group', '')
        version = kwargs.get('version', '')
        key = self._to_key(interface, version, group)
        second = self._service_provides.get(interface, {})
        return second.get(key, {})

    def event_listener(self, event):
        """
        node provides上下线的监听回调函数
        :param event:
        :return:
        """
        self._do_event(event)

    def configuration_listener(self, event):
        """
        监听
        :param event:
        :return:
        """
        self._do_config_event(event)

    def _to_key(self, interface, versioin, group):
        """
        计算存放在内存中的服务的key，以接口、版本、分组计算
        :param interface: 接口 类似com.ofpay.demo.DemoProvider
        :param versioin: 版本 1.0
        :param group:  分组 product
        :return: key 字符串
        """
        return '{0}|{1}|{2}'.format(interface, versioin, group)

    def _add_node(self, interface, service_url):
        key = self._to_key(service_url.interface, service_url.version, service_url.group)
        second_dict = self._service_provides.get(interface)
        if second_dict:
            # 获取最内层的nest的dict
            inner_dict = second_dict.get(key)
            if inner_dict:
                inner_dict[service_url.location] = service_url
            else:
                second_dict[key] = {service_url.location: service_url}
        else:
            # create the second dict
            self._service_provides[interface] = {key: {service_url.location: service_url}}

    def _remove_node(self, interface, service_url):
        key = self._to_key(service_url.interface, service_url.version, service_url.group)
        second_dict = self._service_provides.get(interface)
        if second_dict:
            inner_dict = second_dict.get(key)
            if inner_dict:
                del inner_dict[service_url.location]

    def _compare_swap_nodes(self, interface, nodes):
        """
        比较，替换现有内存中的节点信息，节点url类似如下
        jsonrpc://192.168.2.1:38080/com.ofpay.demo.api.UserProvider?
        anyhost=true&application=demo-provider&default.timeout=10000&dubbo=2.4.10&
        environment=product&interface=com.ofpay.demo.api.UserProvider&
        methods=getUser,queryAll,queryUser,isLimit&owner=wenwu&pid=61578&
        side=provider&timestamp=1428904600188
        首先将url转为ServiceUrl对象，然保持到缓存中
        :param nodes: 节点列表
        :return: 不需要返回
        """
        # 如果已经存在，首先删除原有的服务的集合
        if interface in self._service_provides:
            del self._service_provides[interface]
            logger.debug("delete node {0}".format(interface))
        for child_node in nodes:
            node = urllib.unquote(child_node).decode('utf8')
            logger.debug('child of node is {0}'.format(node))
            if node.startswith('jsonrpc'):
                service_url = ServiceURL(node)
                self._add_node(interface, service_url)


class ZookeeperRegistry(Registry):
    _app_config = ApplicationConfig('default_app')
    _connect_state = 'UNCONNECT'

    def __init__(self, zk_hosts, application_config=None):
        if application_config:
            self._app_config = application_config
        self.__zk = KazooClient(hosts=zk_hosts)
        self.__zk.add_listener(self.__state_listener)
        self.__zk.start()

    def __state_listener(self, state):
        if state == KazooState.LOST:
            # Register somewhere that the session was lost
            self._connect_state = state
        elif state == KazooState.SUSPENDED:
            # Handle being disconnected from Zookeeper
            # print 'disconnect from zookeeper'
            self._connect_state = state
        else:
            # Handle being connected/reconnected to Zookeeper
            # print 'connected'
            self._connect_state = state

    def __unquote(self, origin_nodes):
        return (urllib.unquote(child_node).decode('utf8') for child_node in origin_nodes if child_node)

    def _do_event(self, event):
        # event.path 是类似/dubbo/com.ofpay.demo.api.UserProvider/providers 这样的
        # 如果要删除，必须先把/dubbo/和最后的/providers去掉
        # 将zookeeper中查询到的服务节点列表加入到一个dict中
        # zookeeper中保持的节点url类似如下
        logger.debug("receive event is {0}, event state is {1}".format(event, event.state))
        provide_name = event.path[7:event.path.rfind('/')]
        if event.state == 'CONNECTED':
            children = self.__zk.get_children(event.path, watch=self.event_listener)
            self._compare_swap_nodes(provide_name, self.__unquote(children))
        if event.state == 'DELETED':
            children = self.__zk.get_children(event.path, watch=self.event_listener)
            self._compare_swap_nodes(provide_name, self.__unquote(children))

    def _do_config_event(self, event):
        print event

    def register(self, interface, **kwargs):
        ip = self.__zk._connection._socket.getsockname()[0]
        params = {
            'interface': interface,
            'application': self._app_config.name,
            'application.version': self._app_config.version,
            'category': 'consumer',
            'dubbo': 'dubbo-client-py-1.0.0',
            'environment': self._app_config.environment,
            'method': '',
            'owner': self._app_config.owner,
            'side': 'consumer',
            'pid': os.getpid(),
            'version': '1.0'
        }
        url = 'consumer://{0}/{1}?{2}'.format(ip, interface, urllib.urlencode(params))
        # print urllib.quote(url, safe='')

        consumer_path = '{0}/{1}/{2}'.format('dubbo', interface, 'consumers')
        self.__zk.ensure_path(consumer_path)
        self.__zk.create(consumer_path + '/' + urllib.quote(url, safe=''), ephemeral=True)

    def subscribe(self, interface, **kwargs):
        """
        监听注册中心的服务上下线
        :param interface: 类似com.ofpay.demo.api.UserProvider这样的服务名
        :return: 无返回
        """
        version = kwargs.get('version', '')
        group = kwargs.get('group', '')
        providers_children = self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', interface, 'providers'),
                                                    watch=self.event_listener)
        logger.debug("watch node is {0}".format(providers_children))
        configurators_children = self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', interface, 'configurators'),
                                                        watch=self.configuration_listener)
        # 全部重新添加
        self._compare_swap_nodes(interface, self.__unquote(providers_children))


class MulticastRegistry(Registry):
    class _Loop(Thread):
        def __init__(self, address, callback):
            Thread.__init__(self)
            self.multicast_group, self.multicast_port = address.split(':')
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            # in osx we should use SO_REUSEPORT instead of SO_REUSEADDRESS
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            self.sock.bind(('', int(self.multicast_port)))
            mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.callback = callback

        def run(self):
            while True:
                event = self.sock.recv(10240)
                print event
                self.callback(event.rstrip())

        def set_mssage(self, msg):
            self.sock.sendto(msg, (self.multicast_group, int(self.multicast_port)))

    def __init__(self, address, application_config=None):
        if application_config:
            self._app_config = application_config
        self.event_loop = self._Loop(address, self.event_listener)
        self.event_loop.setDaemon(True)
        self.event_loop.start()

    def _do_event(self, event):
        if event.startswith('register'):
            url = event[9:]
            if url.startswith('jsonrpc'):
                service_provide = ServiceURL(url)
                self._add_node(service_provide.interface, service_provide)
        if event.startswith('unregister'):
            url = event[11:]
            if url.startswith('jsonrpc'):
                service_provide = ServiceURL(url)
                self._remove_node(service_provide.interface, service_provide)


if __name__ == '__main__':
    zk = KazooClient(hosts='192.168.59.103:2181')
    zk.start()
    parent_node = '{0}/{1}/{2}'.format('dubbo', 'com.ofpay.demo.api.UserProvider', '')
    nodes = zk.get_children(parent_node)
    for child_node in nodes:
        node = urllib.unquote(child_node).decode('utf8')
        print node
    configurators_node = '{0}/{1}/{2}'.format('dubbo', 'com.ofpay.demo.api.UserProvider', 'configurators')
    nodes = zk.get_children(configurators_node)
    for child_node in nodes:
        node = urllib.unquote(child_node).decode('utf8')
        print node
    providers_node = '{0}/{1}/{2}'.format('dubbo', 'com.ofpay.demo.api.UserProvider', 'providers')
    nodes = zk.get_children(providers_node)
    for child_node in nodes:
        node = urllib.unquote(child_node).decode('utf8')
        print node
    # zk.delete(parent_node+'/'+child_node, recursive=True)
    # registry = MulticastRegistry('224.5.6.7:1234')
    registry = ZookeeperRegistry('zookeeper:2181')
    registry.subscribe('com.ofpay.demo.api.UserProvider')
    print registry.get_provides('com.ofpay.demo.api.UserProvider')

    time.sleep(500)
