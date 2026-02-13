import re
from typing import Final

from bm.clickhouse import ClickHouseRepo
from bm.entities.shared import CasinoActionArchived
from bm.utils import instance_as_data
from django.core.exceptions import ImproperlyConfigured


class CasinoActionsArchivedClickHouseRepo(ClickHouseRepo[CasinoActionArchived]):
    DB_NAME: Final = 'default'
    COLUMNS: Final = [
        'id',
        'user_id',
        'uuid',
        'transaction_foreign_id',
        'rollback_transaction_foreign_id',
        'round_id',
        'session_id',
        'player_uuid',
        'game_foreign_id',
        'action_type',
        'status',
        'currency',
        'currency_foreign',
        'casino_provider',
        'amount',
        'amount_foreign',
        'promo_amount',
        'freespin_quantity',
        'freespin_used_quantity',
        'freespin_public_reward_id',
        'freespin_promo_identifier',
        'is_last_freespin',
        'freespin_amount',
        'charges.wallet_id',
        'charges.amount',
        'created_at',
        'updated_at',
        'game_type',
    ]

    @classmethod
    def decode_record(cls, row: tuple) -> CasinoActionArchived:
        data = dict(zip(cls.COLUMNS, row))
        return CasinoActionArchived.parse_obj(data)

    @classmethod
    def encode_record(cls, record: CasinoActionArchived) -> dict:
        return instance_as_data(record)

    @classmethod
    def make_repo(
        cls, use_real_count: bool, env_name: str, host: str, port: int, user: str, password: str
    ) -> 'CasinoActionsArchivedClickHouseRepo':
        if not re.match(r'^[a-zA-Z0-9_-]+$', env_name):
            raise ImproperlyConfigured('Invalid env_name: "%s" provided.' % env_name)
        return cls(
            host=host,
            port=port,
            user=user,
            password=password,
            table_qualname=f'{cls.DB_NAME}.casino_actions_{env_name.replace("-", "_")}',
            decode_record=cls.decode_record,
            encode_record=cls.encode_record,
            columns=cls.COLUMNS,
            use_real_count=use_real_count,
        )
