#encoding=utf-8
from urlparse import urlparse, parse_qsl

__author__ = 'caozupeng'


class ServiceURL(object):
    protocol = 'jsonrpc'
    location = ''  # ip+port
    path = ''  # like /com.qianmi.dubbo.UserProvider
    ip = '127.0.0.1'
    port = '9090'
    version = ''
    group = ''

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
            # print key
            self.__dict__[key] = value