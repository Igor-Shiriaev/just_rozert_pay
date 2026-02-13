import logging
from typing import Any, Callable, Dict, List, Optional, Union

from kombu import Exchange, Producer, Queue
from kombu.connection import Connection
from kombu.message import Message
from kombu.mixins import ConsumerMixin
from kombu.simple import SimpleBase

from ..events import Event
from ..utils import auto_close_old_connection

logger = logging.getLogger(__name__)


_OnPayload = Callable[[Union[Dict, Event]], None]
_OnBulkPayload = Callable[[List['Event']], None]
_OnError = Callable[[Exception, Message], None]
BodyType = Union[Dict, 'Event', List['Event']]


ACCEPTED_SERIALIZERS = ['json', 'dataclass', 'bulk-dataclass']


class ConsumerNoLogError(Exception):
    """ This error is not logged in consumer. You can use it, if you just
    want message to be retried silently.
    """


class Consumer(ConsumerMixin):
    """https://docs.celeryq.dev/projects/kombu/en/latest/userguide/consumers.html#consumer-mixin-classes
    """
    # NOTE: seems like it's not suitable for bulk processing (even though you see handle_bulk_payload here
    # as an argument). Seems like it's just for the case then message body is a list.
    # So it should have been named handle_list_payload or something like that instead.
    _producer_connection: Optional[Connection] = None
    prefetch_count: int
    fallback_queue: Optional[Queue]
    # accepted_serializer: List[str]

    def __init__(
        self,
        connection: Connection,
        queues: List[Queue],
        on_payload: _OnPayload,
        on_bulk_payload: _OnBulkPayload = None,
        on_error: _OnError = None,
        fallback_queue: Optional[Queue] = None,
        prefetch_count: int = 1,
        pass_message_to_handlers: bool = False,
        connect_max_retries: int = 3,
    ) -> None:
        self.connect_max_retries = connect_max_retries
        # self.accepted_serializer = []
        self.pass_message_to_handlers = pass_message_to_handlers
        self.prefetch_count = prefetch_count
        self.queues = queues
        self.connection = connection
        self.on_payload = on_payload
        self.handle_bulk_payload = on_bulk_payload
        self.on_error = on_error
        self.fallback_queue = fallback_queue

        self.init()

    def init(self) -> None:
        for queue in self.queues:
            self._validate_queue(queue)
            logger.info('queue validated', extra={'queue': queue})

        if self.fallback_queue:
            self._validate_queue(self.fallback_queue)
            self.fallback_queue.maybe_bind(self.producer_connection)
            self.fallback_queue.declare()
            logger.info('fallback queue declared', extra={'queue': self.fallback_queue})

    @staticmethod
    def _validate_queue(queue: Queue) -> None:  # type: ignore
        if isinstance(queue, Queue):
            if queue.bindings:
                return None
            if not isinstance(queue.exchange, Exchange):
                raise AssertionError(f'Unexpected exchange type {type(queue.exchange)}')
        else:
            raise AssertionError(f'Unexpected queue type {type(queue)}')

    def get_consumers(self, consumer_class: Any, channel: Any) -> List:     # type: ignore
        """Required by ConsumerMixin."""
        consumer = consumer_class(
            queues=self.queues,
            callbacks=[self.handle_message],
            accept=ACCEPTED_SERIALIZERS
        )
        consumer.qos(prefetch_count=self.prefetch_count)
        return [consumer]

    @auto_close_old_connection
    def handle_message(
        self,
        body: BodyType,
        message: Message
    ) -> None:
        handler_args = (body,) if not self.pass_message_to_handlers else (body, message)

        try:
            if isinstance(body, (dict, Event)):
                self.on_payload(*handler_args)  # type: ignore
            elif isinstance(body, list):
                if self.handle_bulk_payload:
                    self.handle_bulk_payload(*handler_args)  # type: ignore
                else:
                    raise RuntimeError(
                        'handle_bulk_payload is not supported for this consumer', f'{body}'
                    )
            else:
                raise RuntimeError(f'unknown body type: {type(body)}, '
                                   f'{body}')
        except Exception as exc:
            self.handle_error(exc, body, message)
        else:
            message.ack()

    def handle_error(self, exc: Exception, body: BodyType, message: Message) -> None:
        """ IMPORTANT NOTE:

            If you want to override this method, be sure it is either acks message or dies.
            Otherwise main thread may be blocked forever because of unacked message.
        """
        if not isinstance(exc, ConsumerNoLogError):
            logger.exception('Consuming error in %s', self.__class__.__name__, extra={'body': body})  # NOQA: LOG004
        message.ack()

        if self.fallback_queue is not None:
            self._publish_to_fallback_queue(message)
        if self.on_error is not None:
            self.on_error(exc, message)

    def _publish_to_fallback_queue(self, message: Message) -> None:
        assert self.fallback_queue is not None  # mypy
        self.producer.publish(
            body=message.body,
            routing_key=self.fallback_queue.routing_key,
            headers=message.headers,
            exchange=self.fallback_queue.exchange,
            content_type=message.content_type,
            content_encoding=message.content_encoding,
            retry=True
        )
        logger.info('published message with delivery_tag=%s to fallback queue %s', message.delivery_tag, self.fallback_queue.name)

    def on_consume_end(self, connection: Connection, channel: Any) -> None:     # type: ignore
        if self._producer_connection is not None:
            self._producer_connection.close()
            self._producer_connection = None

    @property
    def producer(self) -> Producer:     # type: ignore
        return Producer(self.producer_connection)

    @property
    def producer_connection(self) -> Connection:    # type: ignore
        if self._producer_connection is None:
            conn = self.connection.clone(transport_options={'confirm_publish': True})
            conn.ensure_connection(
                self.on_connection_error,
                self.connect_max_retries
            )
            self._producer_connection = conn
        return self._producer_connection

    def on_decode_error(self, message, exc) -> None:        # type: ignore
        if self.fallback_queue is not None:
            self._publish_to_fallback_queue(message)
        super().on_decode_error(message, exc)


