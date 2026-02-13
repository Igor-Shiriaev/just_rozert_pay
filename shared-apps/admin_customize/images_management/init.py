from typing import Any, Callable, cast

from s3.entities import AccountConfigsRegistry

_s3: AccountConfigsRegistry = cast(AccountConfigsRegistry, None)
_s3_factory: Callable[[], AccountConfigsRegistry] = cast(Any, None)


def set_s3(s3: AccountConfigsRegistry) -> None:
    global _s3
    _s3 = s3


def set_s3_factory(s3_factory: Callable[[], AccountConfigsRegistry]) -> None:
    global _s3_factory
    _s3_factory = s3_factory


def get_s3() -> AccountConfigsRegistry:
    if not _s3 and not _s3_factory:  # type: ignore
        raise RuntimeError('You must set s3 (factory) first, using set_s3 or set_s3_factory methods')
    return _s3 or _s3_factory()
