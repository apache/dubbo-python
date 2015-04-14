# coding=utf-8
from dubbo_client import ApplicationConfig

__author__ = 'caozupeng'


def test_application_config_new():
    application_config = ApplicationConfig('test_app', version='2.0.0', owner='caozupeng', error='ssd')
    assert application_config.architecture == 'web'
    assert application_config.name == 'test_app'
    assert application_config.environment == 'run'
    assert application_config.version == '2.0.0'
    assert 'owner' in application_config.__dict__
    assert 'ssd' not in application_config.__dict__
