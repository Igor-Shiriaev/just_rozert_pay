import json

from typing import Any, Tuple, List, Union

from decimal import Decimal

from django.db.models import JSONField, BooleanField
from django.db.models.expressions import Func, Subquery
from django.db.models.lookups import Lookup

from bm.serializers import serialize_decimal


class JSONFieldDeleteKeyFunc(Func):
    @property
    def template(self) -> str:  # type: ignore
        parts = ['%(field)s']
        for key in self.keys:
            parts += ['-', f'\'{key}\'']
        return ' '.join(parts)

    def __init__(self, field: str, *, keys: List[str]):
        self.keys = keys
        super().__init__(field)


def _prepare_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, Decimal):
        return f'"{serialize_decimal(value)}"'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, (list, dict)):
        return json.dumps(value)
    elif isinstance(value, dict):
        return json.dumps(value)
    else:
        raise TypeError(f'Incompatible type of value: {type(value)}')


class JSONFieldSetValueFunc(Func):
    function = 'jsonb_set'
    template = '%(function)s(%(field)s, \'{"%(key)s"}\',\'%(value)s\', %(create_missing)s)'
    arity = 1

    def __init__(
        self, field: str, *, key: str, value: Any, create_missing: bool = False, **extra: Any
    ) -> None:
        super().__init__(
            field,
            key=key,
            value=_prepare_value(value),
            create_missing='true' if create_missing else 'false',
            **extra,
        )


class JSONBNestedFieldUpdateFunc(Func):
    function = 'jsonb_set'
    template = '%(function)s(%(field)s, \'%(path)s\',\'%(value)s\', %(create_missing)s)'
    arity = 1

    def __init__(
        self,
        field: str,
        *,
        path: list[str],
        value: Any,
        create_missing: bool = False,
        **extra: Any,
    ) -> None:
        super().__init__(
            field,
            path='{' + ','.join(path) + '}',
            value=_prepare_value(value),
            create_missing='true' if create_missing else 'false',
            **extra,
        )


class SubqueryJsonAgg(Subquery):
    template = '(SELECT to_jsonb(array_agg(row_to_json(_subquery))) FROM (%(subquery)s) _subquery)'

    output_field = JSONField(default=list)


@JSONField.register_lookup
class JSONFieldInnerArrayContainsFunc(Lookup):
    lookup_name = 'array_contains'

    def as_sql(self, compiler: Any, connection: Any) -> Tuple[str, Tuple[Union[int, str], ...]]:
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        # Ensure the RHS is properly cast to jsonb
        if isinstance(rhs_params[0], (dict, list)):
            # For Django 4.2+, we need to explicitly handle dict/list values
            rhs = '%s::jsonb'
            rhs_params = list(map(json.dumps, rhs_params))
        else:
            rhs = '%s'
        params = (*lhs_params, *rhs_params)
        return (
            'EXISTS(SELECT value from jsonb_array_elements(%s) where value::jsonb <@ %s::jsonb limit 1)'
            % (lhs, rhs),
            params,
        )


class JsonHasKey(Func):
    function = '?'
    template = '%(expressions)s %(function)s %(key)s'

    def __init__(self, expression: str, key: str) -> None:
        super().__init__(expression, output_field=BooleanField())
        self.key = key

    def as_sql(self, compiler: Any, connection: Any, **extra_context: Any) -> Any:
        extra_context['key'] = f"'{self.key}'"
        return super().as_sql(compiler, connection, **extra_context)
