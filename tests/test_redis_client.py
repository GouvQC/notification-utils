import pytest
from freezegun import freeze_time
from unittest.mock import Mock
from freezegun import freeze_time

from notifications_utils.clients.redis import (
    daily_limit_cache_key,
    rate_limit_cache_key
)
from notifications_utils.clients.redis.redis_client import RedisClient


class RedisMock(Mock):

    def __init__(self):
        pass

    def zadd(self, cache_key, score, item):
        pass

    def zremrangebyscore(self, cache_key, min, max):
        pass

    def zcard(self, cache_key):
        pass

    def expire(self, cache_key, interval):
        pass

    def execute(self):
        pass


my_redis_mock = RedisMock()


@pytest.fixture(scope='function')
def mocked_redis_client(app, mocker):
    app.config['REDIS_ENABLED'] = True
    return build_redis_client(app, mocker)


def build_redis_client(app, mocker):
    redis_client = RedisClient()
    redis_client.init_app(app)
    mocker.patch.object(redis_client.redis_store, 'get', return_value=100)
    mocker.patch.object(redis_client.redis_store, 'set')
    mocker.patch.object(redis_client.redis_store, 'hincrby')
    mocker.patch.object(redis_client.redis_store, 'hgetall',
                        return_value={b'template-1111': b'8', b'template-2222': b'8'})
    mocker.patch.object(redis_client.redis_store, 'hmset')
    mocker.patch.object(redis_client.redis_store, 'expire')
    mocker.patch.object(redis_client.redis_store, 'pipeline', return_value=my_redis_mock)

    return redis_client


def test_should_not_raise_exception_if_raise_set_to_false(app):
    app.config['REDIS_ENABLED'] = True
    redis_client = RedisClient()
    redis_client.init_app(app)
    redis_client.redis_store.get = Mock(side_effect=Exception())
    redis_client.redis_store.set = Mock(side_effect=Exception())
    redis_client.redis_store.incr = Mock(side_effect=Exception())
    redis_client.redis_store.pipeline = Mock(side_effect=Exception())
    assert redis_client.get('test') is None
    assert redis_client.set('test', 'test') is None
    assert redis_client.incr('test') is None
    assert redis_client.exceeded_rate_limit('test', 100, 100) is False


def test_should_raise_exception_if_raise_set_to_true(app):
    app.config['REDIS_ENABLED'] = True
    redis_client = RedisClient()
    redis_client.init_app(app)
    redis_client.redis_store.get = Mock(side_effect=Exception('get failed'))
    redis_client.redis_store.set = Mock(side_effect=Exception('set failed'))
    redis_client.redis_store.incr = Mock(side_effect=Exception('inc failed'))
    redis_client.redis_store.pipeline = Mock(side_effect=Exception('pipeline failed'))
    with pytest.raises(Exception) as e:
        redis_client.get('test', raise_exception=True)
    assert str(e.value) == 'get failed'
    with pytest.raises(Exception) as e:
        redis_client.set('test', 'test', raise_exception=True)
    assert str(e.value) == 'set failed'
    with pytest.raises(Exception) as e:
        redis_client.incr('test', raise_exception=True)
    assert str(e.value) == 'inc failed'
    with pytest.raises(Exception) as e:
        redis_client.exceeded_rate_limit('test', 100, 200, raise_exception=True)
    assert str(e.value) == 'pipeline failed'


def test_should_not_call_set_if_not_enabled(mocked_redis_client):
    mocked_redis_client.active = False
    assert not mocked_redis_client.set('key', 'value')
    mocked_redis_client.redis_store.set.assert_not_called()


def test_should_call_set_if_enabled(mocked_redis_client):
    mocked_redis_client.set('key', 'value')
    mocked_redis_client.redis_store.set.assert_called_with('key', 'value', None, None, False, False)


def test_should_not_call_get_if_not_enabled(mocked_redis_client):
    mocked_redis_client.active = False
    mocked_redis_client.get('key')
    mocked_redis_client.redis_store.get.assert_not_called()


def test_should_not_call_redis_if_not_enabled_for_rate_limit_check(mocked_redis_client):
    mocked_redis_client.active = False
    mocked_redis_client.exceeded_rate_limit('key', 100, 200)
    mocked_redis_client.redis_store.pipeline.assert_not_called()


