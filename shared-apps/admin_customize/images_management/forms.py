import os.path
import uuid
from copy import deepcopy
from typing import (
    TYPE_CHECKING, Any, Callable, Collection, Optional, Type,
    Union,
)

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from pydantic import BaseModel, root_validator

from admin_customize.forms import BasicAdminActionForm
from bm.django_utils.field_value_path import FieldValuePath
from s3.utils import upload_django_in_memory_public_image
from .init import get_s3
from .utils import get_file_extension, maybe_patch_static_s3_url_to_use_proxy

if TYPE_CHECKING:
    from django.db.models import Model


class FormImageData(BaseModel):
    image: Optional[UploadedFile] = None
    image_url: Optional[str] = None
    delete_image: bool = False

    def should_be_uploaded(self) -> bool:
        return bool(self.image and not self.image_url and not self.delete_image)

    @root_validator
    def check_values_present(cls, values: dict[str, Any]) -> dict[str, Any]:
        assert any(values.values()), 'Should be set any of params'
        return values

    class Config:
        arbitrary_types_allowed = True


class DynamicImageManagementForm(BasicAdminActionForm):
    field_prefix: str
    upload_path: str
    remove_deleted_urls: bool = True
    field_value_path: FieldValuePath
    base_for_fields: Optional[list[str]] = None
    should_field_be_added_value: Optional[bool] = None
    field_help_text: Optional[Union[dict[str, str], str]] = None

    @classmethod
    def construct_from(
        cls,
        *,
        field_prefix: str = '',
        upload_path: str,
        remove_deleted_urls: bool = True,
        instance_field_path: Union[str, FieldValuePath],
        base_for_fields: Union[Callable[['DynamicImageManagementForm'], list[str]], list[str]],
        should_field_be_added: Union[Callable[['DynamicImageManagementForm', str], bool], bool],
        field_help_text: Optional[Union[dict[str, str], str]] = None,
    ) -> Type['DynamicImageManagementForm']:
        new_form = deepcopy(cls)
        new_form.field_prefix = field_prefix
        new_form.upload_path = upload_path
        new_form.remove_deleted_urls = remove_deleted_urls
        new_form.field_help_text = field_help_text

        if isinstance(instance_field_path, str):
            instance_field_path = FieldValuePath.from_field_path(instance_field_path, nullable=True)
        new_form.field_value_path = instance_field_path

        if callable(base_for_fields):
            new_form.get_base_for_fields = base_for_fields  # type: ignore
        elif isinstance(base_for_fields, list):
            new_form.base_for_fields = base_for_fields
        else:
            raise ValueError('base_for_fields should be callable or list')

        if callable(should_field_be_added):
            new_form.should_field_be_added = should_field_be_added  # type: ignore
        elif isinstance(should_field_be_added, bool):
            new_form.should_field_be_added_value = should_field_be_added
        else:
            raise ValueError('should_field_be_added should be callable or bool')

        return new_form

    def get_base_for_fields(self) -> list[str]:
        if self.base_for_fields is None:
            raise NotImplementedError()
        return self.base_for_fields

    def should_field_be_added(self, item: str) -> bool:
        if self.should_field_be_added_value is None:
            raise NotImplementedError()
        return self.should_field_be_added_value

    def get_current_state(self) -> dict[str, Optional[str]]:
        return self.field_value_path.get_value(self.instance) or {}

    def set_new_state(self, data: dict[str, Optional[str]]) -> None:
        self.field_value_path.set_value(self.instance, data)

    def __init__(self, *args: Any, instance: 'Model', **kwargs: Any) -> None:
        self.instance = instance
        self._structured_data: Optional[dict[str, FormImageData]] = None
        super().__init__(*args, **kwargs)

        for item in self.get_base_for_fields():
            if not self.should_field_be_added(item):
                continue
            current_url = self.get_current_state().get(item)
            if current_url:
                preview_data = (
                    f'Current url: <a href="{current_url}">{current_url}</a><br>'
                    f'<img class="image-preview" src="{current_url}" '
                    f'alt="" height="40">'
                )
            else:
                preview_data = ''

            if self.field_help_text:
                if isinstance(self.field_help_text, dict):
                    help_text = self.field_help_text.get(item, '')
                else:
                    help_text = self.field_help_text
            else:
                help_text = ''
            self.fields[f'{self.field_prefix}_{item}_image'] = forms.FileField(
                required=False, label=f'{item.capitalize()} Image', help_text=preview_data
            )
            self.fields[f'{self.field_prefix}_{item}_image_url'] = forms.URLField(
                required=False,
                label=f'{item.capitalize()} Image Url',
                widget=forms.widgets.TextInput(attrs={'size': 80}),
                help_text=help_text,
            )
            self.fields[f'{self.field_prefix}_{item}_delete_image'] = forms.BooleanField(
                required=False,
                label=f'Delete {item.capitalize()} Image',
                help_text='<br><br><br><br>',
            )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        cleaned_data_by_items = {}
        for item in self.get_base_for_fields():
            image = cleaned_data.get(f'{self.field_prefix}_{item}_image')
            image_url = cleaned_data.get(f'{self.field_prefix}_{item}_image_url')
            image_delete = cleaned_data.get(f'{self.field_prefix}_{item}_delete_image')
            if any([image, image_url, image_delete]):
                try:
                    cleaned_data_by_items[item] = FormImageData(
                        image=image, image_url=image_url, delete_image=image_delete
                    )
                except ValueError as e:
                    errors = [str(e_.exc) for e_ in e.raw_errors]  # type: ignore[attr-defined]
                    raise forms.ValidationError(', '.join(errors))
        self._structured_data = cleaned_data_by_items
        return cleaned_data

    def process(self) -> None:
        images_section = self.get_current_state()
        assert self._structured_data is not None
        for item, data in self._structured_data.items():
            if data.should_be_uploaded():
                new_file_name = '.'.join([str(uuid.uuid4()), get_file_extension(data.image)])
                image_url = upload_django_in_memory_public_image(
                    in_memory_file=data.image,
                    s3_config=get_s3(),
                    new_filename=new_file_name,
                    subfolder=os.path.join(self.upload_path, item),
                )
            elif data.image_url:
                image_url = data.image_url
            else:
                image_url = ''
            if image_url:
                image_url = maybe_patch_static_s3_url_to_use_proxy(image_url)
            images_section[item] = image_url
            if data.delete_image and self.remove_deleted_urls:
                images_section.pop(item, None)
            elif data.delete_image and not self.remove_deleted_urls:
                images_section[item] = None
        self.set_new_state(images_section)
        return self.instance.save()


