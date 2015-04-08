# coding=utf-8
import urllib
from urlparse import urlparse, parse_qsl

from kazoo.protocol.states import KazooState


__author__ = 'caozupeng'
from kazoo.client import KazooClient
import logging

logging.basicConfig()
zk = KazooClient(hosts='172.19.65.33:2181', read_only=True)
service_provides = {}


def state_listener(state):
    if state == KazooState.LOST:
        # Register somewhere that the session was lost
        print 'session lost'
    elif state == KazooState.SUSPENDED:
        # Handle being disconnected from Zookeeper
        print 'disconnect from zookeeper'
    else:
        # Handle being connected/reconnected to Zookeeper
        print 'connected'


zk.add_listener(state_listener)


class JsonProvide(object):
    protocol = 'jsonrpc'
    location = ''
    path = ''
    ip = '127.0.0.1'
    port = '9090'

    def __init__(self, url):
        result = urlparse(url)
        self.protocol = result[0]
        self.location = result[1]
        self.path = result[2]
        if self.location.find(':') > -1:
            self.ip, self.port = result[1].split(':')
        params = parse_qsl(result[4])
        for key, value in params:
            # url has a default.timeout property, but it can not add in python object
            # so keep the last one
            pos = key.find('.')
            if pos > -1:
                key = key[pos + 1:]
            print key
            self.__dict__[key] = value


def node_listener(event):
    print event


def add_provider_listener(provide_name):
    children = zk.get_children('{0}/{1}/{2}'.format('dubbo', provide_name, 'providers'), watch=node_listener)
    for child_node in children:
        url = urllib.unquote(child_node).decode('utf8')
        if url.startswith('jsonrpc'):
            provide = JsonProvide(url)
            service_key = service_provides.get(provide.interface)
            if service_key:
                service_key[provide.location] = provide
            else:
                service_provides[provide.interface] = {provide.location: provide}


zk.start()

if __name__ == '__main__':
    zk.start()
    if zk.exists("/dubbo"):
        # Print the version of a node and its data
        # children = zk.get_children("/dubbo")
        # print "There are {0} children".format(len(children))
        # for node in children:
        # print node
        add_provider_listener('com.ofpay.demo.api.UserProvider')

