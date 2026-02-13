import enum


class AccountType(enum.Enum):
    PUBLIC_STATIC = 'public_static'
    PARTNERS = 'partners'
    PRIVATE = 'private'
    BACKEND_INTERNAL = 'backend_internal'
    ANALYTICS = 'analytics'

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}.{self.name}'
