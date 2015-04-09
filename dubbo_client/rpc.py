import httplib
import json
import random
from urllib2 import HTTPError
from pyjsonrpc import HttpClient, JsonRpcError

from dubbo_client.registry import service_provides, add_provider_listener
from dubbo_client.rpcerror import NoProvider, ConnectionFail, dubbo_client_errors


__author__ = 'caozupeng'


def raw_client(service_interface, app_params):
    headers = {"Content-type": "application/json-rpc",
               "Accept": "text/json"}
    provides = service_provides.get(service_interface, ())
    if len(provides) > 0:
        location, first = provides.items().pop()
        h1 = httplib.HTTPConnection(first.ip, port=int(first.port))
        h1.request("POST", first.path, json.dumps(app_params), headers)
        response = h1.getresponse()
        return response.read(), None
    else:
        return None, 'can not find the provide of {0}'.format(service_interface)


class DubboClient(object):
    interface = ''

    class _Method(object):

        def __init__(self, client_instance, method):
            self.client_instance = client_instance
            self.method = method

        def __call__(self, *args, **kwargs):
            return self.client_instance.call(self.method, *args, **kwargs)

    def __init__(self, interface):
        self.interface = interface
        add_provider_listener(interface)

    def call(self, method, *args, **kwargs):
        provides = service_provides.get(self.interface, {})
        if len(provides) == 0:
            raise NoProvider('can not find provide', self.interface)
        location, provide = random.choice(provides.items())
        print 'location is {0}'.format(location)
        client = HttpClient(url="http://{0}{1}".format(location, provide.path))
        try:
            return client.call(method, *args, **kwargs)
        except HTTPError, e:
            raise ConnectionFail(None, e.filename)
        except JsonRpcError, error:
            raise dubbo_client_errors.get(error.code, None)

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
    app_params = {
        "jsonrpc": "2.0",
        "method": "getUser",
        "params": ["A001"],
        "id": 1
    }
    service_interface = 'com.ofpay.demo.api.UserProvider'
    add_provider_listener(service_interface)
    ret, error = raw_client(service_interface, app_params)
    if not error:
        print json.loads(ret, encoding='utf-8')