from typing import TYPE_CHECKING, Any, Optional, Type

from admin_customize.admin import BaseModelAdmin
from admin_customize.forms import BasicAdminActionForm
from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.template.response import TemplateResponse

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.db.models import Model, QuerySet
    from django.http import HttpRequest


class HideColumnsForm(BasicAdminActionForm):
    visible_columns = None
    action = 'set_hidden_columns'

    def __init__(
        self,
        *args: Any,
        user: 'User',
        model: Type['Model'],
        all_columns: list[str],
        visible_columns: list[str],
        hidden_columns_extra_key: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._user = user
        self._model = model
        self._all_columns = all_columns
        self._hidden_columns_extra_key = hidden_columns_extra_key

        choices: list[tuple[str, str]] = []
        for column in all_columns:  # type: ignore[attr-defined]
            try:
                verbose_name = getattr(getattr(self, column), 'short_description')
            except AttributeError:
                try:
                    verbose_name = model._meta.get_field(column).verbose_name  # type: ignore[attr-defined]
                except FieldDoesNotExist:
                    verbose_name = column.replace('_', ' ')
            choices.append((column, verbose_name.upper()))

        self.fields[self._hidden_columns_extra_key] = forms.MultipleChoiceField(
            widget=forms.CheckboxSelectMultiple(),
            choices=choices,
            initial=visible_columns,
            label='Visible columns'
        )

    def process(self) -> None:
        columns_to_hide = set(self._all_columns) - set(self.cleaned_data[self._hidden_columns_extra_key])
        app_label = self._model._meta.app_label

        if self._hidden_columns_extra_key not in self._user.extra:
            self._user.extra[self._hidden_columns_extra_key] = {}
        if app_label not in self._user.extra[self._hidden_columns_extra_key]:
            self._user.extra[self._hidden_columns_extra_key][app_label] = {}

        app_label_dict = self._user.extra[self._hidden_columns_extra_key][app_label]
        if set(app_label_dict.get(self._model.__name__, [])) != columns_to_hide:
            app_label_dict[self._model.__name__] = list(columns_to_hide)
            self._user.save()


class CustomHiddenColumnsMixin(BaseModelAdmin):
    __hidden_columns_extra_key = 'hidden_admin_columns'

    changelist_actions = ['set_visible_columns']

    def set_visible_columns(
        self, request: 'HttpRequest', queryset: 'QuerySet'
    ) -> Optional[TemplateResponse]:
        form = HideColumnsForm(
            request,
            user=request.user,
            model=self.model,
            all_columns=self.list_display,
            visible_columns=self.get_list_display(request),
            hidden_columns_extra_key=self.__hidden_columns_extra_key,
        )
        if form.is_valid():
            form.process()
            return None
        context = form.make_context(
            model=self.model,
            queryset=queryset.none(),  # type: ignore[attr-defined]
        )
        return TemplateResponse(
            request,
            form.form_template,
            context,
        )

    def get_list_display(self, request: 'HttpRequest') -> list[str]:
        list_display = super().get_list_display(request)

        try:
            hidden_columns = request.user.extra[
                self.__hidden_columns_extra_key
            ][self.model._meta.app_label][self.model.__name__]
        except KeyError:
            return list_display

        return [column for column in list_display if column not in hidden_columns]
