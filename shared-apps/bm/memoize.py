from bm.constants import LOCAL_FILE_CACHE, LOCAL_MEMORY_CACHE
from django.core.cache import caches
from memoize import Memoizer

_memoizer = Memoizer(cache=caches[LOCAL_MEMORY_CACHE])

memoize_cache = _memoizer.memoize
delete_memoized = _memoizer.delete_memoized
delete_memoized_verhash = _memoizer.delete_memoized_verhash

memoize_file = Memoizer(cache=caches[LOCAL_FILE_CACHE]).memoize