def handle_fallback_queue(
    rabbitmq_url: str,
    fallback_queue: Optional[Union[Dict, Queue]],
    on_payload: _OnPayload,
    heartbeat: int = 4,
    stop_on_error: bool = True,
) -> None:
    with Connection(rabbitmq_url, heartbeat=heartbeat) as connection:
        queue = connection.SimpleQueue(fallback_queue)
        while True:
            try:
                message = queue.get(block=False)
                try:
                    on_payload(message.payload)
                except Exception as exc:
                    message.reject(requeue=True)
                    if not isinstance(exc, ConsumerNoLogError):
                        logger.exception('Exception in handle_fallback_queue')
                    if stop_on_error:
                        break
                    else:
                        continue
                else:
                    message.ack()
            except SimpleBase.Empty:
                break


def handle_fallback_queue_by_batches(
    *,
    rabbitmq_url: str,
    fallback_queue: Optional[Union[Dict, Queue]],
    on_bulk_payload: _OnBulkPayload,
    heartbeat: int = 4,
    batch_size: int = 1000,
) -> None:
    """NOTE: can be used for any queue, not only fallback queues.
    It's called this way because:
    - it does not support fallback queue in case there was an error
      while processing the batch (all messages in the batch will be requeued);
    - it's intended to be used for fallback queues - usually small and we need
      to process them until they are empty (e.g. cronjob every 10 minutes).
    """
    messages_batch: list[Message] = []

    def process_batch() -> bool:
        """Returns True if a batch was proccessed successful, False otherwise."""

        try:
            on_bulk_payload([message.payload for message in messages_batch])
        except Exception:
            for message in messages_batch:
                message.reject(requeue=True)
            logger.exception('Exception in handle_fallback_queue_by_batches')
            return False
        else:
            messages_batch[-1].ack(multiple=True)
            return True

    with Connection(rabbitmq_url, heartbeat=heartbeat) as connection:
        queue = connection.SimpleQueue(fallback_queue)

        while True:
            try:
                message = queue.get(block=False)

                try:
                    message.payload     # Try to decode the message
                except Exception as e:
                    logger.warning(
                        'Failed to decode message',
                        extra={'delivery_tag': message.delivery_tag, 'error': e},
                    )
                    message.reject(requeue=True)
                    continue

                messages_batch.append(message)
                if len(messages_batch) == batch_size:
                    if process_batch():
                        messages_batch = []
                    else:
                        return
            except SimpleBase.Empty:
                break
        if messages_batch:
            process_batch()


