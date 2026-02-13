"""
Tests for the english_only pylint checker.

This module tests that the checker correctly identifies non-English text
in Django field parameters, admin descriptions, and error messages.
"""

from unittest.mock import MagicMock

import astroid  # type: ignore[import-untyped]
from code_checks.english_only import (  # type: ignore[attr-defined,import]
    EnglishOnlyChecker,
    _contains_non_english,
    _extract_string_value,
)
from pylint.testutils import CheckerTestCase, MessageTest


def make_message_test(
    msg_id: str, node: astroid.NodeNG, args: tuple[str, ...]
) -> MessageTest:
    """Helper to create MessageTest with all required fields from node."""
    return MessageTest(
        msg_id=msg_id,
        node=node,
        line=node.lineno,
        col_offset=node.col_offset,
        end_line=node.end_lineno,
        end_col_offset=node.end_col_offset,
        args=args,
    )


class TestEnglishOnlyChecker(CheckerTestCase):
    """Test cases for EnglishOnlyChecker."""

    CHECKER_CLASS = EnglishOnlyChecker

    def test_english_help_text_is_allowed(self) -> None:
        """Test that English help_text passes without warnings."""
        node = astroid.extract_node(
            """
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(
                    max_length=100,
                    help_text="Enter your name here"  #@
                )
            """
        )
        with self.assertNoMessages():
            self.checker.visit_call(node.parent)

    def test_cyrillic_help_text_is_detected(self) -> None:
        """Test that Cyrillic text in help_text is detected."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        help_text="Введите ваше имя"
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]
        help_text_keyword = next(
            kw for kw in call_node.keywords if kw.arg == "help_text"
        )

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                help_text_keyword,
                ("help_text", "Введите ваше имя"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_cyrillic_verbose_name_is_detected(self) -> None:
        """Test that Cyrillic text in verbose_name is detected."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name="Имя пользователя"
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]
        verbose_name_keyword = next(
            kw for kw in call_node.keywords if kw.arg == "verbose_name"
        )

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                verbose_name_keyword,
                ("verbose_name", "Имя пользователя"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_english_verbose_name_is_allowed(self) -> None:
        """Test that English verbose_name passes without warnings."""
        node = astroid.extract_node(
            """
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(
                    max_length=100,
                    verbose_name="User name"  #@
                )
            """
        )
        with self.assertNoMessages():
            self.checker.visit_call(node.parent)

    def test_cyrillic_validation_error_is_detected(self) -> None:
        """Test that Cyrillic text in ValidationError is detected."""
        code = """
from django.core.exceptions import ValidationError

def validate_something(value):
    raise ValidationError("Неверное значение")
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]

        with self.assertAddsMessages(
            make_message_test(
                "non-english-validation-error",
                call_node,
                ("ValidationError", "Неверное значение"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_english_validation_error_is_allowed(self) -> None:
        """Test that English ValidationError passes without warnings."""
        code = """
from django.core.exceptions import ValidationError

def validate_something(value):
    raise ValidationError("Invalid value")
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]

        with self.assertNoMessages():
            self.checker.visit_call(call_node)

    def test_cyrillic_fieldset_label_is_detected(self) -> None:
        """Test that Cyrillic text in fieldset labels is detected."""
        code = """
fieldsets = (
    ("Основная информация", {"fields": ("name", "email")}),
)
"""
        module = astroid.parse(code)
        tuple_nodes = list(module.nodes_of_class(astroid.Tuple))
        fieldset_tuple = tuple_nodes[1]
        label_node = fieldset_tuple.elts[0]

        with self.assertAddsMessages(
            make_message_test(
                "non-english-fieldset",
                label_node,
                ("Основная информация",),
            )
        ):
            self.checker.visit_tuple(fieldset_tuple)

    def test_english_fieldset_label_is_allowed(self) -> None:
        """Test that English fieldset labels pass without warnings."""
        node = astroid.extract_node(
            """
            ("Core Information", {"fields": ("name", "email")})  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_tuple(node)

    def test_chinese_text_is_detected(self) -> None:
        """Test that Chinese text is detected."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        help_text="输入您的名字"
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]
        help_text_keyword = next(
            kw for kw in call_node.keywords if kw.arg == "help_text"
        )

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                help_text_keyword,
                ("help_text", "输入您的名字"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_arabic_text_is_detected(self) -> None:
        """Test that Arabic text is detected."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        help_text="أدخل اسمك"
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]
        help_text_keyword = next(
            kw for kw in call_node.keywords if kw.arg == "help_text"
        )

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                help_text_keyword,
                ("help_text", "أدخل اسمك"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_admin_description_with_cyrillic_is_detected(self) -> None:
        """Test that Cyrillic text in admin description assignment is detected."""
        code = """
description = "Описание модели"
"""
        module = astroid.parse(code)
        assign_node = list(module.nodes_of_class(astroid.Assign))[0]

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                assign_node,
                ("description", "Описание модели"),
            )
        ):
            self.checker.visit_assign(assign_node)

    def test_english_admin_description_is_allowed(self) -> None:
        """Test that English admin description passes without warnings."""
        node = astroid.extract_node(
            """
            description = "Model description"  #@
            """
        )
        with self.assertNoMessages():
            self.checker.visit_assign(node)

    def test_error_messages_dict_with_cyrillic_is_detected(self) -> None:
        """Test that Cyrillic text in error_messages dict is detected."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        error_messages={"required": "Это поле обязательно"}
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]
        error_messages_keyword = next(
            kw for kw in call_node.keywords if kw.arg == "error_messages"
        )
        dict_node = error_messages_keyword.value
        required_value = next(
            value
            for key, value in dict_node.items
            if _extract_string_value(key) == "required"
        )

        with self.assertAddsMessages(
            make_message_test(
                "non-english-text",
                required_value,
                ("error_messages[required]", "Это поле обязательно"),
            )
        ):
            self.checker.visit_call(call_node)

    def test_mixed_ascii_special_chars_allowed(self) -> None:
        """Test that special ASCII characters are allowed."""
        node = astroid.extract_node(
            """
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(
                    max_length=100,
                    help_text="Enter value (e.g., 'test-123' or $100.00)"  #@
                )
            """
        )
        with self.assertNoMessages():
            self.checker.visit_call(node.parent)

    def test_gettext_wrapped_cyrillic_is_detected(self) -> None:
        """Test that Cyrillic text wrapped in _() is still detected."""
        code = """
from django.utils.translation import gettext_lazy as _
from django.db import models

class MyModel(models.Model):
    class Meta:
        verbose_name = _("Модель")
"""
        module = astroid.parse(code)
        call_nodes = list(module.nodes_of_class(astroid.Call))
        gettext_call = call_nodes[0]

        with self.assertAddsMessages(
            make_message_test(
                "non-english-validation-error",
                gettext_call,
                ("_", "Модель"),
            )
        ):
            self.checker.visit_call(gettext_call)

    def test_long_text_is_truncated_in_message(self) -> None:
        """Test that long text is truncated in error messages."""
        code = """
from django.db import models

class MyModel(models.Model):
    name = models.CharField(
        max_length=100,
        help_text="Это очень длинное описание на русском языке которое должно быть обрезано в сообщении об ошибке"
    )
"""
        module = astroid.parse(code)
        call_node = list(module.nodes_of_class(astroid.Call))[0]

        self.checker.visit_call(call_node)


