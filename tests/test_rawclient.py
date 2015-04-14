from pyjsonrpc import HttpClient

__author__ = 'caozupeng'

def test_client_every_new():
    user_provider = HttpClient(url="http://{0}{1}".format('172.19.3.111:38081/', 'com.ofpay.demo.api.UserProvider2'))
    print user_provider.getUser('A003')
    print user_provider.queryUser(
        {u'age': 18, u'time': 1428463514153, u'sex': u'MAN', u'id': u'A003', u'name': u'zhangsan'})
    print user_provider.queryAll()
    print user_provider.isLimit('MAN', 'Joe')
    print user_provider('getUser', 'A005')


if __name__ == '__main__':
    test_client_every_new()