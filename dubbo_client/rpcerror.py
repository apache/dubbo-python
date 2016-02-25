# coding=utf-8
__author__ = 'caozupeng'

dubbo_client_errors = {}


class DubboClientError(RuntimeError):
    code = None
    message = None
    data = None

    def __init__(self, message=None, data=None, code=None):
        RuntimeError.__init__(self)
        self.message = message or self.message
        self.data = data
        self.code = code or self.code
        assert self.code, "Error without code is not allowed."

    def __str__(self):
        return "DubboError({code}): {message}".format(
            code=self.code,
            message=str(self.message)
        )

    def __unicode__(self):
        return u"DubboClientError({code}): {message}".format(
            code=self.code,
            message=self.message
        )


class MethodNotFound(DubboClientError):
    code = -32601
    message = u"The method does not exist / is not available."

    def __init__(self, message=None, data=None):
        DubboClientError.__init__(self, message=message, data=data)


class ConnectionFail(DubboClientError):
    code = 504
    message = u'connect failed {0}'

    def __init__(self, message=None, data=None):
        message = self.message.format(data)
        DubboClientError.__init__(self, message=message, data=data)


class NoProvider(DubboClientError):
    code = 5050
    message = u'No provide name {0}'
    provide_name = u''

    def __init__(self, message=None, data=None):
        self.provide_name = data
        DubboClientError.__init__(self, message=self.message.format(data), data=data)


class InvalidParams(DubboClientError):
    code = -32602
    message = u"Invalid method parameter(s)."

    def __init__(self, message=None, data=None):
        DubboClientError.__init__(self, message=message, data=data)


class InternalError(DubboClientError):
    code = -32603
    message = u"Internal JSON-RPC error."

    def __init__(self, message=None, data=None):
        DubboClientError.__init__(self, message=message, data=data)


class InvalidRequest(DubboClientError):
    code = -32600
    message = u"The JSON sent is not a valid Request object."

    def __init__(self, message=None, data=None):
        DubboClientError.__init__(self, message=message, data=data)


class UserDefinedError(DubboClientError):
    code = -32000
    message = u'User defined error happend'

    def __init__(self, message=None, data=None):
        DubboClientError.__init__(self, message=message, data=data)


dubbo_client_errors[MethodNotFound.code] = MethodNotFound
dubbo_client_errors[NoProvider.code] = NoProvider
dubbo_client_errors[ConnectionFail.code] = ConnectionFail
dubbo_client_errors[InvalidParams.code] = InvalidParams
dubbo_client_errors[InternalError.code] = InternalError
dubbo_client_errors[InvalidRequest.code] = InvalidRequest
dubbo_client_errors[UserDefinedError.code] = UserDefinedError
