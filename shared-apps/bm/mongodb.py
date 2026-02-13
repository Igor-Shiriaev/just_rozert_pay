import os
from copy import deepcopy
from decimal import Decimal
from importlib import import_module
from threading import local
from typing import Iterator, cast, Any

from bson.codec_options import TypeCodec, TypeRegistry
from bson.decimal128 import Decimal128
from django.utils.functional import cached_property
from pymongo.database import Database


class DecimalCodec(TypeCodec):
    python_type = Decimal
    bson_type = Decimal128

    def transform_python(self, value: Decimal) -> Decimal128:
        return Decimal128(value)

    def transform_bson(self, value: Decimal128) -> Decimal:
        return value.to_decimal()


decimal_codec = DecimalCodec()


type_registry = TypeRegistry(
    [
        decimal_codec,
    ]
)


class MongoDBConnectionHandler:
    def __init__(
        self,
        *,
        default_host: str,
        default_port: int = 27017,
        default_pool_size: int = 10,
        default_replica_set: str = None,
        databases: dict = None,  # config, redefining default settings for each database
        appname: str = None,
    ) -> None:
        self._host = default_host
        self._port = default_port
        self._pool_size = default_pool_size
        self._replica_set = default_replica_set
        self._databases = databases
        self._appname = appname or os.environ.get('PGAPPNAME', 'backend')
        self._connections = local()

    @cached_property
    def databases(self) -> dict:
        return cast(dict, self._databases)

    def ensure_defaults(self, db_name_alias: str) -> None:
        try:
            conn = self.databases[db_name_alias]
        except KeyError:
            raise ValueError(f'Unknown database {db_name_alias}')

        conn.setdefault('host', self._host)
        conn.setdefault('port', self._port)
        conn.setdefault('replicaSet', self._replica_set)
        conn.setdefault('connectTimeoutMS', 10000)
        conn.setdefault('socketTimeoutMS', 10000)
        conn.setdefault('waitQueueTimeoutMS', 10000)
        conn.setdefault('maxPoolSize', self._pool_size)
        conn.setdefault('authSource', 'admin')
        conn.setdefault('name', db_name_alias)
        conn.setdefault('tz_aware', True)
        conn.setdefault('client_module', 'pymongo')
        conn.setdefault('client_class', 'MongoClient')
        conn.setdefault('type_registry', type_registry)
        conn.setdefault('uuidRepresentation', 'pythonLegacy')
        conn.setdefault('w', 'majority')
        conn.setdefault('appname', self._appname)

    def _get_client(self, db_name_alias: str, **custom_params: Any) -> Any:
        self.ensure_defaults(db_name_alias)
        connection_settings = deepcopy(self.databases[db_name_alias])
        if custom_params is not None:
            connection_settings.update(custom_params)

        # Extract all reference keys before client instance construction.
        connection_settings.pop('name')
        client_module_name = connection_settings.pop('client_module')
        client_class_name = connection_settings.pop('client_class')

        client_module = import_module(client_module_name)
        client_class = getattr(client_module, client_class_name)
        client = client_class(**connection_settings)

        return client

    def __getitem__(self, db_name_alias: str) -> Database:
        if hasattr(self._connections, db_name_alias):
            return getattr(self._connections, db_name_alias)
        client = self._get_client(db_name_alias)
        _db: Database = client[self.databases[db_name_alias]['name']]
        setattr(self._connections, db_name_alias, _db)
        return _db

    def get_client_with_custom_params(self, db_name_alias: str, **custom_params: Any) -> Any:
        return self._get_client(db_name_alias, **custom_params)

    def __iter__(self) -> Iterator:
        return iter(self.databases)

    def all(self) -> list[Database]:
        return [self[db_name_alias] for db_name_alias in self]
