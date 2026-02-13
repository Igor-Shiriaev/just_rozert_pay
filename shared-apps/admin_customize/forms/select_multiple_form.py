from typing import Any, List, Tuple, Union

from django import forms


class SelectMultipleForm(forms.Form):
    CHOICES: List[Tuple[Union[str, int], str]]
    FIELD_NAME: str

    ALL_MARKER = '__all__'

    form_template = 'admin/custom_intermediate_choice_form.html'

    choices = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple(),
    )

    def __init__(self, *args: Any, preselected: List[str], **kwargs: Any) -> None:  # type: ignore
        super().__init__(*args, **kwargs)
        self.fields['choices'].choices = [(self.ALL_MARKER, 'All'), *self.CHOICES]
        self.fields['choices'].label = self.FIELD_NAME
        self.fields['choices'].initial = preselected

    def get_selected_data(self) -> List[str]:
        return [c for c in self.cleaned_data['choices'] if c != self.ALL_MARKER]
