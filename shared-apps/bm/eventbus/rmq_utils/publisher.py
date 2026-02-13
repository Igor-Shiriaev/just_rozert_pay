import logging
from typing import Any, Optional, List, Dict

from kombu import Exchange, Producer
from kombu.connection import Connection
from kombu.pools import producers, ProducerPool

from bm.eventbus.events import Event

from . import ORIGINAL_EVENTS_EXCHANGE


logger = logging.getLogger(__name__)


class Publisher:

    MAX_RETRIES = 3
    CONNECTION_SOCK_TIMEOUT_SECONDS = 5
    PRODICER_ACQUIRE_TIMEOUT_SECONDS = 5
    POOL_SIZE = 10

    def __init__(
        self,
        rabbitmq_url: str,
        exchange: Exchange,
        max_retries_num: int = MAX_RETRIES,
        connection_sock_timeout_seconds: float = CONNECTION_SOCK_TIMEOUT_SECONDS,
        producer_acquire_timeout_seconds: float = PRODICER_ACQUIRE_TIMEOUT_SECONDS,
        pool_size: int = POOL_SIZE,
    ) -> None:
        self.connection_sock_timeout_seconds = connection_sock_timeout_seconds
        self.max_retries_num = max_retries_num
        self.rabbitmq_url = rabbitmq_url

        self._exchange = exchange
        self._exchange_declared = False
        self._producer_pool: Optional[ProducerPool] = None
        self.producer_acquire_timeout_seconds = producer_acquire_timeout_seconds
        self.pool_size = pool_size

    @classmethod
    def make_original_events_publisher(
        cls,
        rabbitmq_url: str,
        max_retries_num: int = MAX_RETRIES,
        connection_sock_timeout_seconds: float = CONNECTION_SOCK_TIMEOUT_SECONDS,
        producer_acquire_timeout_seconds: float = PRODICER_ACQUIRE_TIMEOUT_SECONDS,
        pool_size: int = POOL_SIZE,
    ) -> 'Publisher':
        """Exchange could not be passed from outside, ORIGINAL_EVENTS_EXCHANGE is always used.
        It's single entry point for all original events.
        """
        return cls(
            rabbitmq_url=rabbitmq_url,
            exchange=ORIGINAL_EVENTS_EXCHANGE,
            max_retries_num=max_retries_num,
            connection_sock_timeout_seconds=connection_sock_timeout_seconds,
            producer_acquire_timeout_seconds=producer_acquire_timeout_seconds,
            pool_size=pool_size,
        )

    @classmethod
    def make_fallback_events_publisher(
        cls,
        rabbitmq_url: str,
        exchange: Exchange,
        max_retries_num: int = MAX_RETRIES,
        connection_sock_timeout_seconds: float = CONNECTION_SOCK_TIMEOUT_SECONDS,
        producer_acquire_timeout_seconds: float = PRODICER_ACQUIRE_TIMEOUT_SECONDS,
        pool_size: int = POOL_SIZE,
    ) -> 'Publisher':
        """This method is implemented just to contrast the difference with `make_original_events_publisher` above.
        Exchange for fallback producer could be specified manually since for now we are not interested in the
        common entry point for all failed events.
        """
        return cls(
            rabbitmq_url=rabbitmq_url,
            exchange=exchange,
            max_retries_num=max_retries_num,
            connection_sock_timeout_seconds=connection_sock_timeout_seconds,
            producer_acquire_timeout_seconds=producer_acquire_timeout_seconds,
            pool_size=pool_size,
        )

    @property
    def producer_pool(self) -> ProducerPool:    # type: ignore
        if self._producer_pool is None or self._producer_pool._closed:
            # Celery works bad with kombu default pool implementation.
            # So in celery each task will create new pool. Outside celery
            # everything seems to work correctly.
            self._producer_pool = producers.create(
                Connection(self.rabbitmq_url), self.pool_size
            )
            logger.info('new producer pool created for publisher')
        return self._producer_pool

    @property
    def exchange(self) -> Exchange:         # type: ignore
        if not self._exchange_declared:
            # Sometimes there some inconsistence happen in Rabbit, and he begins to stop routing messages to
            # correct exchange. In such case we need to redeclare exchange. So here we do it on each publisher
            # initialization.
            self.declare_exchange()
            self._exchange_declared = True
        return self._exchange

    def publish_event(
        self,
        event: Event,
        headers: Optional[Dict] = None,
    ) -> None:
        self.publish_payload(
            payload=event,
            routing_key=event.routing_key,
            serializer='dataclass',
            headers=headers,
        )

    def publish_event_bulk(self, bulk: List[Event], routing_key: Optional[str]) -> None:
        self.publish_payload(
            payload=bulk,
            routing_key=routing_key,
            serializer='bulk-dataclass',
        )

    def declare_exchange(self) -> None:
        with self.producer_pool.acquire(
            block=True, timeout=self.producer_acquire_timeout_seconds
        ) as producer:
            assert isinstance(producer, Producer)
            bound_exchange = self._exchange.bind(producer.channel)
            bound_exchange.declare()

    def publish_payload(            # type: ignore
        self,
        payload: Any,
        routing_key: Optional[str],
        serializer: str = 'json',
        **kwargs: Any
    ) -> None:
        with self.producer_pool.acquire(
            block=True,
            timeout=self.producer_acquire_timeout_seconds,

        ) as producer:
            assert isinstance(producer, Producer)

            # TODO: retry policy
            # retry_policy={
            #     'interval_start': 0, # First retry immediately,
            #     'interval_step': 2,  # then increase by 2s for every retry.
            #     'interval_max': 30,  # but don't exceed 30s between retries.
            #     'max_retries': 30,   # give up after 30 tries.
            # }
            producer.publish(
                payload,
                exchange=self.exchange,
                routing_key=routing_key,
                retry=True,
                retry_policy={'max_retries': self.max_retries_num},
                serializer=serializer,
                **kwargs
            )
