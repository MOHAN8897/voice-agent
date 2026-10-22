"""Deterministic checks for language coherence in the rendered instruction set.
These checks reject known contradictions; conversation evaluations are still
required for semantic conflicts and natural phrasing.
"""
from __future__ import annotations
import re
from server.config.constants import constants, normalize_supported_language

_LANGUAGE_NAMES = {entry['name'].split(' (')[0].lower(): locale for locale, entry in constants.SUPPORTED_LANGUAGES.items()}
_LANGUAGE_NAMES.update({'english': 'en', 'hinglish': 'hi-IN', 'bangla': 'bn-IN'})
_NAMES = '|'.join(sorted(map(re.escape, _LANGUAGE_NAMES), key=len, reverse=True))
_POSITIVE = re.compile(r'\b(?:speak|reply|respond|stay|communicate)(?:\s+(?:must|always|only|in|natural|exclusively|strictly|using|entirely|this way:)){0,5}\s+('+_NAMES+r'|[a-z]{2}-[a-z]{2})\b', re.I)
_METADATA = re.compile(r'(?:@language:\s*|---\s*SPOKEN LANGUAGE\s*\(|(?:^|\n)Language:\s*)([a-z]{2}(?:-[a-z]{2})?)', re.I)

def validate_rendered_brain(compiled: str, language: str | None) -> list[str]:
    text=(compiled or '').strip()
    if not text:return ['Compiled brain is empty']
    lang=normalize_supported_language(language or 'te-IN')
    if lang not in constants.SUPPORTED_LANGUAGES:return [f'No spoken language pack for locale {language}']
    issues=[];evidence=False
    for match in _METADATA.finditer(text):
        tagged=normalize_supported_language(match.group(1))
        if tagged != lang:issues.append(f'Language marker {tagged} does not match session language {lang}')
        else:evidence=True
    for match in _POSITIVE.finditer(text):
        # Negative language-switch prohibitions are not positive speaking directives.
        prefix=text[max(0,match.start()-32):match.start()]
        clause=re.split(r'[.\n;:]',prefix)[-1]
        if re.search(r'\b(?:never|not|don\x27t|cannot)\s+(?:ever\s+)?$',clause,re.I):continue
        raw=match.group(1).lower()
        directive=_LANGUAGE_NAMES.get(raw) or normalize_supported_language(raw)
        if directive==lang or (directive=='en' and lang.startswith('en-')):evidence=True
        else:issues.append(f'Conflicting language instruction: {match.group(0)!r} in {lang} session')
    if not evidence:issues.append(f'Assembled brain missing selected-language declaration for {lang}')
    if re.search(r'never switch your spoken language',text,re.I) and re.search(r'reply in .+ from now on',text,re.I):
        issues.append('Conflicting fixed-language and language-switch instructions')
    return list(dict.fromkeys(issues))

def assert_rendered_brain_valid(compiled: str, language: str | None) -> None:
    issues=validate_rendered_brain(compiled,language)
    if issues:
        from server.services.pstn_stack import PstnStackValidationError
        raise PstnStackValidationError('Brain language validation failed',details=issues)
