# coding=utf-8

"""
 Licensed to the Apache Software Foundation (ASF) under one or more
 contributor license agreements.  See the NOTICE file distributed with
 this work for additional information regarding copyright ownership.
 The ASF licenses this file to You under the Apache License, Version 2.0
 (the "License"); you may not use this file except in compliance with
 the License.  You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.

"""


import logging.config
import os
import os.path
import random
import socket
import struct
import threading
import time
import urllib
from threading import Thread

from kazoo.client import KazooClient
from kazoo.protocol.states import KazooState

from dubbo_client.common import ServiceURL
from dubbo_client.config import ApplicationConfig
from dubbo_client.rpcerror import NoProvider


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

    def __init__(self):
        self._service_providers = {}
        self._mutex = threading.Lock()

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

    def get_providers(self, interface, **kwargs):
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

    def get_random_provider(self, interface, **kwargs):
        """
        根据权重和是否禁用获取一个provider
        :param interface:
        :param kwargs:
        :return:
        """
        group = kwargs.get('group', '')
        version = kwargs.get('version', '')
        key = self._to_key(interface, version, group)
        second_dict = self._service_providers.get(interface, {})
        service_url_list = [service_url for service_url in second_dict.get(key, {}).itervalues() if
                            not service_url.disabled and service_url.weight > 0]
        if not service_url_list:
            raise NoProvider('can not find provider', interface)

        total_weight = 0
        same_weight = True
        last_service_url = None
        for service_url in service_url_list:
            total_weight += service_url.weight
            if same_weight and last_service_url and last_service_url.weight != service_url.weight:
                same_weight = False
            last_service_url = service_url

        if total_weight > 0 and not same_weight:
            offset = random.randint(0, total_weight - 1)
            for service_url in service_url_list:
                offset -= service_url.weight
                if offset < 0:
                    return service_url

        return random.choice(service_url_list)

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

    def _to_key(self, interface, version, group):
        """
        计算存放在内存中的服务的key，以接口、版本、分组计算
        :param interface: 接口 类似com.ofpay.demo.DemoProvider
        :param version: 版本 1.0
        :param group:  分组 product
        :return: key 字符串
        """
        return '{0}|{1}|{2}'.format(interface, version, group)

    def _add_node(self, interface, service_url):
        key = self._to_key(service_url.interface, service_url.version, service_url.group)
        second_dict = self._service_providers.get(interface)
        if second_dict:
            # 获取最内层的nest的dict
            inner_dict = second_dict.get(key)
            if inner_dict:
                inner_dict[service_url.location] = service_url
            else:
                second_dict[key] = {service_url.location: service_url}
        else:
            # create the second dict
            self._service_providers[interface] = {key: {service_url.location: service_url}}

    def _remove_node(self, interface, service_url):
        key = self._to_key(service_url.interface, service_url.version, service_url.group)
        second_dict = self._service_providers.get(interface)
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
        if self._mutex.acquire():
            # 存在并发问题,需要线程锁
            try:
                # 如果已经存在，首先删除原有的服务的集合
                if interface in self._service_providers:
                    del self._service_providers[interface]
                    logger.debug("delete node {0}".format(interface))
                for child_node in nodes:
                    node = urllib.unquote(child_node).decode('utf8')
                    logger.debug('child of node is {0}'.format(node))
                    if node.startswith('jsonrpc'):
                        service_url = ServiceURL(node)
                        self._add_node(interface, service_url)
            except Exception as e:
                logger.warn('swap json-rpc provider error %s', str(e))
            finally:
                self._mutex.release()

    def _set_provider_configuration(self, interface, nodes):
        """
        设置provider配置
        :param interface:
        :param nodes:
        :return:
        """
        if not nodes:
            return
        try:
            configuration_dict = {}
            for _child_node in nodes:
                _node = urllib.unquote(_child_node).decode('utf8')
                if _node.startswith('override'):
                    service_url = ServiceURL(_node)
                    key = self._to_key(interface, service_url.version, service_url.group)

                    if key not in configuration_dict:
                        configuration_dict[key] = {}
                    if service_url.location not in configuration_dict[key]:
                        configuration_dict[key][service_url.location] = []
                    configuration_dict[key][service_url.location].append(_node)

            if interface in self._service_providers:
                provider_dict = self._service_providers.get(interface)
                for provider_key, second_dict in provider_dict.iteritems():
                    for service_location, service_url in second_dict.iteritems():
                        configuration_service_urls = configuration_dict.get(provider_key, {}).get(service_location)
                        if not configuration_service_urls:
                            service_url.init_default_config()
                        else:
                            service_url.set_config(configuration_service_urls)

        except Exception as e:
            logger.warn('set provider configuration error %s', str(e))


class ZookeeperRegistry(Registry):
    _app_config = ApplicationConfig('default_app')
    _connect_state = 'UNCONNECT'

    def __init__(self, zk_hosts, application_config=None):
        Registry.__init__(self)
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
        logger.info("receive event is {0}, event state is {1}".format(event, event.state))
        provide_name = event.path[7:event.path.rfind('/')]
        if event.state in ['CONNECTED', 'DELETED']:
            children = self.__zk.get_children(event.path, watch=self.event_listener)
            self._compare_swap_nodes(provide_name, self.__unquote(children))
            configurators_nodes = self._get_provider_configuration(provide_name)
            self._set_provider_configuration(provide_name, configurators_nodes)
        print self._service_providers

    def _do_config_event(self, event):
        """
        zk的目录路径为 /dubbo/com.qianmi.pc.api.es.item.EsGoodsQueryProvider/configurators
        :param event:
        :return:
        """
        logger.info("receive config event is {0}, event state is {1}".format(event, event.state))
        provide_name = event.path[7:event.path.rfind('/')]
        configurators_nodes = self._get_provider_configuration(provide_name)
        self._set_provider_configuration(provide_name, configurators_nodes)

        print self._service_providers

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
        self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', interface, 'configurators'),
                               watch=self.configuration_listener)
        # 全部重新添加
        self._compare_swap_nodes(interface, self.__unquote(providers_children))

        configurators_nodes = self._get_provider_configuration(interface)
        self._set_provider_configuration(interface, configurators_nodes)

    def _get_provider_configuration(self, interface):
        """
        获取dubbo自定义配置数据，从"/dubbo/{interface}/configurators" 路径下获取配置
        :param interface:
        :return:
        """
        try:
            configurators_nodes = self.__zk.get_children('{0}/{1}/{2}'.format('dubbo', interface, 'configurators'),
                                                         watch=self.configuration_listener)
            logger.debug("configurators node is {0}".format(configurators_nodes))
            return self.__unquote(configurators_nodes)
        except Exception as e:
            logger.warn("get provider %s configuration error %s", interface, str(e))


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
        Registry.__init__(self)
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
    print registry.get_providers('com.ofpay.demo.api.UserProvider')

    time.sleep(500)
