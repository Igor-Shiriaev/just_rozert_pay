import logging
import time
from uuid import UUID
import re
from typing import Any, Optional, Callable, Generic, TypeVar, cast, Union


logger = logging.getLogger('clickhouse_repo')


class ClickHouseRepoError(Exception):
    pass


class ObjectDoesNotExist(ClickHouseRepoError):
    pass


class MultipleObjectsReturned(ClickHouseRepoError):
    pass


ClickHouseRecordType = TypeVar('ClickHouseRecordType')


class ClickHouseRepo(Generic[ClickHouseRecordType]):

    VALID_FILTER_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        table_qualname: str,
        columns: list[str],
        decode_record: Callable[[tuple], ClickHouseRecordType],
        encode_record: Callable[[ClickHouseRecordType], dict],
        use_real_count: bool = True,
        request_duration_seconds_warning_threshold: float = 5.0,
    ) -> None:
        """`decode_record` is responsible for parsing raw data read from ClickHouse into record type instance.
        `encode_record` is responsible for encoding record type instance into dict where keys set is set of
        table's (`table_qualname`) columns.
        `columns` is list of columns of `table_qualname` table.
        `use_real_count` controls whether to perform real COUNT or return fake 99999999 result.
        use_real_count=False can be convenient when there are very loose filters and result is only used
        in admin panel, so it's more important to have fast perfomance compared to exact COUNT result.
        """
        from clickhouse_driver import Client

        self.table_qualname = table_qualname
        self.decode_record = decode_record
        self.encode_record = encode_record
        self.columns = columns
        self._columns_set = set(columns)
        self.use_real_count = use_real_count
        self.request_duration_seconds_warning_threshold = request_duration_seconds_warning_threshold
        self.client = Client(
            host=host,
            port=port,
            user=user,
            password=password,
            send_receive_timeout=20,
            client_name='python-ClickHouseRepo'
        )

    def count(self, **filter_params: Any) -> int:
        if not self.use_real_count:
            return 99999999

        where_clause, query_params = self._build_where_clause(**filter_params)
        query = f'SELECT COUNT(*) FROM {self.table_qualname}'
        if where_clause:
            query += f' {where_clause}'

        t1 = time.monotonic()
        # result format is [(100, )]
        result = cast(list[tuple[int]], self.client.execute(query, query_params))
        self._maybe_alert_on_query_duration(
            duration=time.monotonic() - t1,
            log_extra={'_query': query, '_query_params': query_params},
        )

        return result[0][0]

    def filter(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
        **filter_params: Any,
    ) -> list[ClickHouseRecordType]:

        where_clause, query_params = self._build_where_clause(**filter_params)

        query = f'SELECT {", ".join(self.columns)} FROM {self.table_qualname}'
        if where_clause:
            query += f' {where_clause}'

        # NOTE: for some reason parametrized request like
        # "SELECT * FROM eventslog.events ORDER BY %(order_by)s DESC LIMIT 3", {'order_by': 'created_at'}
        # does not provide valid ordering, and no exceptions are rised.
        # As a temporary (permanent ?) measure just validate that order_by is one of the known columns
        # and compile ORDER BY clause on app's side.
        if order_by is not None:
            is_desc_sorting = order_by.startswith('-')
            order_by_column = order_by[1:] if is_desc_sorting else order_by
            if order_by_column not in self._columns_set:
                raise ValueError(f'unknown order_by column provided: "{order_by_column}".')
            query += f' ORDER BY {order_by_column}'
            if is_desc_sorting:
                query += ' DESC'

        if limit is not None:
            query += ' LIMIT %(limit_rows)s'
            query_params['limit_rows'] = limit

        if offset is not None:
            query += ' OFFSET %(offset)s'
            query_params['offset'] = offset

        result_raw = cast(list[tuple], self.execute_query(query, query_params))
        return [self.decode_record(r) for r in result_raw]

    def delete(self, **filter_params: Any) -> None:
        where_clause, query_params = self._build_where_clause(**filter_params)
        query = f'DELETE FROM {self.table_qualname}'
        if where_clause:
            query += f' {where_clause}'
        self.execute_query(query, query_params)

    @classmethod
    def _build_where_clause(cls, **filter_params: Any) -> tuple[Optional[str], dict[str, Any]]:
        """Examples:
            1.
            input: {'event_type': 'GGR_CHANGED', 'timestamp__gte': '2022-01-01'}
            output:
                'WHERE event_type=%(event_type)s AND timestamp >= %(timestamp__gte)s',
                {'event_type': 'GGR_CHANGED', 'timestamp__gte': '2022-01-01'}
            2.
            input: {}
            output: None, {}
        """
        # implement write method for batched consumer

        special_postfix_to_operator_map = {
            'gt': '>',
            'gte': '>=',
            'lt': '<',
            'lte': '<=',
            'in': 'IN',
        }

        special_postfix_to_function_map = {
            'startswith': 'startsWith',
        }

        filters: list[str] = []
        new_filter_params: dict = {}
        for filter_key, value in filter_params.items():

            if not re.match(cls.VALID_FILTER_KEY_PATTERN, filter_key):
                raise ValueError('forbidden symbols found in filter key (column name), only a-zA-Z0-9 are allowed')

            keys = filter_key.split('__')
            if len(keys) == 1:
                filters.append(f'`{filter_key}` = %({filter_key})s')

            else:
                # special case for between
                # Example: period__between=(from, to) --> period.1 >= from AND period.2 <= to
                if keys[-1] == 'between':
                    # WHERE
                    #     period.1 <= to
                    #     AND period.2 >= from
                    if not isinstance(value, (list, tuple)) or len(value) != 2:
                        raise ValueError('for between operator value must be a list or tuple of length 2')
                    filters.append(f'`{keys[0]}.1` >= %({filter_key}_from)s')
                    filters.append(f'`{keys[0]}.2` < %({filter_key}_to)s')
                    new_filter_params[f'{filter_key}_from'] = value[0]
                    new_filter_params[f'{filter_key}_to'] = value[1]
                else:
                    special_condition_function: Optional[str] = None

                    default_condition_operator: str = '='
                    special_condition_operator: Optional[str] = None

                    keys_without_operator: list[str]
                    if keys[-1] in special_postfix_to_operator_map:
                        special_condition_operator = special_postfix_to_operator_map[keys[-1]]
                        keys_without_operator = keys[:-1]

                    elif keys[-1] in special_postfix_to_function_map:
                        special_condition_function = special_postfix_to_function_map[keys[-1]]
                        keys_without_operator = keys[:-1]

                    else:
                        keys_without_operator = keys[:]

                    if not all(keys_without_operator):
                        raise ValueError(f'key {filter_key} is not allowed')

                    if len(keys_without_operator) == 1:
                        condition_field = f'`{keys_without_operator[0]}`'
                        condition_value = f'%({filter_key})s'

                    elif len(keys_without_operator) > 1:
                        if not isinstance(value, str):
                            raise ValueError('only str value allowed for nested fields')

                        json_path = '$.' + '.'.join(keys_without_operator[1:])
                        condition_field = f"JSON_VALUE(`{keys_without_operator[0]}`, '{json_path}')"
                        condition_value = f'%({filter_key})s'

                    else:
                        raise ValueError(f'key {filter_key} is not allowed')

                    if special_condition_function:
                        if not isinstance(value, str):
                            raise ValueError('only str value allowed for nested fields')

                        filters.append(
                            f'{special_condition_function}({condition_field}, {condition_value})'
                        )

                    else:
                        condition_operator = special_condition_operator or default_condition_operator
                        filters.append(
                            f'{condition_field} {condition_operator} {condition_value}'
                        )

        if new_filter_params:
            filter_params.update(new_filter_params)
        query_params = filter_params
        return ('WHERE ' + ' AND '.join(filters)) if filters else None, query_params

    def get(self, **filter_params: Any) -> ClickHouseRecordType:
        result = self.filter(**filter_params, limit=2)
        if not result:
            raise ObjectDoesNotExist
        if len(result) > 1:
            raise MultipleObjectsReturned
        return result[0]

    def insert_many(self, records: list[ClickHouseRecordType]) -> int:
        encoded_records: list[dict] = [self.encode_record(r) for r in records]

        for r in encoded_records:
            if set(r) != self._columns_set:
                logger.error(
                    'encoded ClickHouse record and table columns do not match',
                    extra={'_encoded_record': r, '_columns_set': self._columns_set}
                )
                raise ValueError('serialized ClickHouse row and table columns do not match')

        query = f'INSERT INTO {self.table_qualname} ({", ".join(self.columns)}) VALUES'
        query_params = encoded_records
        # result format is 100 for the batch size 100
        return cast(int, self.execute_query(query, query_params))

    def execute_query(self, query: str, query_params: Union[dict, list[dict]]) -> Any:
        """query_params: list[dict] is used in case of insert_many call, see
        https://clickhouse-driver.readthedocs.io/en/latest/quickstart.html#inserting-data
        """
        if isinstance(query_params, list):
            # In case of batch insert `query_params` can be huge + contain sensitive data,
            # do not log it.
            log_extra = {'_query': query, '_number_of_items': len(query_params)}
        else:
            log_extra = {'_query': query, '_query_params': query_params}

        logger.info('executing parametrized clickhouse request', extra=log_extra)
        t1 = time.monotonic()
        result = self.client.execute(query, query_params)
        self._maybe_alert_on_query_duration(
            duration=time.monotonic() - t1,
            log_extra=log_extra,
        )

        return result

    def get_distinct_user_uuids(
        self,
        limit: Optional[int] = None,
        **filter_params: Any,
    ) -> list[UUID]:
        where_clause, query_params = self._build_where_clause(**filter_params)

        query = f'SELECT DISTINCT user_uuid FROM {self.table_qualname}'
        if where_clause:
            query += f' {where_clause}'
        if limit is not None:
            query += ' LIMIT %(limit)s'
            query_params['limit'] = limit

        result = self.execute_query(query=query, query_params=query_params)
        return [r[0] for r in result]

    def _maybe_alert_on_query_duration(self, duration: float, log_extra: dict) -> None:
        threshold = self.request_duration_seconds_warning_threshold
        if duration <= threshold:
            return

        logger.error(
            'parametrized clickhouse request executed for more than threshold seconds',
            extra={
                **log_extra,
                '_request_duration_seconds': duration,
                'threshold': threshold,
            }
        )
