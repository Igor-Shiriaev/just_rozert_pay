from typing import Any, Callable, List, Optional, Type, Union

from admin_customize.admin.utils import log_change
from admin_customize.key_value_field_management.forms import (
    KeyValueCompatibleForm,
    KeyValueFormset
)
from django.contrib import messages
from django.db.models import Model
from django.forms import Media, formset_factory
from django.http import HttpRequest
from django.template import loader  # type: ignore
from django.template.response import TemplateResponse


class KeyValueAdminMixin:
    model: Type[Model]
    default_update_fields = ['updated_at']
    _custom_display_params: dict = {}

    @property
    def media(self) -> Media:
        media = super().media  # type: ignore
        media += Media(
            css={'all': ('css/preview_widget.css',)},
            js=['js/preview_widget.js'],
        )
        return media

    def process_action(
        self,
        request: HttpRequest,
        obj: Model,
        *,
        model_field_name: str,
        form_class: Type[KeyValueCompatibleForm],
        param_name: str = None,
        custom_update_fields: Optional[List[str]] = None,
        callback_on_save: Optional[Callable] = None,
        **kwargs: Any,
    ) -> Optional[TemplateResponse]:
        if not hasattr(obj, model_field_name):
            raise ValueError(f'{obj} has no field {model_field_name}')
        obj_field_value = getattr(obj, model_field_name) or {}
        if param_name is None:
            data_to_edit = obj_field_value
        else:
            data_to_edit = obj_field_value.get(param_name, {})
        initial_form_data = [{'key': k, 'value': v} for k, v in data_to_edit.items()]
        Formset: Type[KeyValueFormset] = formset_factory(
            formset=KeyValueFormset,
            form=form_class,
            extra=0,
        )
        if request.method != 'POST':
            formset = Formset(initial=initial_form_data, instance=obj, form_kwargs={'instance': obj}, **kwargs)
        else:
            formset = Formset(
                request.POST,
                initial=initial_form_data,
                instance=obj,
                form_kwargs={'instance': obj},
                **kwargs,
            )
            if formset.is_valid():
                data_to_write = formset.get_data_to_write()
                if param_name is None:
                    obj_field_value = data_to_write
                else:
                    obj_field_value.update({param_name: data_to_write})
                setattr(obj, model_field_name, obj_field_value)
                update_fields = custom_update_fields if custom_update_fields is not None else self.default_update_fields
                obj.save(update_fields=[model_field_name, *update_fields])
                if callback_on_save is not None:
                    callback_on_save()
                if param_name is None:
                    log_message = f'Changed {model_field_name}'
                else:
                    log_message = f'Changed {model_field_name} ' f'-> {param_name} field'
                self.message_user(request, log_message, level=messages.SUCCESS)  # type: ignore
                log_change(request.user.pk, obj, log_message)
                return None

        return TemplateResponse(
            request,
            'admin/simple_custom_intermediate_formset.html',
            {'opts': self.model._meta, 'formset': formset, 'obj': obj},
        )

    def render_field(
        self,
        obj: Model,
        *,
        model_field_name: str,
        key_field_name: str,
        value_field_name: str,
        param_name: str = None,
        safe_content: bool = False,
        use_links: bool = False,
        use_images: bool = False,
        image_height: int = 80,
        hide_header: bool = False,
        show_background_toggler: bool = False,
    ) -> Union[str, TemplateResponse]:
        obj_field = getattr(obj, model_field_name, {})
        if param_name is None:
            data_to_render = obj_field
        else:
            data_to_render = obj_field.get(param_name, {})
        if not data_to_render:
            return '-'
        t = loader.get_template('admin/includes/table_layout.html')
        headers = [key_field_name, value_field_name]
        return t.render(
            context={
                'headers': headers,
                'data_to_render': data_to_render,
                'use_links': use_links,
                'use_images': use_images,
                'safe_content': safe_content,
                'image_height': image_height,
                'hide_header': hide_header,
                'key_fields_count': 1,
                'show_background_toggler': show_background_toggler,
                'is_complex': False,
            },
        )

    def render_complex_field(
        self,
        obj: Model,
        *,
        model_field_name: str,
        p_key_field_name: str,
        s_key_field_name: str,
        value_field_name: str,
        param_name: str = None,
        safe_content: bool = False,
        use_links: bool = False,
        use_images: bool = False,
        image_height: int = 80,
        hide_header: bool = False,
        show_background_toggler: bool = False,
    ):
        obj_field = getattr(obj, model_field_name, {})
        if param_name is None:
            data = obj_field
        else:
            data = obj_field.get(param_name, {})
        if not data:
            return '-'

        data_to_render = {}
        for key, value in data.items():
            p_key, s_key = key.split('_', maxsplit=1)
            data_to_render[(p_key, s_key)] = value

        t = loader.get_template('admin/includes/table_layout.html')
        headers = [p_key_field_name, s_key_field_name, value_field_name]
        return t.render(
            context={
                'headers': headers,
                'data_to_render': data_to_render,
                'use_links': use_links,
                'use_images': use_images,
                'safe_content': safe_content,
                'image_height': image_height,
                'hide_header': hide_header,
                'key_fields_count': 2,
                'show_background_toggler': show_background_toggler,
                'is_complex': True,
            },
        )

    def get_custom_value(
        self,
        obj: Model,
        model_field_name: str = 'extra',
        *,
        default_field_name: str,
        custom_field_name: str,
    ) -> Optional[str]:
        custom_param = self._custom_display_params.get(custom_field_name)
        if not hasattr(obj, model_field_name):
            raise ValueError(f'{obj} has no field {model_field_name}')
        field_value = getattr(obj, model_field_name) or {}
        custom_data = field_value.get(custom_field_name)
        if custom_param and custom_data:
            return custom_data.get(custom_param)
        return getattr(obj, default_field_name, None)
