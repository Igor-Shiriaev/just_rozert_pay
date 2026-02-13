from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Union

import pytz
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import resolve_url
from django.template.response import TemplateResponse

from admin_customize.forms import BasicAdminActionForm

if TYPE_CHECKING:
    from django.http import HttpResponse
    from django.http import HttpRequest


@dataclass
class TimezoneData:
    timezone_name: str
    timezone_key: str
    timezone_offset: Union[int, float]

    def get_verbose_name(self) -> str:
        if self.timezone_offset == 0:
            return f'{self.timezone_name} (UTC)'
        elif self.timezone_offset > 0:
            return f'{self.timezone_name} (UTC+{self.timezone_offset})'
        else:
            return f'{self.timezone_name} (UTC-{abs(self.timezone_offset)})'


def get_timezones() -> list[tuple[str, str]]:
    timezones: list[TimezoneData] = []
    for tz in pytz.all_timezones:
        timezone = pytz.timezone(tz)
        timezone_offset = timezone.utcoffset(datetime(2020, 1, 1, 0, 0, 0)).total_seconds() // 3600
        timezones.append(TimezoneData(tz, tz, timezone_offset))

    timezones.sort(key=lambda x: (x.timezone_offset, x.timezone_name))

    return [(timezone.timezone_key, timezone.get_verbose_name()) for timezone in timezones]


timezone_choices = get_timezones()


class SetTimezoneForm(BasicAdminActionForm):
    timezone = forms.CharField(
        widget=forms.Select(choices=timezone_choices),
        initial=settings.TIME_ZONE,
    )
    return_url = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args: Any, instance: Any, **kwargs: Any) -> None:
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields['timezone'].initial = self.instance.extra.get('timezone', settings.TIME_ZONE)

    @transaction.atomic
    def process(self) -> None:
        user = get_user_model().objects.select_for_update().get(pk=self.instance.pk)
        if not hasattr(user, 'extra'):
            return None
        user.extra['timezone'] = self.cleaned_data['timezone']  # type: ignore
        user.save()
        self.request.session['django_timezone'] = self.cleaned_data['timezone']


def set_timezone(request: 'HttpRequest') -> 'HttpResponse':
    if not request.user.is_authenticated:
        raise Http404()

    form = SetTimezoneForm(
        request, instance=request.user, initial={'return_url': request.META.get('HTTP_REFERER')}
    )
    if form.is_valid():
        form.process()
        return HttpResponseRedirect(
            form.cleaned_data.get('return_url', resolve_url('admin:index'))
        )

    return TemplateResponse(
        request,
        'admin/simple_custom_intermediate_form.html',
        {
            'form': form,
            'opts': request.user._meta,
        },
    )
