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

from urllib2 import HTTPError

from pyjsonrpc import HttpClient, JsonRpcError

from dubbo.connection.connections import connection_pool
from dubbo_client.registry import Registry
from dubbo_client.rpcerror import ConnectionFail, dubbo_client_errors, InternalError, DubboClientError


class DubboClient(object):
    interface = ''
    group = ''
    version = ''
    protocol = ''

    protocol_methods = {}

    class _Method(object):

        def __init__(self, client_instance, method):
            self.client_instance = client_instance
            self.method = method

        def __call__(self, *args, **kwargs):
            return self.client_instance.call(self.method, *args, **kwargs)

    def __init__(self, interface, registry, **kwargs):
        assert isinstance(registry, Registry)
        self.interface = interface
        self.registry = registry
        self.group = kwargs.get('group', '')
        self.version = kwargs.get('version', '')
        self.protocol = kwargs.get('protocol', '')
        self.registry.subscribe(interface)
        self.registry.register(interface)

        self.protocol_methods = {'jsonrpc': self.__jsonrpc_call__, 'dubbo': self.__dubbo_call__}

    def call(self, method, *args, **kwargs):
        provider = self.registry.get_random_provider(self.interface, version=self.version, group=self.group,
                                                     protocol=self.protocol)
        timeout = int(provider.timeout) / 1000

        return self.protocol_methods[provider.protocol](method, provider, timeout, *args, **kwargs)

    def __dubbo_call__(self, method, provider, timeout, *args, **kwargs):

        if not isinstance(args, (list, tuple)):
            args = [args]

        request_param = {
            'dubbo_version': provider.dubbo,
            'version': provider.version,
            'path': provider.interface if not provider.group else provider.group + '/' + provider.interface,
            'method': method,
            'arguments': args
        }

        result = connection_pool.get(provider.location, request_param, timeout, **kwargs)
        return result

    def __jsonrpc_call__(self, method, provider, timeout, *args, **kwargs):
        client = HttpClient(url="http://{0}{1}".format(provider.location, provider.path), timeout=timeout)
        try:
            return client.call(method, *args, **kwargs)
        except HTTPError, e:
            raise ConnectionFail(None, e.filename)
        except JsonRpcError, error:
            if error.code in dubbo_client_errors:
                raise dubbo_client_errors[error.code](message=error.message, data=error.data)
            else:
                raise DubboClientError(code=error.code, message=error.message, data=error.data)
        except Exception, ue:
            if hasattr(ue, 'reason'):
                raise InternalError(ue.message, ue.reason)
            else:
                raise InternalError(ue.message, None)

    def __call__(self, method, *args, **kwargs):
        """
        Redirects the direct call to *self.call*
        """
        return self.call(method, *args, **kwargs)

    def __getattr__(self, method):
        """
        Allows the usage of attributes as *method* names.
        """
        return self._Method(client_instance=self, method=method)


if __name__ == '__main__':
    pass
