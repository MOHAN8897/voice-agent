"""Exercise every supported locale through opening, compile and live render paths."""
import re

import pytest

from server.brain.agent_spec import AgentSpec, Evidenced
from server.brain.agent_spec_script_builder import _opening_for_spec
from server.brain.agent_script_compiler import build_opening_line
from server.brain.compiled_brain_artifact import assemble_unified_brain
from server.prompts import agent_voice_rules as rules
from server.realtime.voice_instructions import build_realtime_voice_instructions
from server.prompts.voice_defaults import canonical_language, default_style_for, style_for_language
from server.config.constants import Constants

LOCALES = tuple(rules.SPOKEN_PACKS)


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('direction', ['inbound', 'outbound'])
@pytest.mark.parametrize('company,scope', [('', ''), ('Acme', ''), ('Acme', 'service'), ('', 'service')])
def test_every_opening_branch_has_a_locale_template(locale, direction, company, scope):
    opening = rules.opening_line_for(locale, agent_name='Sam', company_name=company,
                                     work_scope=scope, direction=direction)
    assert 'Sam' in opening
    assert '{' not in opening


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('direction', ['inbound', 'outbound'])
def test_spec_builder_uses_selected_locale(locale, direction):
    spec = AgentSpec(language_code=locale, agent_name=Evidenced(value='Sam'),
                     company_name=Evidenced(value='Acme'))
    assert _opening_for_spec(spec, locale, direction) == rules.opening_line_for(
        locale, agent_name='Sam', company_name='Acme', work_scope='', direction=direction)


@pytest.mark.parametrize('locale', LOCALES)
def test_legacy_writer_accepts_every_supported_locale(locale):
    prompt = rules.script_writer_system(language=locale, budget_tokens=2000)
    assert f'selected language {locale}' in prompt


@pytest.mark.parametrize('locale', ['ta-IN', 'kn-IN', 'ml-IN', 'mr-IN', 'bn-IN', 'gu-IN', 'pa-IN'])
@pytest.mark.parametrize('direction', ['inbound', 'outbound'])
def test_personal_opening_does_not_fall_back_to_hindi_or_telugu(locale, direction):
    line = build_opening_line(agent_name='Sam', company_name='', work_scope='',
                              language=locale, direction=direction, callee_name='Morgan', is_test=True)
    expected = rules.opening_line_for(locale, agent_name='Sam', company_name='',
                                       work_scope='', direction=direction)
    assert expected in line
    assert 'Morgan' in line
    assert 'main Sam bol rahi hoon' not in line
    assert 'Nenu ela sahayam' not in line


@pytest.mark.parametrize('locale', LOCALES)
@pytest.mark.parametrize('model', ['gemini-3.8-live', 'gpt-realtime-2.1-mini'])
@pytest.mark.parametrize('unified', [True, False])
def test_live_rules_do_not_contradict_language_or_truthfulness(locale, model, unified):
    script = '--- AGENT IDENTITY ---\nYou are Sam from Acme.\n--- COMPANY & OFFER ---\nAnswer service questions.'
    brain = assemble_unified_brain(language=locale, script=script) if unified else script
    prompt = build_realtime_voice_instructions(brain, model=model, language=locale, direction='outbound')
    assert 'Never insert Tamil' not in prompt
    assert 'Never say you are an AI' not in prompt
    assert 'garbled or an unsupported language' not in prompt
    assert 'If the caller speaks a different language: (1)' not in prompt
    assert 'only after a successful tool result' in prompt
    assert 'end_call' in prompt
    assert 'dialed' in prompt
    if unified:
        packs = re.findall(r'--- SPOKEN LANGUAGE \(([^)]+)\) ---', prompt, re.I)
        assert [pack.lower() for pack in packs] == [locale.lower()]


def test_retired_british_pack_resolves_to_supported_english():
    assert 'en-GB' not in rules.SPOKEN_PACKS
    assert rules.normalize_compile_language('en-GB') == 'en-IN'
    assert rules.is_native_english('en-GB') is False
    assert '--- SPOKEN LANGUAGE (en-GB) ---' not in rules.spoken_pack_for('en-GB')


def test_language_footer_does_not_reject_understood_code_switching():
    for locale in LOCALES:
        footer = rules.language_runtime_footer(locale, 'natural')
        assert 'Only if a language barrier prevents understanding' in footer
        assert 'how can I help' not in rules.unclear_fallback_for(locale)


@pytest.mark.parametrize('locale', LOCALES)
def test_default_style_and_footer_never_select_another_language(locale):
    assert canonical_language(locale.lower().replace('-', '_')) == locale
    style = default_style_for(locale)
    if not locale.startswith('en-') and locale != 'hi-IN':
        assert Constants.SUPPORTED_LANGUAGES[locale]['name'] in style
    if locale != 'te-IN':
        assert style_for_language('spoken Telugu', locale) == style
    brain = assemble_unified_brain(language=locale, script='Answer service questions.')
    assert f'Language: {locale}. Style: {style}.' in brain
    if locale != 'te-IN':
        assert 'spoken Telugu' not in brain


def test_advertised_languages_match_test_matrix():
    assert set(LOCALES) == set(Constants.SUPPORTED_LANGUAGES)


@pytest.mark.parametrize('locale', LOCALES)
def test_gemini_retains_complete_mandatory_policy_when_budget_is_tight(locale):
    from server.prompts.brain_prompt import SECTION_SAFETY
    from server.brain.sections import STATIC_OUTPUT_RULES
    from server.realtime.gemini_audio_session import GEMINI_TURN_STYLE, build_gemini_audio_session_instructions
    from server.services.voice_pipeline_limits import LIVE_REPLY_BREVITY_RULE

    brain = assemble_unified_brain(language=locale, script='--- AGENT IDENTITY ---\nYou are Sam from Acme.')
    prompt = build_gemini_audio_session_instructions(brain, language=locale, direction='outbound', token_budget=2500)
    assert SECTION_SAFETY in prompt
    # Gemini intentionally replaces character plumbing with native-audio turn
    # delivery. Every other static obligation must survive that adaptation.
    expected_policy = STATIC_OUTPUT_RULES.replace(LIVE_REPLY_BREVITY_RULE, GEMINI_TURN_STYLE)
    assert expected_policy in prompt
    assert rules.call_end_policy_section(locale) in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize('locale', LOCALES)
async def test_brief_to_live_prompt_keeps_language_facts_and_truthfulness(locale):
    from server.brain.agent_script_compiler import compile_agent_from_brief

    compiled, result, *_ = await compile_agent_from_brief(
        brief='Agent name: Sam. Company name: Acme Services. Answer equipment service questions. Inspection costs INR 500.',
        language=locale, interpret_brief=False, use_llm=False, direction='inbound')
    assert result.company_name == 'Acme Services'
    for model in ('gemini-3.8-live', 'gpt-realtime-2.1-mini'):
        prompt = build_realtime_voice_instructions(compiled, language=locale, model=model, direction='inbound')
        assert f'SPOKEN LANGUAGE ({locale})'.lower() in prompt.lower()
        assert 'Never say you are an AI' not in prompt
        assert 'Acme Services' in prompt
        if locale != 'te-IN':
            assert 'spoken Telugu' not in prompt