class TestEnglishOnlyCheckerHelpers:
    """Test helper functions in the module."""

    def test_contains_non_english_with_cyrillic(self) -> None:
        """Test _contains_non_english with Cyrillic text."""
        assert _contains_non_english("Привет") is True
        assert _contains_non_english("Hello") is False
        assert _contains_non_english("Hello Мир") is True

    def test_contains_non_english_with_chinese(self) -> None:
        """Test _contains_non_english with Chinese text."""
        assert _contains_non_english("你好") is True
        assert _contains_non_english("Hello 世界") is True

    def test_contains_non_english_with_special_chars(self) -> None:
        """Test _contains_non_english allows special ASCII chars."""
        assert _contains_non_english("$100.00") is False
        assert _contains_non_english("test@example.com") is False
        assert _contains_non_english("path/to/file") is False
        assert _contains_non_english("Hello, World!") is False

    def test_extract_string_value_const(self) -> None:
        """Test _extract_string_value with Const node."""
        code = 'x = "test string"'
        module = astroid.parse(code)
        assign_node = list(module.nodes_of_class(astroid.Assign))[0]
        const_node = assign_node.value
        assert _extract_string_value(const_node) == "test string"

    def test_extract_string_value_non_string(self) -> None:
        """Test _extract_string_value with non-string Const."""
        node = astroid.extract_node("123")
        assert _extract_string_value(node) is None

    def test_truncate_helper(self) -> None:
        """Test the _truncate method."""
        mock_linter = MagicMock()
        checker = EnglishOnlyChecker(mock_linter)

        assert checker._truncate("Short") == "Short"

        long_text = "A" * 100
        truncated = checker._truncate(long_text)
        assert len(truncated) == 50
        assert truncated.endswith("...")