class BaseImageUploadForm(forms.Form):
    image = forms.FileField(required=False)
    image_url = forms.URLField(required=False, widget=forms.widgets.TextInput(attrs={'size': 80}))

    def __init__(
        self,
        *args: Any,
        current_url: str,
        allowed_content_types: Optional[Collection[str]] = None,
        **kwargs: Any,
    ) -> None:
        self.allowed_content_types = allowed_content_types
        self._current_url = current_url
        super().__init__(*args, **kwargs)
        if self._current_url:
            self.fields['image'].help_text = (
                f'Current url: <a href="{self._current_url}">{self._current_url}</a><br>'
                f'<img class="image-preview" src="{self._current_url}" alt="" height="40">'
            )

    def _clean_image(self) -> Optional[UploadedFile]:
        image_url = self.cleaned_data.get('image_url')
        if image_url:
            return None
        image = self.cleaned_data.get('image')
        if image is None:
            self.add_error(None, 'You should upload an image or set an image url')
            return None
        if self.allowed_content_types is not None and image.content_type not in self.allowed_content_types:
            allowed_types_str = ', '.join(
                [f'"{allowed_content_type}"' for allowed_content_type in self.allowed_content_types]
            )
            raise ValidationError(f'allowed file types are: {allowed_types_str}')
        return image

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        self._clean_image()
        return cleaned_data


class BaseImageUploadOrRemoveForm(BaseImageUploadForm):
    remove = forms.BooleanField(required=False)

    def __init__(
        self,
        *args: Any,
        current_url: str,
        allowed_content_types: Optional[Collection[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            current_url=current_url,
            allowed_content_types=allowed_content_types,
            **kwargs,
        )
        self.fields['remove'].disabled = not current_url

    def _clean_image(self) -> Optional[UploadedFile]:
        if self.cleaned_data.get('remove', False):
            return None
        return super()._clean_image()


class ImageUploadOrRemoveForm(BaseImageUploadOrRemoveForm, BasicAdminActionForm):
    pass
