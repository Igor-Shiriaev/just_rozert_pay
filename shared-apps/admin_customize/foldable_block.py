from django.template import loader
from django.utils.safestring import mark_safe


@mark_safe
def foldable_block(title: str, content: str, collapsed: bool = True) -> str:
    template = loader.get_template('foldable_block.html')
    return template.render(
        {
            'title': title,
            'content': content,
            'collapsed': collapsed,
        },
    )
