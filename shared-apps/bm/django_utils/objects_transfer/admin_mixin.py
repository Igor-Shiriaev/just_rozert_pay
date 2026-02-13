from typing import Any, ClassVar, Iterable, Type

from django import forms
from django.conf import settings
from django.db import transaction
from django.db.models import Model, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse

from .entities import BaseDataTransferEntity


class ImportFileForm(forms.Form):
    file = forms.FileField()

    def __init__(self, *args: Any, dataclass: Type[BaseDataTransferEntity], **kwargs: Any) -> None:
        self.dataclass = dataclass
        super().__init__(*args, **kwargs)

    def get_import_obj(self) -> BaseDataTransferEntity:
        import_data = self.cleaned_data['file'].read().decode('utf-8')
        import_dto = self.dataclass.parse_raw(import_data)
        return import_dto


class DataTransferMixin:
    data_transfer_entity: ClassVar[Type[BaseDataTransferEntity]]

    _import_action = 'import_obj'
    _export_action = 'export_obj'

    change_actions: Iterable[str] = [
        _export_action,
    ]

    changelist_actions: Iterable[str] = [
        _import_action,
    ]

    def get_change_actions(
        self, request: HttpRequest, object_id: Any, form_url: str
    ) -> Iterable[str]:
        actions = super().get_change_actions(request, object_id, form_url)  # type: ignore[misc]
        if self._export_action not in actions:
            actions.append(self._export_action)
        return actions

    def get_changelist_actions(self, *args: Any, **kwargs: Any) -> Iterable[str]:
        actions = super().get_changelist_actions(*args, **kwargs)  # type: ignore[misc]
        if self._import_action not in actions:
            actions.append(self._import_action)
        return actions

    def import_obj(self, request: HttpRequest, queryset: QuerySet) -> HttpResponse:
        form = ImportFileForm(
            request.POST or None, request.FILES or None, dataclass=self.data_transfer_entity
        )
        if form.is_valid():
            with transaction.atomic():
                import_dto = form.get_import_obj()
                for pre_call in self.data_transfer_entity.pre_calls:
                    pre_call()
                new_obj = import_dto.import_obj()
                for post_call in self.data_transfer_entity.post_calls:
                    post_call(new_obj)
            new_obj_url = self.reverse_admin_url(  # type: ignore[attr-defined]
                f'%s_%s_change' % (new_obj._meta.app_label, new_obj._meta.model_name),
                args=(new_obj.pk,),
            )
            return HttpResponseRedirect(new_obj_url)
        return TemplateResponse(
            request,
            'admin/simple_custom_intermediate_form.html',
            {
                'form': form,
                'opts': queryset.model._meta,
                'app_label': queryset.model._meta.app_label,
            },
        )

    def export_obj(self, request: HttpRequest, obj: Model) -> HttpResponse:
        export_obj = self.data_transfer_entity.from_model_obj(obj)

        obj_meta = obj._meta  # noqa

        env_namespace = getattr(settings, 'ENV_NAMESPACE', None)
        if env_namespace and env_namespace == '__default__':
            env_namespace = 'default'
        if env_namespace:
            file_name = f'{env_namespace}_{obj_meta.app_label}_{obj_meta.model_name}_{obj.pk}'
        else:
            file_name = f'{obj_meta.app_label}_{obj_meta.model_name}_{obj.pk}'

        response = HttpResponse(content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{file_name}.json"'
        response.write(export_obj.export_obj())

        return response
