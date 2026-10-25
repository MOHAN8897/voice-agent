"""Deterministic contradiction checks for the rendered instruction set.

Catches known platform-ownership conflicts — wrong locale pack, duplicate close
policy, model-owned farewell, conflicting language rules — before a call is
admitted or an artifact is published. Conversation evaluations are still
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
_CALL_END_HEADER = re.compile(r'(?im)^\s*---\s*CALL END POLICY\s*---\s*$')
# A locale code inside a "language pack" clause names the pack the model is told to use.
_LANGUAGE_PACK_CLAUSE = re.compile(r'[^\n]{0,80}\blanguage\s+pack\b[^\n]{0,80}', re.I)
_LOCALE_CODE = re.compile(r'\b([a-z]{2}-[a-z]{2})\b', re.I)
# Positive instruction to produce the farewell. The platform owns it, so any
# imperative here is a contradiction; negations and "the platform speaks it"
# statements are not.
_FAREWELL_DIRECTIVE = re.compile(
    r'\b(?:say|speak|tell|offer|deliver|give|send|use|include|close\s+with|end\s+with|finish\s+with)\b'
    r'[^\n.;]{0,60}?\b(?:goodbye|good\s+bye|farewell|sign[- ]?off)\b'
    r'|\b(?:confirm|thank)\b[^\n.;]{0,40}?\bfarewell\b[^\n.;]{0,20}?\bclose\b',
    re.I,
)
_NEGATED_OR_DELEGATED = re.compile(
    r'(?:\bnever|\bnot\b|\bdon\x27t\b|\bdo\s+not\b|\bcannot\b|\bcan\x27t\b|\bwithout\b|\bmust\s+not\b)'
    r'[\s\w,]{0,24}$|(?:\bplatform|\bserver|\bsystem|\bpolicy)\s+$',
    re.I,
)

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
    for clause in _LANGUAGE_PACK_CLAUSE.finditer(text):
        line_start=text.rfind('\n', 0, clause.start()) + 1
        line_end=text.find('\n', clause.end())
        line=text[line_start: line_end if line_end >= 0 else len(text)]
        if line.lstrip().startswith('@'):
            # Entity-tag metadata is bookkeeping, not a speaking directive.
            continue
        for match in _LOCALE_CODE.finditer(clause.group(0)):
            tagged=normalize_supported_language(match.group(1))
            if tagged != lang:
                issues.append(f'Language pack {tagged} does not match session language {lang}')
    headers=_CALL_END_HEADER.findall(text)
    if len(headers) > 1:
        issues.append(f'Duplicate CALL END POLICY sections: {len(headers)} found; exactly one may own the close')
    for match in _FAREWELL_DIRECTIVE.finditer(text):
        prefix=text[max(0,match.start()-48):match.start()]
        if _NEGATED_OR_DELEGATED.search(prefix):
            continue
        if re.search(r'\b(?:platform|server|system)\b', match.group(0), re.I):
            # "Use the platform's farewell" delegates ownership instead of claiming it.
            continue
        issues.append('Model-owned farewell directive: the platform owns the farewell and disconnect')
    return list(dict.fromkeys(issues))

def assert_rendered_brain_valid(compiled: str, language: str | None) -> None:
    issues=validate_rendered_brain(compiled,language)
    if issues:
        from server.services.pstn_stack import PstnStackValidationError
        raise PstnStackValidationError('Brain language validation failed',details=issues)
