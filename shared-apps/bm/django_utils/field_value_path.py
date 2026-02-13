from typing import Any, Callable, List, Optional, TypeVar, Union

from django.db.models import ForeignKey, JSONField, Model
from django.utils.encoding import force_str
from pydantic import BaseModel

T_MutatingData = TypeVar('T_MutatingData', bound=Any)


class FieldValuePath(BaseModel):
    """Can be used to get and optionally set values of fields in a model instance or dict.

    It supports nested fields, e.g. 'user.profile.name' and can apply mutators to the field value.
    """

    path_nodes: List[str]
    readonly: bool = False
    nullable: bool = True

    mutators: List[Callable[[T_MutatingData], T_MutatingData]] = []

    @classmethod
    def from_field_path(
        cls,
        field_path: str,
        *,
        nullable: bool = True,
        readonly: bool = False,
        mutators: List[Callable[[Any], Any]] = None,
    ) -> 'FieldValuePath':
        """Construct a FieldValuePath from a field path string (fields are separated by dots).

        :param field_path: A string representing a field path, e.g. 'user.profile.name'
        :param nullable: If False and the field is not exist, an exception will be raised.
        :param readonly: If True, the field cannot be set.
        :param mutators: A list callables that will be applied to the field value before it is returned.

        """
        field_path_nodes = field_path.split('.')
        return cls(
            path_nodes=field_path_nodes,
            nullable=nullable,
            readonly=readonly,
            mutators=mutators or [],
        )

    def __str__(self) -> str:
        return '.'.join(self.path_nodes)

    def __repr__(self) -> str:
        return f'<FieldValuePath: {self}>'

    def __add__(self, other: Union[str, 'FieldValuePath']) -> 'FieldValuePath':
        """
        Allows to create a new FieldValuePath by concatenating two FieldValuePaths or a FieldValuePath and a string.
        Example:
        >>> fvp = FieldValuePath.from_field_path('user.profile')
        >>> fvp + 'name'
        FieldValuePath: user.profile.name
        """
        if not isinstance(other, (str, FieldValuePath)):
            raise ValueError(f'Cannot concatenate FieldValuePath with {type(other)}')

        return FieldValuePath.from_field_path(
            f'{self}.{other}',
            nullable=self.nullable,
            readonly=self.readonly,
            mutators=self.mutators,
        )

    @property
    def base_field(self) -> str:
        return self.path_nodes[0]

    @property
    def intermediate_fields(self) -> List[str]:
        return self.path_nodes[1:-1]

    @property
    def final_field(self) -> str:
        return self.path_nodes[-1]

    @property
    def is_for_complex_field(self) -> bool:
        return len(self.path_nodes) > 1

    def get_value(self, instance: Any) -> Optional[Any]:
        """Get the value of the field in the instance. Also applies mutators if any."""
        if not self.is_for_complex_field:
            value = self._get_field_value(instance, self.base_field)
            value = self._apply_mutators(value)
            return value
        temp_result = self._get_field_value(instance, self.base_field)
        for f in self.intermediate_fields:
            temp_result = self._get_field_value(temp_result, f)
        value = self._get_field_value(temp_result, self.final_field, last_element=True)
        value = self._apply_mutators(value)
        return value

    def _apply_mutators(self, value: Any) -> Any:
        """Apply mutators to the value."""
        for mutator in self.mutators:
            value = mutator(value)
        return value

    def _get_field_value(
        self, instance: Any, name: str, last_element: bool = False
    ) -> Optional[Any]:
        instance_type = type(instance)
        try:
            if instance is None and self.nullable:
                return None
            if instance_type is dict:
                if not self.nullable:
                    return instance[name]
                if not last_element:
                    return (instance or {}).get(name, {})
                return (instance or {}).get(name)
            else:
                return getattr(instance, name)
        except AttributeError:
            raise ValueError(
                '{} has no attribute {}. Check {}'.format(
                    force_str(instance),
                    name,
                    '.'.join(self.path_nodes),
                )
            )
        except KeyError:
            raise ValueError(
                '{} has no key {}. Check {}'.format(
                    force_str(instance),
                    name,
                    '.'.join(self.path_nodes),
                )
            )

    def set_value(self, instance: Any, value: Any) -> None:
        """Set the value of the field in the instance. Raises an exception if the field is read-only."""
        if self.readonly:
            raise ValueError('FieldValue is readonly. Setting value is prohibited')
        if not self.is_for_complex_field:
            return self._set_simple_field_value(instance, value)
        self._set_complex_field_value(instance, value)

    def _set_simple_field_value(self, instance: Any, value: Any) -> None:
        if isinstance(instance, dict):
            instance[self.base_field] = value
            return
        elif hasattr(instance, self.base_field):
            setattr(instance, self.base_field, value)
            return
        raise ValueError(
            '%s cannot be assigned. Check %s',
            force_str(type(instance)),
            '.'.join(self.path_nodes),
        )

    def _set_complex_field_value(self, instance: Any, value: Any) -> None:
        if isinstance(instance, Model):
            field = instance._meta.get_field(self.base_field)
            if isinstance(field, ForeignKey):
                raise ValueError(
                    'Assigning related models is not allowed. Check {}'.format(
                        '.'.join(self.path_nodes)
                    ),
                )
            if isinstance(field, JSONField):
                instance_value = getattr(instance, self.base_field, {})
                self._set_json_value(instance_value, value)
                setattr(instance, self.base_field, instance_value)
                return
        elif isinstance(instance, dict):
            self._set_dict_value(instance, value)
            return
        raise ValueError(
            '{} cannot be assigned. Check {}'.format(
                force_str(type(instance)),
                '.'.join(self.path_nodes),
            )
        )

    def _set_dict_value(self, instance: dict, value: Any) -> None:
        for key in [self.base_field, *self.intermediate_fields]:
            if key not in instance:
                instance[key] = {}
            instance = instance[key]
        instance[self.final_field] = value

    def _set_json_value(self, instance: dict, value: Any) -> None:
        for key in self.intermediate_fields:
            if key not in instance:
                instance[key] = {}
            instance = instance[key]
        instance[self.final_field] = value
