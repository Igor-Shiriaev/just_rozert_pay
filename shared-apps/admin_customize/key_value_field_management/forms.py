from typing import TYPE_CHECKING, Any, Dict, List, Optional

from django import forms

from admin_customize.formsets import BaseFormSet

if TYPE_CHECKING:
    from django.db.models import Model


class KeyValueCompatibleForm(forms.Form):
    EMPTY_OPTION = ['', '---------']
    is_complex: bool

    def __init__(self, *args: Any, instance: Optional['Model'] = None, **kwargs: Any) -> None:
        self.instance = instance
        super().__init__(*args, **kwargs)

    @property
    def key_value(self) -> Optional[str]:
        if 'p_key' in self.cleaned_data and 's_key' in self.cleaned_data:
            return f'{self.cleaned_data["p_key"]}_{self.cleaned_data["s_key"]}'
        else:
            return self.cleaned_data.get('key')


class KeyValueForm(KeyValueCompatibleForm):
    is_complex = False

    key: forms.Field
    value: forms.Field


class ComplexKeyValueForm(KeyValueCompatibleForm):
    is_complex = True
    keys_separator = '_'

    p_key: forms.Field
    s_key: forms.Field
    value: forms.Field

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # type: ignore
        initial_value = kwargs.pop('initial', None)
        if initial_value:
            if 'key' in initial_value:
                key_value = initial_value['key']
                p_key_initial, s_key_initial = key_value.split(self.keys_separator, maxsplit=1)
            else:
                p_key_initial = initial_value['p_key']
                s_key_initial = initial_value['s_key']
            initial_value = {
                'p_key': p_key_initial,
                's_key': s_key_initial,
                'value': initial_value['value'],
            }
        super().__init__(*args, **kwargs, initial=initial_value)
        if self.fields['p_key'].choices:
            for choice in self.fields['p_key'].choices:
                if self.keys_separator in choice[0]:
                    raise ValueError(f'Value {choice[0]} has separator {self.keys_separator}')


class KeyValueFormset(BaseFormSet):
    UNIQUE_FIELD = 'key_value'

    forms: List[KeyValueCompatibleForm]

    def __init__(self, *args: Any, instance: Optional['Model'] = None, **kwargs: Any) -> None:  # type: ignore
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.can_delete = True

    def on_not_unique_form_found(self, form: 'KeyValueCompatibleForm', should_be_unique_value: Any) -> None:  # type: ignore
        if form.is_complex:
            form.add_error('p_key', f'Value {should_be_unique_value} ' f'should be unique')
            form.add_error('s_key', f'Value {should_be_unique_value} ' f'should be unique')
        else:
            form.add_error('key', 'Value of this field should be unique')

    def get_data_to_write(self) -> Dict:
        data_to_write = {}
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                data_to_write.update({form.key_value: form.cleaned_data['value']})
        return data_to_write
