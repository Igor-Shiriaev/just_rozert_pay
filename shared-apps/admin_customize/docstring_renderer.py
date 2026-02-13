import re
from typing import Any, Optional

from django.template import loader
from django.utils.safestring import SafeString, mark_safe
from pydantic import BaseModel

from admin_customize.foldable_block import foldable_block


class Describable(BaseModel):
    name: str
    description: Optional[str] = None


class TemplateContext(BaseModel):
    title: str
    description: Optional[str] = None
    parameters: Optional[list[Describable]] = None
    return_value: Optional[str] = None
    raises: Optional[list[Describable]] = None
    example: Optional[str] = None


@mark_safe
def docstring_to_html(obj: Any, collapse: bool = False) -> str:
    """
    Converts docstring to HTML format.
    """

    docstring = obj.__doc__

    if not docstring:
        return SafeString('')

    custom_title_regex = r':title\s+(?P<name>.*?):'
    custom_title_data = re.search(custom_title_regex, docstring, flags=re.DOTALL)
    if custom_title_data:
        custom_title = custom_title_data.group('name').strip()
    else:
        custom_title = None

    description_regex = (
        r'(?P<description>.*?)(?=\s*:param|\s*:return:|\s*:raises|\s*:title|\s*```|\Z)'
    )

    description_data = re.search(description_regex, docstring, flags=re.DOTALL)
    if description_data:
        description = description_data.group('description').strip().split('\n')
        description = [line.strip() for line in description]
        description_value = ''.join(map(lambda x: f'<p>{x}</p>', description))
    else:
        description_value = None

    params_regex = r':param\s+(?P<name>\w+):\s*(?P<description>.*?)\n'
    params_data = re.findall(params_regex, docstring, flags=re.DOTALL)
    if params_data:
        params_value = [
            Describable(name=param[0], description=param[1].strip()) for param in params_data
        ]
    else:
        params_value = None

    returns_regex = r':return:\s*(?P<description>.*?)\n'
    returns_data = re.search(returns_regex, docstring, flags=re.DOTALL)
    if returns_data:
        return_value = returns_data.group(1).strip()
    else:
        return_value = None

    raises_regex = r':raises\s+(?P<name>\w+):\s*(?P<description>.*?)\n'
    raises_data = re.findall(raises_regex, docstring, flags=re.DOTALL)
    if raises_data:
        raises_value = [
            Describable(name=raise_[0], description=raise_[1].strip()) for raise_ in raises_data
        ]
    else:
        raises_value = None

    code_regex = r'```(.*?)```'
    code_data = re.search(code_regex, docstring, flags=re.DOTALL)
    if code_data:
        code_lines = code_data.group(1).split('\n')
        code_lines = [line.strip() for line in code_lines]
        code_value = '\n'.join(code_lines)
    else:
        code_value = None

    template = loader.get_template('docstring_renderer.html')

    dockstring_block = template.render(
        TemplateContext(
            title=custom_title or obj.__name__,
            description=description_value,
            parameters=params_value,
            return_value=return_value,
            raises=raises_value,
            example=code_value,
        ).dict()
    )

    return foldable_block(
        title=custom_title or obj.__name__,
        content=dockstring_block,
        collapsed=collapse,
    )
