from typing import Any, Dict, List

from django import forms


class BaseFormSet(forms.BaseFormSet):
    DELETE_FIELD = 'DELETE'  # Use can_delete in formset_factory if you want deletable formsets
    UNIQUE_FIELD: str

    def clean(self) -> None:
        if any(self.errors):
            return

        values_pretending_to_be_unique = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):  # type: ignore
                continue
            should_be_unique_value = form.cleaned_data.get(self.UNIQUE_FIELD)
            if should_be_unique_value is not None and should_be_unique_value in values_pretending_to_be_unique:
                self.on_not_unique_form_found(form, should_be_unique_value)
            values_pretending_to_be_unique.append(should_be_unique_value)

    def on_not_unique_form_found(self, form: forms.BaseForm, should_be_unique_value: Any) -> None:  # type: ignore
        form.add_error(self.UNIQUE_FIELD, 'Value of this field should be unique')

    def get_cleaned_data(self) -> List[Dict]:
        return [
            form_data
            for form in self.forms
            if (form_data := form.cleaned_data) and not form_data.get(self.DELETE_FIELD)
        ]