def handle_queue_batched(
    *,
    rabbitmq_url: str,
    queue: Queue,
    on_bulk_payload: _OnBulkPayload,
    heartbeat: int = 60,
    batch_size: int = 1000,
    max_batches_to_process: Optional[int] = None,
    fallback_queue: Queue | None = None,
    prefetch_count: int = 1000,
    batch_timeout_seconds: float = 15.0,
) -> int:
    """Unified batch processing function using basic.consume for efficiency.
    If everything will be ok in production - drop `handle_batch_from_queue` and `handle_fallback_queue_by_batches`
    functions usages in favor of this one.

    Args:
        max_batches_to_process: Maximum number of batches to process before returning.
        batch_timeout_seconds: Maximum time to spend collecting messages for a batch before processing it.
            This prevents waiting forever for batch_size when message rate is low.
        If fallback_queue is provided, messages that fail processing will be sent there.
        Otherwise, failed messages will be requeued.

    Returns:
        Number of messages processed.
    """
    import time
    from kombu import Consumer

    if prefetch_count < batch_size:
        raise ValueError(
            'Prefetch count must not be less than batch size '
            'since batch will never become full since RMQ will stop '
            'pushing messages to consumer due to prefetch_count unacked messages'
        )

    messages_batch: list[Message] = []
    total_processed = 0
    batches_processed = 0
    should_stop = False
    batch_start_time = None

    def publish_to_fallback_queue(message: Message) -> None:
        """Publish a single message to the fallback queue."""
        producer.publish(  # type: ignore
            body=message.body,
            routing_key=fallback_queue.routing_key,  # type: ignore
            headers=message.headers,
            exchange=fallback_queue.exchange,  # type: ignore
            content_type=message.content_type,
            content_encoding=message.content_encoding,
            retry=True
        )

    def process_batch() -> bool:
        """Returns True if a batch was processed successfully, False otherwise."""
        nonlocal total_processed, batches_processed

        try:
            on_bulk_payload([message.payload for message in messages_batch])
        except Exception:
            logger.exception('Exception in handle_queue_batched during messages batch processing')
            if fallback_queue is not None:
                # Send all messages in batch to fallback queue
                for message in messages_batch:
                    publish_to_fallback_queue(message)
                log_extra = {'fallback_queue': fallback_queue, 'batch_size': len(messages_batch)}
                logger.info(f'Published messages batch to fallback queue due to processing error', extra=log_extra)
                # Ack the messages since we've moved them to fallback queue
                messages_batch[-1].ack(multiple=True)
                logger.info('Acknowledged messages batch after publishing to fallback queue', extra=log_extra)
            else:
                # No fallback queue - requeue messages
                for message in messages_batch:
                    message.reject(requeue=True)
                logger.info('Rejected messages batch and requeued due to processing error', extra={'batch_size': len(messages_batch)})
            batches_processed += 1
            return False
        else:
            messages_batch[-1].ack(multiple=True)
            total_processed += len(messages_batch)
            batches_processed += 1
            logger.info('Processed and acknowledged messages batch', extra={'batch_size': len(messages_batch)})
            return True

    def on_message(body: Any, message: Message) -> None:
        """Callback for each received message."""
        nonlocal should_stop, batch_start_time

        try:
            # Try to decode the message
            message.payload
        except Exception as e:
            logger.warning(
                'Failed to decode message',
                extra={'delivery_tag': message.delivery_tag, 'error': e},
            )
            if fallback_queue is not None:
                publish_to_fallback_queue(message)
                logger.info('Published undecodable message to fallback queue', 
                           extra={'delivery_tag': message.delivery_tag, 'fallback_queue': fallback_queue})
                message.ack()
            else:
                message.reject(requeue=True)
                logger.info('Rejected and requeued undecodable message', 
                           extra={'delivery_tag': message.delivery_tag})
            return

        # Start timing when we get the first message of a new batch
        if not messages_batch:
            batch_start_time = time.monotonic()

        messages_batch.append(message)

        # Process batch when it reaches batch_size or timeout
        should_process = (
            len(messages_batch) >= batch_size or
            (batch_start_time and time.monotonic() - batch_start_time >= batch_timeout_seconds)
        )
        if should_process:
            process_batch()
            messages_batch.clear()
            batch_start_time = None
            if max_batches_to_process is not None and batches_processed >= max_batches_to_process:
                should_stop = True

    with Connection(rabbitmq_url, heartbeat=heartbeat) as connection:
        producer: Producer | None = None
        if fallback_queue is not None:
            producer = Producer(connection)

        with Consumer(connection, queues=[queue], callbacks=[on_message], accept=ACCEPTED_SERIALIZERS, prefetch_count=prefetch_count) as consumer:
            # Consume messages until we should stop or no more messages
            while not should_stop:
                try:
                    # If no messages for 5s, queue is empty, exit the loop, close consumer+connection
                    # NOTE: too small timeout here (for example 0.1s) can lead to situation, when
                    # RMQ was not yet able to push new 'prefetch_count' messages to the connection, so
                    # our code will prematurely exit thinking that queue is empty.
                    # If queue is not empty and one `prefetch_count` messages (in our case 1000) can't be pushed
                    # in 5s it means that either each message is huge (there is a possibility
                    # to control prefetch_size instead of prefetch_count) or network is too slow.
                    # We suppose it should not happen in our installation. 5s is a safe choice.
                    connection.drain_events(timeout=5.0)
                except Exception:
                    # Timeout means no messages available - exit immediately
                    break

        # Process any remaining messages in batch
        if messages_batch:
            process_batch()

        return total_processed


def run_consumer(
    rabbitmq_url: str,
    queues: List[Union[Dict, Queue]],
    on_payload: _OnPayload,
    on_error: _OnError = None,
    fallback_queue: Optional[Union[Dict, Queue]] = None,
    heartbeat: int = 4,
    prefetch_count: int = 1,
) -> None:
    with Connection(rabbitmq_url, heartbeat=heartbeat) as connection:
        consumer = Consumer(
            connection=connection,
            queues=queues,
            prefetch_count=prefetch_count,
            on_payload=on_payload,
            on_error=on_error,
            fallback_queue=fallback_queue
        )
        logger.info('Consumer is ready')
        consumer.run()
