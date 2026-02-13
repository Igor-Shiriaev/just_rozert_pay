# Cache Fixture for Unit Tests

## Overview

The `disable_cache` fixture allows you to disable the memory cache during unit tests. This is useful when you want to test code that uses the cache without actually storing or retrieving cached values.

## Usage

### Basic Usage

Simply add the `disable_cache` fixture as a parameter to your test function:

```python
def test_my_function(disable_cache):
    # Your test code here
    # Cache operations will be disabled
    pass
```

### What the Fixture Does

1. **Clears the in-memory cache**: Removes all existing cached values
2. **Mocks Redis operations**: Prevents actual Redis calls during tests
3. **Mocks cache functions**: 
   - `memory_cache_get()` returns `None`
   - `memory_cache_get_set()` calls the `on_miss` function and returns its result
   - `memory_cache_set()` does nothing
   - `memory_cache_invalidate()` does nothing
4. **Restores cache state**: After the test, the original cache state is restored

### Example Tests

```python
from datetime import timedelta
from typing import List
from rozert_pay.common.helpers.cache import memory_cache_get, memory_cache_set, CacheKey

def test_cache_disabled(disable_cache):
    key: CacheKey = CacheKey("test_key")
    
    # This will return None instead of cached value
    result = memory_cache_get(key, List[str])
    assert result is None
    
    # This will not actually cache the value
    memory_cache_set(key, ["test"], timedelta(minutes=5))
    
    # Still returns None
    cached_result = memory_cache_get(key, List[str])
    assert cached_result is None

def test_cache_get_set_with_fixture(disable_cache):
    key: CacheKey = CacheKey("test_key")
    
    def on_miss() -> List[str]:
        return ["generated_data"]
    
    # This will call on_miss and return the result
    result = memory_cache_get_set(key, List[str], on_miss, timedelta(minutes=5))
    assert result == ["generated_data"]
```

### When to Use

- When testing code that depends on cache behavior
- When you want to ensure cache doesn't interfere with test isolation
- When testing cache miss scenarios
- When you want to avoid Redis dependencies in unit tests

### When Not to Use

- When testing the cache functionality itself
- When you need to verify actual cache behavior
- When testing cache invalidation logic

## Pros and Cons

### Pros
- ✅ Isolates tests from cache state
- ✅ Prevents Redis calls during tests
- ✅ Makes tests more predictable
- ✅ Faster test execution (no cache operations)
- ✅ Easy to use with simple fixture parameter

### Cons
- ❌ Doesn't test actual cache behavior
- ❌ May hide cache-related bugs
- ❌ Changes the behavior of the code under test
- ❌ Requires understanding of what gets mocked 