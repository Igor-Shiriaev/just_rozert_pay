import codecs
import json
from typing import Dict, List, Union, Any

import pydantic
from kombu.serialization import registry

from bm.utils import instance_as_data, json_dumps, json_loads
from bm.exceptions import ValidationError

from .events import Event, EVENT_PAYLOAD_BY_EVENT_TYPE
from .constants import EventType


def serialize_event(event: 'Event') -> str:
    data = instance_as_data(event)
    return json_dumps(data)


def deserialize_event(value: str) -> 'Event':
    """
    {
        'event_type': 'DEPOSIT',
        'created_at': '2020-03-25T09:46:51.648011',
        'priority': 10,
        'payload': {...}
    }
    """
    data = json_loads(value)
    assert isinstance(data, dict), (data, type(data))
    return make_event_from_data(data)


def make_event_from_data(data: Dict) -> 'Event':
    try:
        event_type = EventType[data['event_type']]
        payload_class = EVENT_PAYLOAD_BY_EVENT_TYPE[event_type]
    except (KeyError, ValueError):
        raise ValidationError({'event_type': f'Unexpected event type for data {data}'})
    try:
        payload = payload_class(**data['payload'])  # type: ignore
        return Event(**{  # type: ignore
            **data,
            'payload': payload,
            'event_type': event_type
        })
    except pydantic.ValidationError as exc:
        error_data = {
            str(err['loc'][0]): err['msg'] for err in exc.errors()
        }
        error_data['event_data'] = data  # type: ignore
        raise ValidationError(error_data) from exc


def register_json() -> None:
    def _loads(obj: Union[str, bytes]) -> Any:          # type: ignore
        if isinstance(obj, bytes):
            obj = obj.decode('utf-8')
        return json.loads(obj)

    registry.register(
        name='json',
        encoder=json_dumps,
        decoder=_loads,
        content_type='application/json',
        content_encoding='utf-8'
    )


def serialize_event_bulk(bulk: List['Event']) -> bytes:
    out = json_dumps([instance_as_data(el) for el in bulk])
    return codecs.encode(out.encode('utf8'), encoding='zlib')


def deserialize_event_bulk(raw: Union[str, bytes]) -> List['Event']:
    if isinstance(raw, bytes):
        raw = codecs.decode(raw, encoding='zlib')

    data = json_loads(raw)
    return [make_event_from_data(item) for item in data]


def register_serializers() -> None:
    registry.unregister('json')
    register_json()
    registry.register(
        name='dataclass',
        encoder=serialize_event,
        decoder=deserialize_event,
        content_type='application/x-dataclass',
        content_encoding='utf-8'
    )
    registry.register(
        name='bulk-dataclass',
        encoder=serialize_event_bulk,
        decoder=deserialize_event_bulk,
        content_type='application/x-bulk-dataclass',
        content_encoding='utf-8',
    )

    registry.enable('application/json')
    registry.enable('application/x-dataclass')
    registry.enable('application/x-bulk-dataclass')

