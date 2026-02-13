import re
from typing import Final

from bm.utils import instance_as_data
from bm.clickhouse import ClickHouseRepo
from bm.entities.shared import WalletTransactionArchived


class WalletTransactionArchivedClickHouseRepo(ClickHouseRepo[WalletTransactionArchived]):
    DB_NAME: Final = 'default'
    COLUMNS: Final = ['id', 'datetime', 'opening_balance_available', 'opening_balance_on_hold', 'balance_available', 'balance_on_hold', 'system_namespace', 'system', 'system_transaction_id', 'details', 'wallet_id']

    @classmethod
    def decode_record(cls, row: tuple) -> WalletTransactionArchived:
        data = dict(zip(cls.COLUMNS, row))
        return WalletTransactionArchived.parse_obj(data)

    @classmethod
    def encode_record(cls, record: WalletTransactionArchived) -> dict:
        return instance_as_data(record)

    @classmethod
    def make_repo(cls, use_real_count: bool, env_name: str, host: str, port: int, user: str, password: str) -> 'WalletTransactionArchivedClickHouseRepo':
        assert re.match(r'^[a-zA-Z0-9_-]+$', env_name), f'Invalid env_name: {env_name}'
        return cls(
            host=host,
            port=port,
            user=user,
            password=password,
            table_qualname=f'{cls.DB_NAME}.wallet_transactions_{env_name.replace("-", "_")}',
            decode_record=cls.decode_record,
            encode_record=cls.encode_record,
            columns=cls.COLUMNS,
            use_real_count=use_real_count,
        )
