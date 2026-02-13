import abc
import logging
import time
from datetime import timedelta
from typing import Callable

from bm.utils import ReprMixin
from django.core.cache.backends.locmem import LocMemCache
from redis import Redis     # type: ignore

logger = logging.getLogger(__name__)


class ThrottledChannelClosed(Exception):
    pass


class Throttler(abc.ABC):

    @abc.abstractmethod
    def should_allow_request(self) -> bool:
        """ Returns whether task can be executed, or not
        Raises ThrottledChannelClosed in case channel is closed
        (count = 0, so no messages can pass through)
        """

    def process_request(
        self,
        on_discarded: Callable[[], None],
        on_paused: Callable[[], None],
        on_allowed: Callable[[], None]
    ) -> None:
        """ Generic function, for use throttler.

        Calls on_discarded if request was discarded and can't be sent
        Calls on_paused if request can't be allowed right now (throttled)
        Callse on_allowed if request is allowed
        """
        try:
            should_allow_request = self.should_allow_request()
        except ThrottledChannelClosed:
            return on_discarded()

        if not should_allow_request:
            return on_paused()

        on_allowed()


class DummyThrottler(Throttler):
    """ Throttler which allows all requests.
    """
    def should_allow_request(self) -> bool:
        return True


class LeakingBucketMeterThrottler(ReprMixin, Throttler):
    """ This throttler uses Leaking Bucket with counter algo:

    * Keep <counter> in redis - size of our bucket
    * With each incoming item - increment counter
    * During the time decrement counter with speed <count_per_window/window> item/sec
    * Allow request if current counter value <= self.count_per_window

    See https://en.wikipedia.org/wiki/Leaky_bucket#As_a_meter for more algo details.
    """
    repr_fields = ['key', 'window', 'count_per_window']
    redis_keys_ttl_sec = 600
    redis_client: Redis
    prefix: str

    def __init__(
        self, key: str, window: timedelta, count_per_window: int,
        memory_cache_ttl_sec: float = 1,
    ) -> None:
        assert self.redis_client

        self.key = key
        self.count_per_window = count_per_window
        assert count_per_window >= 0
        self.window = window
        self.cache = LocMemCache(f'throttler_mem_cache', {})
        self.memory_cache_ttl_sec = memory_cache_ttl_sec

    def should_allow_request(self) -> bool:
        if not self.count_per_window:
            # In case count_per_window = 0 we don't want to retry, but just stop execution.
            raise ThrottledChannelClosed

        # from_cache = self.cache.get(self.key)
        # if from_cache is False:
        #     # If request not allowed - don't hit redis for memory_cache_ttl_sec.
        #     # If request is allowed - skip cache, as we need to update state in redis.
        #     return False

        KEYS = [
            self.last_execution_data_key,
            self.counter_data_key,
        ]
        now = time.time()
        decrease_elem_per_sec = self.count_per_window / self.window.total_seconds()
        ARGV = [
            str(now),
            str(decrease_elem_per_sec),
            str(self.redis_keys_ttl_sec),
        ]

        # NOTE: Some notes on lua scripting:
        # * For details see https://redis.io/commands/eval
        # * All input and output types are converted to bytestring, so needs explicit conversion
        # * This script executed synchronously, so no conflicts can happen
        # * This script does all needed bucket calculations, and return arrays with elements:
        #   * result[0] - whether request is allowed, "true"/"false"
        #   * result[1-3] - some debug information
        # * Indexing in Lua starts from 1
        lua_script = '''
local now = tonumber(ARGV[1])
local decrease_elems_per_sec = tonumber(ARGV[2])
local keys_ttl = tonumber(ARGV[3])
local last_call_key = KEYS[1]
local bucket_key = KEYS[2]

local last_call = redis.call("get", last_call_key)
if not last_call then
    last_call = 0
end

local bucket = redis.call("get", bucket_key)
if not bucket then
    bucket = 0
end

bucket = tonumber(bucket)
last_call = tonumber(last_call)

-- Decrease bucket on count elements from last call
local decrease = decrease_elems_per_sec * (now - last_call)
local bucket_before = bucket
bucket = bucket - decrease

if bucket < 0 then bucket = 0 end

local allow_pass = false

if bucket < 1 then
    bucket = bucket + 1
    allow_pass = true
end

redis.call("set", last_call_key, now, "EX", keys_ttl)
redis.call("set", bucket_key, bucket, "EX", keys_ttl)

return {tostring(allow_pass), tostring(bucket_before), tostring(decrease), tostring(bucket)}
        '''
        allow_pass, *debug = self.redis_client.eval(    # type: ignore
            lua_script, len(KEYS), *KEYS, *ARGV,  # type: ignore
        )

        if allow_pass == b'true':
            return True
        elif allow_pass == b'false':
            self.cache.set(self.key, False, self.memory_cache_ttl_sec)
            return False

        raise RuntimeError()

    @property
    def counter_data_key(self) -> str:
        return f'{self.prefix}:{self.__class__.__qualname__}:{self.key}:count_registered_tasks'

    @property
    def last_execution_data_key(self) -> str:
        return f'{self.prefix}:{self.__class__.__qualname__}:{self.key}:last_execution'


class UnionThrottler(Throttler):
    def __init__(self, *throttlers: Throttler):
        self.throttlers = throttlers

    def __repr__(self) -> str:
        acc = [repr(t) for t in self.throttlers]
        return f'{self.__class__.__name__}({", ".join(acc)})'

    def should_allow_request(self) -> bool:
        return max(
            t.should_allow_request()
            for t in self.throttlers
        )
