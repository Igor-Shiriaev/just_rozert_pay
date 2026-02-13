from collections import ChainMap

from typing import Any, Collection, Iterable, Mapping, Optional


def get_supported_language(
    language: str,
    supported_languages: Collection[str],
    default: Optional[str] = None,
    allow_fallback_to_base_language: bool = True,
    allow_fallback_to_other_regional_language: bool = False
) -> str:
    """
    Returns the specified language or the most suitable replacement of supported ones.
    Raises the LookupError if no replacement is found.
    """
    if language in supported_languages:
        return language

    base_language = language.split('-')[0]

    if allow_fallback_to_base_language:
        # If 'pt-br' is not supported, try just base language 'pt'.
        if base_language in supported_languages:
            return base_language

    if allow_fallback_to_other_regional_language:
        # if pt-pt is not supported, try pt-br.
        for supported_language in supported_languages:
            if supported_language.startswith(base_language + '-'):
                return supported_language

    if default is not None:
        return default

    raise LookupError(language)


MISSING = object()

Translation = Mapping[str, Any]     # type: ignore


def get_translation(        # type: ignore
    language: str,
    translations: Translation,
    default: Any = MISSING,
    fallback_language: str = 'en',
    allow_fallback_to_base_language: bool = True,
    allow_fallback_to_other_regional_language: bool = False
) -> Any:
    """
    Returns translation for specified language from specified translations.
    If `allow_fallback_to_base_language` is set and language like pt-br is not found in `translation`,
    then we will try the base language pt.
    If `allow_fallback_to_other_regional_language` is set and language like pt is not found in
    `translation`, then we will return the first match with pt-. This has lowest priority.
    """
    try:
        return translations[get_supported_language(
            language=language,
            supported_languages=translations.keys(),
            allow_fallback_to_base_language=allow_fallback_to_base_language,
            allow_fallback_to_other_regional_language=allow_fallback_to_other_regional_language
        )]
    except LookupError:
        if fallback_language in translations:
            return translations[fallback_language]

    if default is not MISSING:
        return default

    raise LookupError(language)


def get_chain_translation(      # type: ignore
    language: str,
    translations_chain: Iterable[Translation],
    default: Any = MISSING,
    fallback_language: str = 'en',
    allow_fallback_to_base_language: bool = True,
    allow_fallback_to_other_regional_language: bool = False
) -> Any:
    """
    Returns translation for specified language from specified translations.
    Here translations are chained, so if no translation is found in the first mapping,
    we try to find a translation in the next one.
    Raises the LookupError if no translation is found.
    """
    return get_translation(
        language=language,
        translations=ChainMap(*translations_chain),         # type: ignore[arg-type]
        default=default,
        fallback_language=fallback_language,
        allow_fallback_to_base_language=allow_fallback_to_base_language,
        allow_fallback_to_other_regional_language=allow_fallback_to_other_regional_language
    )
