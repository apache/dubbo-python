# coding=utf-8
import Queue
from threading import Thread
import urllib

from kazoo.protocol.states import KazooState

from dubbo_client.common import ServiceProvider


__author__ = 'caozupeng'
from kazoo.client import KazooClient
import logging

logging.basicConfig()
zk = KazooClient(hosts='172.19.65.33:2181', read_only=True)
"""
所有注册过的服务端将在这里
格式为{providername:{ip+port:service}}
providername = group_version_servicename
"""
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


def node_listener(event):
    print event
    event_queue.put(event)


def handler_urls(urls):
    for child_node in urls:
        url = urllib.unquote(child_node).decode('utf8')
        if url.startswith('jsonrpc'):
            provide = ServiceProvider(url)
            service_key = service_provides.get(provide.interface)
            if service_key:
                service_key[provide.location] = provide
            else:
                service_provides[provide.interface] = {provide.location: provide}


def add_provider_listener(provide_name):
    #如果已经存在，首先删除原有的服务的集合
    if provide_name in service_provides:
        del service_provides[provide_name]
    children = zk.get_children('{0}/{1}/{2}'.format('dubbo', provide_name, 'providers'), watch=node_listener)
    #全部重新添加
    handler_urls(children)


num_worker_threads = 2


def worker():
    while True:
        event = event_queue.get()
        do_event(event)
        event_queue.task_done()


event_queue = Queue.Queue()


def do_event(event):
    # event.path 是类似/dubbo/com.ofpay.demo.api.UserProvider/providers 这样的
    # 如果要删除，必须先把/dubbo/和最后的/providers去掉
    provide_name = event.path[7:event.path.rfind('/')]
    if provide_name in service_provides:
        del service_provides[provide_name]
    if event.state == 'CONNECTED':
        children = zk.get_children(event.path, watch=node_listener)
        handler_urls(children)
    if event.state == 'DELETED':
        children = zk.get_children(event.path, watch=node_listener)
        handler_urls(children)

for i in range(num_worker_threads):
    t = Thread(target=worker)
    t.daemon = False
    t.start()


zk.start()
event_queue.join()

if __name__ == '__main__':
    zk.start()
    if zk.exists("/dubbo"):
        add_provider_listener('com.ofpay.demo.api.UserProvider')

