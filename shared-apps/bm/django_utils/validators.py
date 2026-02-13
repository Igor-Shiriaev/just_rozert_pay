from typing import Dict, Any, List, Callable

from django.core.exceptions import ValidationError


def validate_translations_field(
    languages: List[str],
    required_languages: List[str] = None
) -> Callable[[Dict], None]:
    required_languages = required_languages or []

    def validator(data: Dict) -> None:
        if not data:
            return None
        _required_languages = list(required_languages)  # type: ignore
        for lang, value in data.items():
            if lang not in languages:
                raise ValidationError(f'Unknown language {lang}')
            if lang in _required_languages:
                _required_languages.remove(lang)
                if not value:
                    raise ValidationError(
                        f'Field doesn\'t have translation to required language "{lang}"'
                    )
        if _required_languages:
            raise ValidationError(
                f'Field doesn\'t have translation to required languages {_required_languages}'
            )
    return validator


def validate_not_empty_required(value: Any) -> None:    # type: ignore
    if not value:
        raise ValidationError('Required field')
