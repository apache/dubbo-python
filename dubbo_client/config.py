# coding=utf-8
__author__ = 'caozupeng'


class ApplicationConfig(object):
    # 应用名称
    name = 'default'
    # 模块版本
    version = '1.0.0'
    #应用负责人
    owner = ''
    #组织名(BU或部门)
    organization = ''
    #分层
    architecture = 'web'
    #环境，如：dev/test/run
    environment = 'run'

    def __init__(self, name, **kwargs):
        self.name = name
        object_property = dir(ApplicationConfig)
        for key, value in kwargs.items():
            if key in object_property:
                setattr(self, key, value)

    def __str__(self):
        return 'ApplicationConfig is {0}'.format(",".join(k + ':' + v for k, v in vars(self).iteritems()))


class ReferenceConfig(object):
    registry = None
    interface = ''
    version = ''


if __name__ == '__main__':
    application_config = ApplicationConfig('test_app', version='2.0.0', owner='caozupeng', error='ssd')
    print application_config