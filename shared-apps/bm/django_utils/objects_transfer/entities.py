import abc
from typing import Any, Callable, ClassVar, Generic, Type, TypeVar

from django.db.models import Model
from pydantic import BaseModel

T = TypeVar('T', bound=Model)
PT = TypeVar('PT', bound=BaseModel)


class BaseDataTransferEntity(BaseModel, Generic[T], abc.ABC):
    pre_calls: ClassVar[list[Callable[..., None]]] = []
    post_calls: ClassVar[list[Callable[[Any], None]]] = []

    @classmethod
    @abc.abstractmethod
    def from_model_obj(cls, obj: T) -> 'BaseDataTransferEntity':
        """Create object from model instance."""
        pass

    def export_obj(self) -> str:
        """Compose JSON string from object."""
        return self.json(exclude_unset=True, exclude_none=True)

    @abc.abstractmethod
    def import_obj(self) -> T:
        """Create objects from attributes."""
        pass

    @staticmethod
    def _construct_obj(model: Type[PT], obj: Model, **additional_fields: Any) -> PT:
        if not isinstance(obj, Model):
            raise ValueError(f'Object {obj} is not instance of Model')
        if not issubclass(model, BaseModel):
            raise ValueError(f'Model {model} is not instance of BaseModel')
        fields = list(model.__fields__)
        data = {field: getattr(obj, field) for field in fields}
        return model(**{**data, **additional_fields})
