import csv
import datetime
import gzip
import io
import logging
import math
import re
import zoneinfo
from abc import ABC, abstractmethod
from typing import Any, Optional

import boto3
from clickhouse_driver import Client
from django.conf import settings
from django.db import connections  # type: ignore
from psycopg2.extensions import AsIs

logger = logging.getLogger(__name__)


class PGTableArchivatorById(ABC):
    """Constraints:
    1 - there is an integer 'id' column in the table, which is unique and indexed;
    2 - there is a datetime column in the table.

    `clickhouse_table_base_name` arg is called base name because env postfix will be added to the
    full table name in ClickHouse.
    """

    def __init__(
        self,
        clickhouse_table_base_name: str,
        pg_table_name: str,
        pg_connection_name: str,
        pg_max_batch_size: int = 100_000,
        s3_max_batch_size: int = 1_000_000,
        strict_empty_batch_check: bool = True,
    ):
        self.s3_client = boto3.client(
            's3',
            region_name=settings.PG_ARCHIVE_S3_REGION,
            aws_access_key_id=settings.PG_ARCHIVE_S3_ACCESS_KEY,
            aws_secret_access_key=settings.PG_ARCHIVE_S3_SECRET_ACCESS_KEY,
        )
        self.ch_client = Client(
            host=settings.PG_ARCHIVE_CLICKHOUSE_HOST,
            port=settings.PG_ARCHIVE_CLICKHOUSE_PORT,
            user=settings.PG_ARCHIVE_CLICKHOUSE_USER,
            password=settings.PG_ARCHIVE_CLICKHOUSE_PASSWORD,
            send_receive_timeout=20,
            client_name=f'python-{clickhouse_table_base_name}-archive',
        )
        _validate_table_name(pg_table_name)
        self.pg_table_name = pg_table_name
        self.pg_connection_name = pg_connection_name
        self.clickhouse_table_base_name = clickhouse_table_base_name
        self.env = settings.ENV_NAMESPACE.replace('-', '_')
        self.PG_MAX_BATCH_SIZE = pg_max_batch_size
        self.S3_MAX_BATCH_SIZE = s3_max_batch_size
        self.S3_KEY_STATIC_PREFIX = f'pg_archive/{self.env}/{clickhouse_table_base_name}'
        self.strict_empty_batch_check = strict_empty_batch_check

    @abstractmethod
    def get_clickhouse_table_columns(self) -> str:
        ...

    @abstractmethod
    def get_clickhouse_table_partition_by(self) -> str:
        """Example: toYYYYMMDD(created_at)"""
        ...

    @abstractmethod
    def get_clickhouse_table_primary_key(self) -> str:
        """Example: (user_id, created_at)"""
        ...

    @abstractmethod
    def get_csv_fieldnames(self) -> list[str]:
        """Example: ['id', 'datetime', 'opening_balance_available', ...]"""
        ...

    @abstractmethod
    def decode_pg_row(self, pg_row: dict[str, Any]) -> tuple[int, datetime.datetime, dict] | None:
        """
        NOTE: pg_row is a dict representing a row from the PostgreSQL table with the columns
        names as keys.
        Returns None if the row should be skipped (not archived).
        Otherwise returns:
            - id: integer id of the row
            - datetime: datetime of the row
            - csv dict representing the row with all the fields from `get_csv_fieldnames`
        Example:
            (12345, datetime.datetime(2023, 10, 1, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo('UTC')),
            {'id': 12345, 'datetime': '2023-10-01T12:00:00+00:00', 'opening_balance_available': 100.0, ...})
        """
        ...

    def create_clickhouse_structures(self) -> None:

        # See https://clickhouse.com/docs/en/engines/table-engines/integrations/s3queue#introspection
        self.ch_client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS system.s3queue_log (
                hostname LowCardinality(String) COMMENT 'Hostname',
                event_date Date COMMENT 'Event date of writing this log row',
                event_time DateTime COMMENT 'Event time of writing this log row',
                database String COMMENT 'The name of a database where current S3Queue table lives.',
                table String COMMENT 'The name of S3Queue table.',
                uuid String COMMENT 'The UUID of S3Queue table',
                file_name String COMMENT 'File name of the processing file',
                rows_processed UInt64 COMMENT 'Number of processed rows',
                status Enum8('Processed' = 0, 'Failed' = 1) COMMENT 'Status of the processing file',
                processing_start_time Nullable(DateTime) COMMENT 'Time of the start of processing the file',
                processing_end_time Nullable(DateTime) COMMENT 'Time of the end of processing the file',
                exception String COMMENT 'Exception message if happened'
            )
            ENGINE = MergeTree
            PARTITION BY toYYYYMM(event_date)
            ORDER BY (event_date, event_time)
            SETTINGS index_granularity = 8192
        """
        )

        table_columns = self.get_clickhouse_table_columns()

        table_base_name = self.clickhouse_table_base_name
        self.ch_client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_base_name}_s3queue_{self.env} (
                {table_columns}
            )
            ENGINE = S3Queue(
                '{settings.PG_ARCHIVE_S3_ENDPOINT}/{self.S3_KEY_STATIC_PREFIX}/*/*/*.csv.gz',
                'CSVWithNames',
                'gzip'
            )
            SETTINGS
                mode = 'ordered',
                s3queue_enable_logging_to_s3queue_log = 1,
                s3queue_polling_min_timeout_ms = 300000,   -- 5 min
                s3queue_polling_max_timeout_ms = 600000,   -- 10 min
                after_processing = 'keep',                 -- because S3 is used as a backup as well
                loading_retries = 0,
                processing_threads_num = 1;
        """
        )

        self.ch_client.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_base_name}_{self.env} (
                {table_columns}
            )
            ENGINE = MergeTree
            PARTITION BY {self.get_clickhouse_table_partition_by()}
            PRIMARY KEY {self.get_clickhouse_table_primary_key()}
        """
        )

        self.ch_client.execute(
            f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {table_base_name}_s3consumer_{self.env} TO {table_base_name}_{self.env}
            AS SELECT * FROM {table_base_name}_s3queue_{self.env};
        """
        )

    def _get_s3_last_processed_id(self) -> Optional[int]:
        """Response example: {
            "IsTruncated": false,
            "Contents": [
                {
                    "Key": "your/directory/prefix/file1.txt",
                    "LastModified": "2020-01-01T00:00:00.000Z",
                    "ETag": "\"etag_value\"",
                    "Size": 123,
                    "StorageClass": "STANDARD"
                },
                ...
            ],
            "Name": "your-s3-bucket-name",
            "Prefix": "your/directory/prefix/something_<min_id>-<max_id>.csv",
            "MaxKeys": 1000,
            "CommonPrefixes": [],
            "KeyCount": 2
        }
        """

        file_names: list[str] = []
        continuation_token: Optional[str] = None

        while True:
            if continuation_token:
                response = self.s3_client.list_objects_v2(
                    Bucket=settings.PG_ARCHIVE_S3_BUCKET,
                    Prefix=self.S3_KEY_STATIC_PREFIX,
                    MaxKeys=1000,
                    ContinuationToken=continuation_token,
                )
            else:
                response = self.s3_client.list_objects_v2(
                    Bucket=settings.PG_ARCHIVE_S3_BUCKET,
                    Prefix=self.S3_KEY_STATIC_PREFIX,
                    MaxKeys=1000,
                )

            file_names.extend([obj['Key'] for obj in response.get('Contents', [])])

            # Check if there are more file_names to fetch
            if response.get('IsTruncated'):  # If true, there are more file_names to retrieve
                continuation_token = response['NextContinuationToken']
            else:
                break

        if file_names:
            max_batches_ids: list[int] = []
            for f in file_names:
                # File name format is "your/directory/prefix/..._ids_<min_id>_<max_id>.csv",
                fname_no_prefix_not_ext = f.split('/')[-1].replace('.csv.gz', '')
                max_id = int(fname_no_prefix_not_ext.split('_')[-1])
                max_batches_ids.append(max_id)
            return max(max_batches_ids)
        else:
            return None

    def archive(
        self, expected_min_id: int, to_id: Optional[int] = None, only_ddl: bool = False
    ) -> list[str]:
        """Always start from last processed id (based on S3 data). It will be validated against `expected_min_id`.
        If `to_id` is provided process until `to_id`, otherwise process until the end of the table.
        """

        self.create_clickhouse_structures()
        if only_ddl:
            return []

        # compute and validate starting point
        last_processed_id = self._get_s3_last_processed_id()
        if last_processed_id is None:
            min_id = self._get_min_pg_id()
            logger.info(f"No previous S3 files found, starting from {min_id=}")
            from_id = min_id
        else:
            from_id = last_processed_id + 1
        assert from_id == expected_min_id, f"{from_id=}, {expected_min_id=}"

        # compute ending point
        if to_id is not None:
            assert to_id > from_id, f"to small, {to_id=}, {from_id=}"
        else:
            to_id = self._get_max_pg_id()

        logger.info('Starting archiving from/to', extra={'from_id': from_id, 'to_id': to_id})

        new_s3_file_names: list[str] = []
        while True:
            max_allowed_to_id = from_id + self.S3_MAX_BATCH_SIZE
            to_id_effective = min(to_id, max_allowed_to_id)
            s3_file_name, last_processed_id = self.upload_batch_to_s3(
                from_id=from_id,
                to_id=to_id_effective,
            )
            logger.info('New S3 file is uploaded', extra={'s3_file_name': s3_file_name})
            new_s3_file_names.append(s3_file_name)

            if last_processed_id == to_id:
                break
            else:
                from_id = last_processed_id + 1

        return new_s3_file_names

    def upload_batch_to_s3(self, from_id: int, to_id: int) -> tuple[str, int]:
        wt_buffer = io.StringIO()
        csv_writer = csv.DictWriter(wt_buffer, fieldnames=self.get_csv_fieldnames())
        csv_writer.writeheader()

        s3_file_min_id: int = math.inf  # type: ignore  # will be updated in the first iteration
        s3_file_max_id: int = 0
        # datetime.max, so that it will be updated in the first iteration
        s3_file_min_datetime: datetime.datetime = datetime.datetime.max.replace(
            tzinfo=zoneinfo.ZoneInfo('UTC')
        )
        s3_file_batch_size = 0

        batch_min_id = from_id
        while batch_min_id < to_id:
            batch_max_id = min(batch_min_id + self.PG_MAX_BATCH_SIZE, to_id)

            with connections[self.pg_connection_name].cursor() as c:
                c.execute(
                    "SELECT * FROM %s where id >= %s and id <= %s order by id",
                    params=(AsIs(self.pg_table_name), batch_min_id, batch_max_id),
                )
                pg_rows_list = c.fetchall()
                col_names = [desc[0] for desc in c.description]
                logger.info(
                    'PG Batch fetched',
                    extra={
                        'batch_min_id': batch_min_id,
                        'batch_max_id': batch_max_id,
                        'batch_size': len(pg_rows_list),
                    },
                )
                if not pg_rows_list:
                    logger.error(
                        'Empty PG batch found. Manual check required',
                        extra={'batch_min_id': batch_min_id, 'batch_max_id': batch_max_id},
                    )
                    if self.strict_empty_batch_check:
                        raise ValueError('Empty PG batch found')
                    batch_min_id = batch_max_id + 1
                    continue
            for pg_row in pg_rows_list:
                pg_row_dict = dict(zip(col_names, pg_row))
                decoded_row = self.decode_pg_row(pg_row_dict)
                if decoded_row is None:
                    continue  # meaning we should skip this row
                row_id, row_datetime, csv_dict = decoded_row
                s3_file_min_id = min(s3_file_min_id, row_id)
                s3_file_max_id = max(s3_file_max_id, row_id)
                s3_file_min_datetime = min(s3_file_min_datetime, row_datetime)
                csv_writer.writerow(csv_dict)
                s3_file_batch_size += 1
            del pg_rows_list
            batch_min_id = batch_max_id + 1

        wt_buffer.seek(0)

        # NOTE: we use isoformat() in `now_prefix` (and isoformat for year and month prefixes as well) file name
        # because we use S3Queue engine in ClickHouse with mode='ordered',
        # see more here: https://clickhouse.com/docs/en/engines/table-engines/integrations/s3queue#mode
        # ISO8601 for datetime guarantees lexicographical order.
        # `s3_file_min_datetime_prefix` is for human readability of datetime represented by the file content.
        now_prefix = datetime.datetime.now().isoformat()
        now = datetime.datetime.now()
        year_prefix = now.strftime('%Y')
        month_prefix = now.strftime('%m')
        s3_file_min_datetime_prefix = s3_file_min_datetime.strftime('%Y-%m-%d')
        s3_file_name = f'{self.S3_KEY_STATIC_PREFIX}/{year_prefix}/{month_prefix}/at_{now_prefix}_for_{s3_file_min_datetime_prefix}_ids_{s3_file_min_id}_{s3_file_max_id}.csv.gz'
        logger.info(
            'S3 batches are ready',
            extra={'s3_file_name': s3_file_name, 'batch_size': s3_file_batch_size},
        )

        if not s3_file_batch_size:
            return s3_file_name, to_id

        gzip_buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=gzip_buffer, mode='wb') as gz_file:
            gz_file.write(wt_buffer.getvalue().encode('utf-8'))
        s3_gzip_data = gzip_buffer.getvalue()
        gzip_buffer.seek(0)

        logger.info(
            'gzipped s3 batch is ready',
            extra={
                's3_file_name': s3_file_name,
                'batch_size': s3_file_batch_size,
                'bytes_size MB': len(s3_gzip_data) / 1024 / 1024,
            },
        )
        self.s3_client.upload_fileobj(gzip_buffer, settings.PG_ARCHIVE_S3_BUCKET, s3_file_name)
        return s3_file_name, s3_file_max_id


    def _get_min_pg_id(self) -> int:
        with connections[self.pg_connection_name].cursor() as c:
            c.execute("SELECT min(id) FROM %s", params=(AsIs(self.pg_table_name),))
            return c.fetchone()[0]


    def _get_max_pg_id(self) -> int:
        with connections[self.pg_connection_name].cursor() as c:
            c.execute("SELECT max(id) FROM %s", params=(AsIs(self.pg_table_name),))
            return c.fetchone()[0]


def _validate_table_name(table_name: str) -> None:
    if not re.match(r'^[\w\d_]+$', table_name):
        raise ValueError(f'Invalid table name: {table_name}')
