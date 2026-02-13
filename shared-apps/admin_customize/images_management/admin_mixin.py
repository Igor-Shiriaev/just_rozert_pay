import io
import uuid
from typing import TYPE_CHECKING, Callable, Optional, Type, Union

import requests
from admin_customize.admin.utils import log_change
from bm.django_utils.field_value_path import FieldValuePath
from django.contrib import messages
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model
from django.template.response import TemplateResponse
from django.utils.safestring import mark_safe
from s3.utils import upload_django_in_memory_public_image

from .forms import DynamicImageManagementForm, ImageUploadOrRemoveForm
from .init import get_s3
from .utils import get_file_extension, maybe_patch_static_s3_url_to_use_proxy

if TYPE_CHECKING:
    from django.http import HttpRequest


class ImagesManagementMixin:
    model: Type['Model']
    message_user: Callable

    DEFAULT_IMAGE_HEIGHT = 40  # height in pixels

    @mark_safe
    def get_image_preview(
        self, *, obj: 'Model', field_path: str, image_height: int = None, show_url: bool = True
    ) -> str:
        assert image_height is None or image_height > 0
        image_url = self._get_current_url(obj=obj, field_path=field_path)
        height = image_height or self.DEFAULT_IMAGE_HEIGHT
        if not image_url:
            return ''

        url_input = f'<input value="{image_url}" readonly size="30"><br>' if show_url else ''
        return (
            f'{url_input}'
            f'<img class="image-preview" src="{image_url}" '
            f'alt="" height="{height}">'
        )

    @mark_safe
    def get_images_preview(
        self,
        *,
        obj: 'Model',
        field_path_prefix: str,
        options: list[str],
        filters: list[str] = None,
        image_height: int = None,
    ) -> str:
        blocks = []
        for option in options:
            if filters and option not in filters:
                continue
            html_block = self.get_image_preview(
                obj=obj, field_path=f'{field_path_prefix}.{option}', image_height=image_height
            )
            if not html_block:
                continue
            blocks.append(f'<b>{option.capitalize()}</b><br>{html_block}<br>')
        if not blocks:
            return '-'
        return ''.join(blocks)

    def image_upload_or_remove_view(
        self,
        *,
        request: 'HttpRequest',
        obj: 'Model',
        method_name: str,  # Needed for form initialization
        field_path: str,
        subfolder: str,
    ) -> Optional[TemplateResponse]:
        current_url = self._get_current_url(obj=obj, field_path=field_path)
        public_static_bucket_config = get_s3().config_for_public_static_bucket
        form = ImageUploadOrRemoveForm(
            request,
            current_url=current_url,
            action=method_name,
            allowed_content_types=public_static_bucket_config.content_types,
        )
        if form.is_valid():
            if form.cleaned_data['remove']:
                if not self._get_current_url(obj=obj, field_path=field_path):
                    return None
                self._set_new_url(obj=obj, field_path=field_path, image_url=None)
                obj.save()
                log_change(
                    admin_id=request.user.pk,
                    obj=obj,
                    change_message=f'Removed image from field {field_path}',
                )
                self.message_user(
                    request, f'Removed image from field {field_path}', messages.SUCCESS
                )
            else:
                if form.cleaned_data['image']:
                    file_to_upload = form.cleaned_data['image']
                    image_url = self._upload_image(
                        image_file=file_to_upload, upload_path=subfolder
                    )
                else:
                    image_url = form.cleaned_data['image_url']
                if image_url:
                    image_url = maybe_patch_static_s3_url_to_use_proxy(image_url)
                self._set_new_url(obj=obj, field_path=field_path, image_url=image_url)
                obj.save()
                self.message_user(request, f'Uploaded new image as {field_path}', messages.SUCCESS)
                log_change(
                    request.user.pk,
                    obj,
                    f'Replaced image in {field_path} from {current_url} to {image_url}',
                )
            return None
        return TemplateResponse(
            request, form.form_template, form.make_context(model=self.model, obj=obj)
        )

    def images_upload_or_remove_view(
        self,
        request: 'HttpRequest',
        obj: 'Model',
        upload_path: str,
        instance_field_path: Union[str, FieldValuePath],
        base_for_fields: Union[Callable[['DynamicImageManagementForm'], list[str]], list[str]],
        should_field_be_added: Callable[['DynamicImageManagementForm', str], bool],
        field_prefix: str = '',
        remove_deleted_urls: bool = True,
        field_help_text: Optional[Union[dict[str, str], str]] = None,
    ) -> Optional[TemplateResponse]:
        form_class = DynamicImageManagementForm.construct_from(
            upload_path=upload_path,
            base_for_fields=base_for_fields,
            should_field_be_added=should_field_be_added,
            instance_field_path=instance_field_path,
            field_prefix=field_prefix,
            remove_deleted_urls=remove_deleted_urls,
            field_help_text=field_help_text,
        )
        form = form_class(request, instance=obj)
        if form.is_valid():
            form.process()
            log_change(
                admin_id=request.user.pk,
                obj=obj,
                change_message=f'Updated images for {instance_field_path}',
            )
            self.message_user(
                request, f'Updated images for {instance_field_path}', messages.SUCCESS
            )
            return None
        return TemplateResponse(
            request, form.form_template, form.make_context(model=self.model, obj=obj)
        )

    @staticmethod
    def _get_current_url(*, obj: 'Model', field_path: str) -> str:
        image_path = FieldValuePath.from_field_path(field_path)
        return image_path.get_value(obj) or ''

    @staticmethod
    def _set_new_url(*, obj: 'Model', field_path: str, image_url: Optional[str]) -> None:
        image_path = FieldValuePath.from_field_path(field_path, nullable=True)
        image_path.set_value(obj, image_url)

    def load_foreign_image(
        self, request: 'HttpRequest', obj: 'Model', field_path: FieldValuePath, upload_path: str
    ) -> None:
        original_image_url = field_path.get_value(obj)
        if not original_image_url:
            self.message_user(request, f'No image found in {str(field_path)}', messages.ERROR)
            return
        if original_image_url.startswith(get_s3().public_url_for_public_static_bucket):
            self.message_user(
                request,
                f'Image in {str(field_path)} is already on our S3',
                messages.ERROR,
            )
            return

        image_file = self._load_image(original_image_url)
        if not image_file:
            self.message_user(request, f'No image found in {str(field_path)}', messages.ERROR)
            return

        image_url = self._upload_image(image_file, upload_path)

        field_path.nullable = True
        field_path.set_value(obj, image_url)
        obj.save()
        self.message_user(request, f'Uploaded new image as {str(field_path)}', messages.SUCCESS)
        log_change(
            request.user.pk,
            obj,
            f'Replaced image in {str(field_path)} from {original_image_url} to {image_url}',
        )

    def load_foreign_images(
        self,
        request: 'HttpRequest',
        obj: 'Model',
        field_path: FieldValuePath,
        upload_path: str,
    ) -> None:
        original_image_urls: dict[str, str] = field_path.get_value(obj) or {}
        if not original_image_urls:
            self.message_user(request, f'No images found in {str(field_path)}', messages.ERROR)
            return
        if all(
            original_image_url.startswith(get_s3().public_url_for_public_static_bucket)
            for original_image_url in original_image_urls.values()
        ):
            self.message_user(
                request,
                f'Images in {str(field_path)} are already on our S3',
                messages.ERROR,
            )
            return
        data_to_process: dict[str, str] = {}
        for key, original_image_url in original_image_urls.items():
            if not original_image_url.startswith(get_s3().public_url_for_public_static_bucket):
                data_to_process[key] = original_image_url

        new_image_urls: dict[str, str] = {}
        for key, original_image_url in data_to_process.items():
            image_file = self._load_image(original_image_url)
            if not image_file:
                self.message_user(request, f'No image found in {str(field_path)}', messages.ERROR)
                return

            image_url = self._upload_image(image_file, upload_path)
            new_image_urls[key] = image_url

        field_path.nullable = True
        field_path.set_value(obj, new_image_urls)
        obj.save()
        self.message_user(request, f'Uploaded new images as {str(field_path)}', messages.SUCCESS)
        log_change(
            request.user.pk,
            obj,
            f'Replaced images in {str(field_path)} from {original_image_urls} to {new_image_urls}',
        )

    @staticmethod
    def _load_image(
        image_url: str,
    ) -> Optional['UploadedFile']:
        image_response = requests.get(image_url)

        if image_response.status_code == 404:
            return None
        elif image_response.status_code >= 400:
            image_response.raise_for_status()

        io_container = io.BytesIO(image_response.content)

        image_file = UploadedFile(
            file=io_container,
            name=image_url.rsplit('/', maxsplit=1)[-1],
            size=len(image_response.content),
            content_type=image_response.headers['Content-Type'],
        )
        return image_file

    @staticmethod
    def _upload_image(
        image_file: 'UploadedFile',
        upload_path: str,
    ) -> str:
        new_file_name = '.'.join([str(uuid.uuid4()), get_file_extension(image_file)])
        image_url = upload_django_in_memory_public_image(
            in_memory_file=image_file,
            s3_config=get_s3(),
            new_filename=new_file_name,
            subfolder=upload_path,
        )
        return image_url