def test_should_call_get_if_enabled(mocked_redis_client):
    assert mocked_redis_client.get('key') == 100
    mocked_redis_client.redis_store.get.assert_called_with('key')


def test_should_build_cache_key_service_and_action(sample_service):
    with freeze_time("2016-01-01 12:00:00.000000"):
        assert daily_limit_cache_key(sample_service.id) == '{}-2016-01-01-count'.format(sample_service.id)


def test_should_build_daily_limit_cache_key(sample_service):
    assert rate_limit_cache_key(sample_service.id, 'TEST') == '{}-TEST'.format(sample_service.id)


def test_decrement_hash_value_should_decrement_value_by_one_for_key(mocked_redis_client):
    key = '12345'
    value = "template-1111"

    mocked_redis_client.decrement_hash_value(key, value, -1)
    mocked_redis_client.redis_store.hincrby.assert_called_with(key, value, -1)


def test_incr_hash_value_should_increment_value_by_one_for_key(mocked_redis_client):
    key = '12345'
    value = "template-1111"

    mocked_redis_client.increment_hash_value(key, value)
    mocked_redis_client.redis_store.hincrby.assert_called_with(key, value, 1)


def test_get_all_from_hash_returns_hash_for_key(mocked_redis_client):
    key = '12345'
    assert mocked_redis_client.get_all_from_hash(key) == {b'template-1111': b'8', b'template-2222': b'8'}
    mocked_redis_client.redis_store.hgetall.assert_called_with(key)


def test_set_hash_and_expire(mocked_redis_client):
    key = 'hash-key'
    values = {'key': 10}
    mocked_redis_client.set_hash_and_expire(key, values, 1)
    mocked_redis_client.redis_store.hmset.assert_called_with(key, values)
    mocked_redis_client.redis_store.expire.assert_called_with(key, 1)


@freeze_time("2001-01-01 12:00:00.000000")
def test_should_add_correct_calls_to_the_pipe(mocked_redis_client, mocker):
    zadd = mocker.patch('tests.test_redis_client.RedisMock.zadd')
    zremrangebyscore = mocker.patch('tests.test_redis_client.RedisMock.zremrangebyscore')
    zcard = mocker.patch('tests.test_redis_client.RedisMock.zcard')
    expire = mocker.patch('tests.test_redis_client.RedisMock.expire')
    execute = mocker.patch('tests.test_redis_client.RedisMock.execute')

    mocked_redis_client.exceeded_rate_limit("key", 100, 100)
    assert mocked_redis_client.redis_store.pipeline.called
    zadd.assert_called_with("key", 978350400.0, 978350400.0)
    zremrangebyscore.assert_called_with("key", '-inf', 978350300.0)
    zcard.assert_called_with("key")
    expire.assert_called_with("key", 100)
    assert execute.called


@freeze_time("2001-01-01 12:00:00.000000")
def test_should_fail_request_if_over_limit(mocked_redis_client, mocker):
    mocker.patch('tests.test_redis_client.RedisMock.execute', return_value=[True, True, 100, True])
    assert mocked_redis_client.exceeded_rate_limit("key", 99, 100)


@freeze_time("2001-01-01 12:00:00.000000")
def test_should_allow_request_if_not_over_limit(mocked_redis_client, mocker):
    mocker.patch('tests.test_redis_client.RedisMock.execute', return_value=[True, True, 100, True])
    assert not mocked_redis_client.exceeded_rate_limit("key", 101, 100)


@freeze_time("2001-01-01 12:00:00.000000")
def test_should_allow_request_if_not_over_limit(mocked_redis_client, mocker):
    mocker.patch('tests.test_redis_client.RedisMock.execute', return_value=[True, True, 100, True])
    assert not mocked_redis_client.exceeded_rate_limit("key", 101, 100)


def test_should_not_call_set_if_not_enabled(mocked_redis_client):
    mocked_redis_client.active = False

    assert not mocked_redis_client.exceeded_rate_limit('key', 100, 100)
    assert not mocked_redis_client.redis_store.pipeline.called
