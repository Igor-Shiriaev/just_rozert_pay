from typing import Any

from admin_customize.utils import add_param_to_url
from django.contrib.admin.views.main import PAGE_VAR
from django.core.paginator import Paginator
from django.template import Library
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

register = Library()


@register.inclusion_tag("admin/includes/pagination.html")
def universal_pagination(
    paginator: Paginator,
    current_page_number: int,
    opts: Any,
    suffix: str = None,
    suffix_plural: str = None,
) -> dict[str, Any]:
    pagination_required = paginator.num_pages > 1
    pages_range = (
        paginator.get_elided_page_range(current_page_number) if pagination_required else []
    )
    need_show_all_link = False
    return {
        "opts": opts,
        "paginator": paginator,
        "pagination_required": pagination_required,
        "page_range": pages_range,
        "current_page_number": current_page_number,
        "need_show_all_link": need_show_all_link,
        "PAGE_VAR": "p",
        "suffix": suffix,
        "suffix_plural": suffix_plural,
    }


@register.simple_tag(takes_context=True)
def paginator_number(
    context: Any, paginator: Paginator, current_page: int, page_num: int
) -> SafeString:
    if page_num == paginator.ELLIPSIS:
        return format_html("{} ", paginator.ELLIPSIS)
    elif page_num == int(current_page):
        return format_html('<span class="this-page">{}</span> ', page_num)
    else:
        return format_html(
            '<a href="{}"{}>{}</a> ',
            add_param_to_url(context.request.path, {PAGE_VAR: page_num}),
            mark_safe(' class="end"' if page_num == paginator.num_pages else ""),
            page_num,
        )
