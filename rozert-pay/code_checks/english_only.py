# type: ignore
"""
Pylint plugin to ensure Django fields, admin texts, and error messages are in English only.

This checker verifies that:
- Model field parameters (help_text, verbose_name, verbose_name_plural, error_messages)
- Admin class parameters (description, fieldsets labels)
- ValidationError messages
- Form help_texts
Do not contain non-ASCII characters (which would indicate non-English text).

Usage:
    Add to pylintrc:
    [MASTER]
    load-plugins=code_checks.english_only

    [MESSAGES CONTROL]
    enable=non-english-text
"""

import re
from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


# Django field kwargs that should contain English-only text
DJANGO_FIELD_KWARGS = frozenset(
    {
        "help_text",
        "verbose_name",
        "verbose_name_plural",
        "error_messages",
        "label",
        "label_suffix",
        "empty_label",
        "initial",
    }
)

# Django admin/form class attributes that should contain English-only text
DJANGO_ADMIN_ATTRS = frozenset(
    {
        "description",
        "short_description",
        "empty_value_display",
    }
)

# Functions/classes where string arguments should be English-only
ENGLISH_ONLY_CALLS = frozenset(
    {
        "ValidationError",
        "PermissionDenied",
        # gettext functions - text should still be English (translations are separate)
        "_",
        "gettext",
        "gettext_lazy",
        "ngettext",
        "ngettext_lazy",
        "pgettext",
        "pgettext_lazy",
    }
)

# Pattern to check that text contains only English characters (ASCII)
# English text should contain only ASCII characters (codes 0-127):
# - Latin letters (a-z, A-Z)
# - Digits (0-9)
# - Punctuation and special characters
# - Whitespace
# Any character outside ASCII range is considered non-English
NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7F]")


def _contains_non_english(text: str) -> bool:
    """Check if text contains non-English characters (non-ASCII)."""
    return bool(NON_ASCII_PATTERN.search(text))


def _extract_string_value(node: nodes.NodeNG) -> str | None:
    """
    Extract string value from AST node.
    Handles Const nodes and simple concatenations.
    """
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        return node.value
    if isinstance(node, nodes.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, nodes.Const) and isinstance(value.value, str):
                parts.append(value.value)
        return "".join(parts) if parts else None
    return None


class EnglishOnlyChecker(BaseChecker):
    """
    Checker to ensure Django-related strings are in English only.

    This helps maintain consistency in the codebase where all user-facing
    strings should be in English (with translations handled separately via i18n).
    """

    name = "english-only-checker"
    msgs = {
        "W7010": (
            "Non-English text detected in '%s': '%s'. "
            "All Django field texts, admin descriptions, and error messages must be in English.",
            "non-english-text",
            "Used when non-English characters are detected in Django field parameters, "
            "admin descriptions, or error messages.",
        ),
        "W7011": (
            "Non-English text detected in %s call: '%s'. "
            "All messages must be in English.",
            "non-english-validation-error",
            "Used when non-English characters are detected in ValidationError, "
            "gettext, or similar function calls.",
        ),
        "W7012": (
            "Non-English text detected in fieldset label: '%s'. "
            "Admin fieldset labels must be in English.",
            "non-english-fieldset",
            "Used when non-English characters are detected in admin fieldset labels.",
        ),
    }

    def visit_call(self, node: nodes.Call) -> None:
        """Check function/class calls for non-English strings."""
        func_name = self._get_func_name(node)

        if func_name in ENGLISH_ONLY_CALLS:
            self._check_call_args(node, func_name)

        self._check_django_field_kwargs(node)

    def visit_keyword(self, node: nodes.Keyword) -> None:
        """Check keyword arguments in function calls."""
        if node.arg in DJANGO_FIELD_KWARGS:
            self._check_keyword_value(node)

    def visit_assign(self, node: nodes.Assign) -> None:
        """Check assignments for admin attributes."""
        for target in node.targets:
            if isinstance(target, nodes.AssignName):
                if target.name in DJANGO_ADMIN_ATTRS:
                    string_value = _extract_string_value(node.value)
                    if string_value and _contains_non_english(string_value):
                        self.add_message(
                            "non-english-text",
                            node=node,
                            args=(target.name, self._truncate(string_value)),
                        )

    def visit_dict(self, node: nodes.Dict) -> None:
        """Check dictionary literals for fieldsets and error_messages."""
        self._check_dict_for_non_english(node)

    def visit_tuple(self, node: nodes.Tuple) -> None:
        """Check tuple literals for fieldsets."""
        self._check_tuple_for_fieldset_labels(node)

    def _get_func_name(self, node: nodes.Call) -> str | None:
        """Extract function name from Call node."""
        if isinstance(node.func, nodes.Name):
            return node.func.name
        if isinstance(node.func, nodes.Attribute):
            return node.func.attrname
        return None

    def _check_call_args(self, node: nodes.Call, func_name: str) -> None:
        """Check positional arguments in function calls."""
        for arg in node.args:
            string_value = _extract_string_value(arg)
            if string_value and _contains_non_english(string_value):
                self.add_message(
                    "non-english-validation-error",
                    node=node,
                    args=(func_name, self._truncate(string_value)),
                )

    def _check_django_field_kwargs(self, node: nodes.Call) -> None:
        """Check Django field keyword arguments."""
        for keyword in node.keywords:
            if keyword.arg in DJANGO_FIELD_KWARGS:
                self._check_keyword_value(keyword)

    def _check_keyword_value(self, node: nodes.Keyword) -> None:
        """Check keyword value for non-English text."""
        string_value = _extract_string_value(node.value)
        if string_value and _contains_non_english(string_value):
            self.add_message(
                "non-english-text",
                node=node,
                args=(node.arg, self._truncate(string_value)),
            )

        if isinstance(node.value, nodes.Dict):
            self._check_dict_for_non_english(node.value, context=node.arg)

    def _check_dict_for_non_english(
        self, node: nodes.Dict, context: str = "dict"
    ) -> None:
        """Check dictionary values for non-English text."""
        for key, value in node.items:
            string_value = _extract_string_value(value)
            if string_value and _contains_non_english(string_value):
                key_name = _extract_string_value(key) if key else "unknown"
                self.add_message(
                    "non-english-text",
                    node=value,
                    args=(f"{context}[{key_name}]", self._truncate(string_value)),
                )

    def _check_tuple_for_fieldset_labels(self, node: nodes.Tuple) -> None:
        """Check if tuple looks like a fieldset definition and validate labels."""
        if len(node.elts) >= 2:
            first_elem = node.elts[0]
            second_elem = node.elts[1]

            if isinstance(first_elem, nodes.Const) and isinstance(
                second_elem, nodes.Dict
            ):
                string_value = _extract_string_value(first_elem)
                if string_value and _contains_non_english(string_value):
                    self.add_message(
                        "non-english-fieldset",
                        node=first_elem,
                        args=(self._truncate(string_value),),
                    )

    def _truncate(self, text: str, max_length: int = 50) -> str:
        """Truncate text for display in error messages."""
        if len(text) > max_length:
            return text[: max_length - 3] + "..."
        return text


def register(linter: "PyLinter") -> None:  # pragma: no cover
    linter.register_checker(EnglishOnlyChecker(linter))
