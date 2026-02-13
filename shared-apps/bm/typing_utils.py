from typing import Callable, TypeVar

T_Callable = TypeVar('T_Callable', bound=Callable)
T_Decorated_Function = TypeVar('T_Decorated_Function', bound=Callable)
