import dataclasses
from typing import Any, Optional, Union


@dataclasses.dataclass
class AdminFieldset:
    name: Optional[str] = None
    fields: list[Union[str, tuple[str, ...]]] = dataclasses.field(default_factory=list)

    wide: bool = False
    collapse: bool = False
    description: Optional[str] = None
    additional_classes: Optional[list[str]] = None

    def as_django_fieldset(self) -> tuple[Optional[str], dict]:
        classes = []
        if self.wide:
            classes.append('wide')
        if self.collapse:
            classes.append('collapse')
        if self.additional_classes:
            classes.extend(self.additional_classes)
        fieldset_data: dict[str, Any] = {
            'fields': self.fields,
            'classes': classes,
        }
        if self.description:
            fieldset_data['description'] = self.description

        return (
            self.name,
            fieldset_data,
        )
