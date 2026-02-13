from django.template import Template
from django.template.base import Node  # type: ignore[attr-defined]
from django.template.base import NodeList  # type: ignore[attr-defined]
from django.template.base import VariableNode  # type: ignore[attr-defined]
from django.template.library import SimpleNode  # type: ignore[attr-defined]


class TemplateVariable:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f'TemplateVariable(name={self.name})'

    @classmethod
    def from_variable_node(cls, node: VariableNode) -> 'TemplateVariable':
        var_name = node.filter_expression.var.var
        return cls(name=var_name)


class TemplateTag:
    def __init__(self, name: str, args: list[str]) -> None:
        self.name = name
        self.args = args

    def __repr__(self) -> str:
        if self.args:
            args_str = ', '.join(map(str, self.args))
            return f'TemplateTag(name={self.name}, args=[{args_str}])'
        else:
            return f'TemplateTag(name={self.name})'

    @classmethod
    def from_tag_node(cls, node: SimpleNode) -> 'TemplateTag':
        tag_name, *tag_args = node.token.split_contents()

        return cls(name=tag_name, args=tag_args if tag_args else [])

    @property
    def clear_args(self) -> list[str]:
        return [arg.strip('"').strip("'") for arg in self.args if isinstance(arg, str)]


class TemplateExtractor:
    def __init__(self, template_code: str):
        self.template_code = template_code
        self._variables, self._tags = self.extract_vars_and_tags(self.template_code)

    @staticmethod
    def extract_vars_and_tags(template_code: str) -> tuple[set[VariableNode], set[SimpleNode]]:
        try:
            template = Template(template_code)
        except Exception:
            return set(), set()  # Return empty sets on error
        variables = set()
        tags = set()

        def walk_nodelist(nodelist: list[Node] | NodeList) -> None:  # type: ignore
            for node in nodelist:  # type: ignore
                if isinstance(node, VariableNode):
                    variables.add(node)
                elif isinstance(node, SimpleNode):
                    tags.add(node)
                for attr in dir(node):
                    value = getattr(node, attr, None)
                    if isinstance(value, NodeList):
                        walk_nodelist(value)
                    elif isinstance(value, list):
                        for sub in value:
                            if isinstance(sub, NodeList):
                                walk_nodelist(sub)

        walk_nodelist(template.nodelist)  # type: ignore[attr-defined]
        return variables, tags

    @property
    def directly_used_variables(self) -> list[TemplateVariable]:
        return [TemplateVariable.from_variable_node(var) for var in self._variables]

    @property
    def tags(self) -> list[TemplateTag]:
        return [TemplateTag.from_tag_node(tag) for tag in self._tags]

    @property
    def variables(self) -> set[str]:
        directly_used_vars = [var.name for var in self.directly_used_variables]
        tags_used_vars = [tag.clear_args[0] for tag in self.tags if tag.clear_args]
        return set(directly_used_vars + tags_used_vars)
