from typing import Union
from kombu import Exchange, Queue, binding


ORIGINAL_EVENTS_EXCHANGE = Exchange('eventbus', type='topic')


def build_original_events_queue(name: str, routing_key: Union[str, list[str]]) -> Queue:
    if isinstance(routing_key, list):
        return Queue(
            name,
            bindings=[
                binding(
                    exchange=ORIGINAL_EVENTS_EXCHANGE,
                    routing_key=rk
                )
                for rk in routing_key
            ]
        )
    return Queue(name, exchange=ORIGINAL_EVENTS_EXCHANGE, routing_key=routing_key)
