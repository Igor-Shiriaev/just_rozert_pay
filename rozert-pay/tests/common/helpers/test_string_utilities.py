import re
import typing as ty

from rozert_pay.common.helpers.string_utils import string_matches


def test_string_matches_exact_match():
    """Тест на точное совпадение строки."""
    assert string_matches("test", "test") is True
    assert string_matches("test", "other") is False


def test_string_matches_pattern():
    """Тест на совпадение с регулярным выражением."""
    pattern = re.compile(r"test\d+")
    assert string_matches("test123", pattern) is True
    assert string_matches("test", pattern) is False
    assert string_matches("asdasd test123 dfasdasd", pattern) is True


def test_string_matches_list_of_strings():
    """Тест на совпадение со списком строк."""
    patterns = ["test1", "test2", "test3"]
    assert string_matches("test1", patterns) is True
    assert string_matches("test2", patterns) is True
    assert string_matches("other", patterns) is False


def test_string_matches_list_of_patterns():
    """Тест на совпадение со списком регулярных выражений."""
    patterns = [re.compile(r"test\d+"), re.compile(r"other\d+")]
    assert string_matches("test123", patterns) is True
    assert string_matches("other456", patterns) is True
    assert string_matches("test", patterns) is False


def test_string_matches_mixed_patterns():
    """Тест на совпадение со смешанным списком строк и регулярных выражений."""
    patterns: list[str | ty.Pattern[str]] = ["test1", re.compile(r"other\d+")]
    assert string_matches("test1", patterns) is True
    assert string_matches("other123", patterns) is True
    assert string_matches("test2", patterns) is False


def test_string_matches_empty_list():
    """Тест на пустой список паттернов."""
    assert string_matches("test", []) is False


def test_string_matches_none_value():
    """Тест на None значение."""
    assert not string_matches(None, "test")  # type: ignore
