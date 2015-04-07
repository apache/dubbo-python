import httplib
import json

from dubbo_client.registry import service_provides, add_provider_listener


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