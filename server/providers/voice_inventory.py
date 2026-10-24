"""Provider-sourced voice inventories. No network access on the call hot path.

The bundled snapshot is generated from vendor documentation, not a UI shortlist.
Refreshable API catalogs supersede it only after a complete successful fetch.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from server.config.constants import constants

SNAPSHOT = Path(__file__).with_name("catalog_data") / "voices.json"
DOCUMENTS = {
    "sarvam": "https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices.md",
    "sarvam-voices": "https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices",
    "sarvam-rest": "https://docs.sarvam.ai/api-reference/text-to-speech/convert.md",
    "gnani": "https://docs.gnani.ai/api/TTS/available-voices.md",
    "gemini": "https://ai.google.dev/gemini-api/docs/speech-generation",
    "cartesia-models": "https://docs.cartesia.ai/build-with-cartesia/tts-models/older-models.md",
}
_cache: dict[str, Any] | None = None
_loaded_path: str | None = None
_loaded_mtime: int | None = None
_voice_indexes: dict[tuple[str, str], tuple[dict[str, Any], tuple[int, ...], dict[str, dict[str, Any]]]] = {}
_refresh_lock = asyncio.Lock()
_LOCALES = {str(meta["name"]).lower(): code for code, meta in constants.SUPPORTED_LANGUAGES.items() if code.endswith("-IN")}
_LOCALES.update(english="en-IN", hinglish="hi-en", odia="od-IN")
_V4_VOICE_ID = re.compile(r"[a-z]+_(as|enhi|en|hi|bn|gu|kn|mr|pa|ta|te)_[a-z_]+$")
# Native persona language carried in the voice id. It is display metadata, not
# a synthesis restriction: v4 maps the requested language_code at request time.
_V4_LANGUAGE = {
    "as": ["as-IN"],
    "enhi": ["hi-IN", "en-IN"],
    "en": ["en-IN"],
    "hi": ["hi-IN"],
    "bn": ["bn-IN"],
    "gu": ["gu-IN"],
    "kn": ["kn-IN"],
    "mr": ["mr-IN"],
    "pa": ["pa-IN"],
    "ta": ["ta-IN"],
    "te": ["te-IN"],
}
# Every target language this platform supports is accepted by v4-flash for
# every persona. The provider rejects only as-IN.
_V4_TARGET_LANGUAGES = tuple(sorted(code for code in constants.SUPPORTED_LANGUAGES if code.endswith("-IN")))
# The Gemini prebuilt voice API omits gender for the 30 featured personas, so
# the tenant voice picker cannot group them without this documented roster.
GEMINI_FEATURED_GENDERS = {
    **{name: "female" for name in (
        "Achernar", "Aoede", "Autonoe", "Callirrhoe", "Despina", "Erinome", "Gacrux",
        "Kore", "Laomedeia", "Leda", "Pulcherrima", "Sulafat", "Vindemiatrix", "Zephyr",
    )},
    **{name: "male" for name in (
        "Achird", "Algenib", "Algieba", "Alnilam", "Charon", "Enceladus", "Fenrir",
        "Iapetus", "Orus", "Puck", "Rasalgethi", "Sadachbia", "Sadaltager", "Schedar",
        "Umbriel", "Zubenelgenubi",
    )},
}


def v4_voice_languages(voice_id: str) -> list[str] | None:
    """The persona's native language(s), encoded in its Bulbul v4 voice id.

    Returns None for ids that are not v4 voice ids, so callers can leave rows alone.
    """
    match = _V4_VOICE_ID.fullmatch(str(voice_id or "").strip().lower())
    return list(_V4_LANGUAGE[match.group(1)]) if match else None


def _repair_v4_rows(data: dict[str, Any]) -> None:
    rows = ((data.get("sarvam") or {}).get("models") or {}).get("bulbul:v4-flash") or []
    for row in rows:
        preferred = v4_voice_languages(str(row.get("id") or ""))
        if preferred is not None:
            row["languages"] = list(_V4_TARGET_LANGUAGES)
            row["preferredLanguages"] = preferred
            row.pop("selectable", None)
            row.pop("unavailableReason", None)


def _row(voice_id: str, languages: list[str], **metadata: Any) -> dict[str, Any]:
    return {"id": voice_id, "providerVoiceId": voice_id, "label": metadata.pop("label", voice_id),
        "languages": sorted(set(languages)), **metadata}


def _gemini_gender(row: dict[str, Any]) -> str:
    """Published gender, falling back to the documented featured-voice roster."""
    return str(row.get("gender") or GEMINI_FEATURED_GENDERS.get(str(row.get("id") or "")) or "")


def parse_document_catalogs(sources: dict[str, str]) -> dict[str, Any]:
    """Parse published vendor tables; refuse incomplete/changed document layouts."""
    locales = sorted(code for code in constants.SUPPORTED_LANGUAGES if code.endswith("-IN"))
    sarvam: dict[str, list[dict[str, Any]]] = {}
    # The markdown page keeps the v4 table, while the rendered page carries the
    # v3 voice cards grouped under Male/Female headings. Parse both so gender
    # and tone stay provider-sourced instead of guessed in the UI.
    rendered = html.unescape(sources.get("sarvam-voices", "")).replace('\\"', '"').replace("\\n", "\n")
    try:
        male_block = rendered.split("## Bulbul v3 Male Voices", 1)[1].split("## Bulbul v3 Female Voices", 1)[0]
        female_block = rendered.split("## Bulbul v3 Female Voices", 1)[1].split("## Bulbul v4 Flash Voices", 1)[0]
    except IndexError as exc:
        raise ValueError("Sarvam voice documentation layout changed") from exc
    male_names = re.findall(r'VoiceCard name="([^"]+)"', male_block)
    female_names = re.findall(r'VoiceCard name="([^"]+)"', female_block)
    if len(male_names) < 20 or len(female_names) < 12:
        raise ValueError("Sarvam gender sections are incomplete")
    sarvam_gender = {name: "male" for name in male_names} | {name: "female" for name in female_names}
    sarvam_tone = {name: tone for name, tone in re.findall(r'VoiceCard name="([^"]+)" tagline="([^"]*)"', rendered)}
    v4 = {}
    for line in sources["sarvam"].splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip("| ").split("|")]
        if len(cells) == 3 and v4_voice_languages(cells[0]) is not None:
            preferred = v4_voice_languages(cells[0]) or []
            metadata = {"label": cells[1], "category": cells[2].replace("_", " "), "preferredLanguages": preferred}
            gender = sarvam_gender.get(cells[0].split("_", 1)[0])
            if gender:
                metadata["gender"] = gender
            tone = sarvam_tone.get(cells[0].split("_", 1)[0])
            if tone:
                metadata["tone"] = tone
            v4[cells[0]] = _row(cells[0], list(_V4_TARGET_LANGUAGES), **metadata)
    if len(v4) < 200:
        raise ValueError("Sarvam catalog table is incomplete")
    sarvam["bulbul:v4-flash"] = list(v4.values())
    rest = sources["sarvam-rest"].split("**Model Compatibility", 1)[1]
    for model, next_marker in (("bulbul:v3", "bulbul:v4-flash"), ("bulbul:v2", "Note:")):
        section = rest.split(f"**{model}:**", 1)[1].split(f"**{next_marker}:**", 1)[0]
        section = section.split("Note:", 1)[0]
        if model == "bulbul:v2":
            female = re.search(r"Female:\s*([a-z ,]+)", section)
            male = re.search(r"Male:\s*([a-z ,]+)", section)
            if not female or not male:
                raise ValueError("Sarvam v2 gender sections changed")
            names = [(name, "female") for name in re.findall(r"\b[a-z]+\b", female.group(1))]
            names += [(name, "male") for name in re.findall(r"\b[a-z]+\b", male.group(1))]
            if len(names) < 7:
                raise ValueError("Sarvam speaker enum changed")
            sarvam[model] = [_row(name, locales, gender=gender) for name, gender in names]
            continue
        documented = re.findall(r"\b[a-z]+\b", re.sub(r"\([^)]*\)|Female:|Male:|\*", "", section))
        if len(documented) < 30:
            raise ValueError("Sarvam speaker enum changed")
        if any(name not in sarvam_gender for name in documented):
            raise ValueError("Sarvam v3 gender table changed")
        sarvam[model] = [
            _row(name, locales, gender=sarvam_gender[name], tone=sarvam_tone.get(name, ""))
            for name in documented
        ]
    gnani = {}
    for model, title in (("timbre-v2.5", "## Timbre v2.5 voices"), ("timbre-v3.0", "## Timbre v3.0 voices")):
        section = sources["gnani"].split(title, 1)[1].split("\n## ", 1)[0]
        rows = []
        for line in section.splitlines():
            cells = [c.strip() for c in line.strip("| ").split("|")]
            if len(cells) != 5 or cells[1] not in {"Female", "Male"}:
                continue
            languages = [_LOCALES[name.strip().lower()] for name in cells[2].split(",") if name.strip().lower() in _LOCALES]
            mapping = {"hi-IN": "hi-en"} if "hi-en" in languages else {}
            if mapping:
                languages = ["hi-IN"]
            rows.append(_row(cells[0], languages, gender=cells[1].lower(), category=cells[3], tone=cells[4], providerLanguageMap=mapping))
        if len(rows) < (42 if model.endswith("2.5") else 13):
            raise ValueError("Gnani voice table is incomplete")
        gnani[model] = rows
    tables = re.findall(r"<table\b.*?</table>", sources["gemini"], re.S)
    voice_table = next(table for table in tables if "Zephyr" in table and "Sulafat" in table)
    cells = re.findall(r"<td\b[^>]*>(.*?)</td>", voice_table, re.S)
    gemini = []
    for cell in cells:
        text = html.unescape(re.sub(r"<[^>]*>", "", cell)).strip()
        name, tone = re.split(r"\s*--\s*", text, maxsplit=1)
        gender = GEMINI_FEATURED_GENDERS.get(name.strip())
        gemini.append(_row(name.strip(), list(constants.SUPPORTED_LANGUAGES), tone=tone.strip(),
            **({"gender": gender} if gender else {})))
    if len(gemini) != 30:
        raise ValueError("Gemini featured voice table changed")
    tts_models = sorted(set(re.findall(r"gemini-[a-z0-9.-]*?tts(?:-preview)?\b", sources["gemini"])))
    cartesia_languages = {}
    for line in sources["cartesia-models"].splitlines():
        cells = [cell.strip().strip("`") for cell in line.strip("| ").split("|")]
        if len(cells) >= 4 and re.fullmatch(r"sonic-[\d.]+-\d{4}-\d{2}-\d{2}", cells[0]):
            codes = cells[2].split(", ")
            languages = [locale for locale in locales if locale.split("-")[0] in codes]
            cartesia_languages[cells[0]] = languages
            cartesia_languages.setdefault(re.sub(r"-\d{4}-\d{2}-\d{2}$", "", cells[0]), languages)
    if "sonic-3.5" not in cartesia_languages:
        raise ValueError("Cartesia model language table changed")
    return {"sarvam": {"models": sarvam}, "gnani": {"models": gnani}, "gemini": {"featured": gemini, "ttsModels": tts_models},
        "cartesia": {"modelLanguages": cartesia_languages}}


def _cache_path() -> Path:
    from server.config.env import get_settings

    return Path(get_settings().data_dir) / "provider_voice_inventory.json"


def inventory() -> dict[str, Any]:
    global _cache, _loaded_path, _loaded_mtime
    path = _cache_path()
    mtime = path.stat().st_mtime_ns if path.exists() else None
    if _cache is None or _loaded_path != str(path) or _loaded_mtime != mtime:
        _cache = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved.get("schemaVersion") == 1:
                    _cache.update(saved)
            except (OSError, ValueError):
                pass
        _loaded_path = str(path)
        _loaded_mtime = mtime
        _repair_v4_rows(_cache)
    return _cache


def default_voice(provider: str, model: str, language: str | None = None, preferred: str | None = None) -> str:
    """First catalog voice valid for the model/language, honoring a configured preference."""
    normalized = language
    if provider in {"sarvam", "gnani"} and normalized in {"en-US", "en-GB"}:
        normalized = "en-IN"
    candidates = voices_for_model(provider, model)
    if normalized:
        candidates = [row for row in candidates if normalized in row.get("languages", [])]
    if not candidates:
        scope = f" for {language}" if language else ""
        raise ValueError(f"No {provider} voice is published for {model}{scope}")
    if preferred:
        for row in candidates:
            if str(row["providerVoiceId"]).casefold() == str(preferred).casefold():
                return str(row["providerVoiceId"])
    # v4 personas can speak every supported language, so a plain first-row
    # fallback would choose an unrelated native language. Prefer a persona
    # native to the requested language, then the provider's own default.
    native = [row for row in candidates if normalized in (row.get("preferredLanguages") or [])]
    if native:
        return str(native[0]["providerVoiceId"])
    if provider == "sarvam" and model == "bulbul:v4-flash":
        for row in candidates:
            if row["providerVoiceId"] == "shubh_enhi_ads":
                return "shubh_enhi_ads"
    return str(candidates[0]["providerVoiceId"])


def voices_for_model(provider: str, model: str) -> list[dict[str, Any]]:
    entry = inventory().get(provider, {})
    if provider == "gemini":
        from server.realtime.models import is_gemini_live_voice_model

        if not (is_gemini_live_voice_model(model) or model in entry.get("ttsModels", [])):
            return []
        # Extended library belongs to the 3.8 speech family, not legacy previews.
        featured = {row["id"].casefold(): row for row in entry.get("featured", [])}
        if model.startswith("gemini-3.8-"):
            for row in entry.get("voices") or []:
                key = row["id"].casefold()
                if key in featured:
                    # Featured voices are multilingual. The API locale describes
                    # their native accent, not a restriction on their languages.
                    base = featured[key]
                    featured[key] = {**base, **row, "id": base["id"], "providerVoiceId": base["providerVoiceId"],
                        "languages": base["languages"], "preferredLanguages": row["languages"]}
                else:
                    featured[key] = row
        rows = copy.deepcopy(list(featured.values()))
        for row in rows:
            row["gender"] = _gemini_gender(row)
        return rows
    if provider == "cartesia":
        if model not in constants.CARTESIA_TTS_MODELS:
            return []
        supported = set(entry.get("modelLanguages", {}).get(model) or [])
        rows = [{**row, "languages": sorted(set(row["languages"]) & supported)} for row in entry.get("voices") or []]
        return copy.deepcopy([row for row in rows if row["languages"]])
    return copy.deepcopy((entry.get("models") or {}).get(model) or [])


def validate_voice(provider: str, model: str, voice_id: str, language: str | None = None) -> dict[str, Any]:
    source = inventory()
    entry = source.get(provider, {})
    signature = tuple(id(value) for value in (entry, entry.get("voices"), entry.get("featured"), (entry.get("models") or {}).get(model)))
    key = (provider, model)
    cached = _voice_indexes.get(key)
    if cached is None or cached[0] is not source or cached[1] != signature:
        index = {row["providerVoiceId"]: row for row in voices_for_model(provider, model)}
        _voice_indexes[key] = (source, signature, index)
    else:
        index = cached[2]
    voice = index.get(voice_id)
    if voice is None:
        raise ValueError("The voice is absent from the selected model's current catalog")
    if provider in {"sarvam", "gnani"} and language in {"en-US", "en-GB"}:
        language = "en-IN"
    if language and language not in voice["languages"]:
        raise ValueError("The voice does not match the selected language")
    return copy.deepcopy(voice)


def profile_voice_rows(provider: str, model: str, languages: list[str], previous: list[dict[str, Any]] | None = None, *, include_unavailable: bool = False) -> list[dict[str, Any]]:
    existing = {row.get("providerVoiceId"): row for row in previous or []}
    result = []
    for row in voices_for_model(provider, model):
        supported = sorted(set(row["languages"]) & set(languages))
        if not supported and not include_unavailable:
            continue
        old = existing.get(row["providerVoiceId"], {})
        key = hashlib.sha256(f"{provider}:{model}:{row['providerVoiceId']}".encode()).hexdigest()[:24]
        result.append({**row, "id": old.get("id") or f"voice-{key}", "languages": supported})
    return result


async def _sarvam_api_voices(client: httpx.AsyncClient, key: str, previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read the live v4 speaker enum from a deliberately rejected request.

    Sarvam has no public list-voices endpoint. Its documented 400 response for
    an invalid speaker lists the full model inventory. This request cannot
    synthesize: the speaker is intentionally outside its persona-id grammar.
    """
    response = await client.post("https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": key}, json={"model": "bulbul:v4-flash",
        "speaker": "__catalog_discovery_invalid__", "text": "Voice catalogue validation.",
        "language_code": "en-IN"})
    if response.status_code != 400:
        response.raise_for_status()
        raise ValueError("The voice inventory validation request was not rejected")
    body = response.json()
    error = body.get("error") if isinstance(body, dict) else None
    message = str(error.get("message") or "") if isinstance(error, dict) else ""
    marker = "Available speakers for bulbul:v4-flash are:"
    if marker not in message:
        raise ValueError("The voice inventory response did not contain a complete speaker enum")
    names = [name.strip() for name in message.split(marker, 1)[1].strip().rstrip(".").split(",")]
    if len(names) < 200 or len(names) != len(set(names)) or any(not _V4_VOICE_ID.fullmatch(name) for name in names):
        raise ValueError("The voice inventory speaker enum was incomplete or changed format")
    known = {row["providerVoiceId"]: row for row in previous}
    # Preserve the documented display order and numbered tenant identities when
    # the live API returns the same speakers in a different order.
    available = set(names)
    ordered_names = [name for name in known if name in available] + [name for name in names if name not in known]
    rows = []
    for name in ordered_names:
        preferred = v4_voice_languages(name) or []
        row = copy.deepcopy(known.get(name)) or _row(
            name, list(_V4_TARGET_LANGUAGES),
            category=name.split("_", 2)[2].replace("_", " "), preferredLanguages=preferred,
        )
        row["languages"] = list(_V4_TARGET_LANGUAGES)
        row["preferredLanguages"] = preferred
        row.pop("selectable", None)
        row.pop("unavailableReason", None)
        rows.append(row)
    return rows


def normalize_cartesia_voice(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not raw.get("id") or raw.get("status", "active") != "active" or raw.get("access") == "private":
        return None
    locales = {str(a.get("locale") or "").replace("_", "-") for a in raw.get("accents", []) if isinstance(a, dict)}
    languages = {code for code in locales if code.endswith("-IN") and code in constants.SUPPORTED_LANGUAGES}
    primary = str(raw.get("language") or "").replace("_", "-")
    if primary in constants.SUPPORTED_LANGUAGES and primary.endswith("-IN"):
        languages.add(primary)
    if f"{primary}-IN" in constants.SUPPORTED_LANGUAGES and (primary != "en" or raw.get("country") == "IN"):
        languages.add(f"{primary}-IN")
    if not languages:
        return None
    return _row(str(raw["id"]), sorted(languages), label=str(raw.get("name") or raw["id"]),
        gender={"feminine": "female", "masculine": "male", "gender_neutral": "neutral"}.get(raw.get("gender"), ""),
        category=str(raw.get("category") or ""), tone=str(raw.get("tagline") or ""), accent="Indian")


async def _api_voices(client: httpx.AsyncClient, provider: str, key: str) -> list[dict[str, Any]]:
    url = "https://api.cartesia.ai/voices" if provider == "cartesia" else "https://generativelanguage.googleapis.com/v1beta/voices"
    headers = ({"Authorization": f"Bearer {key}", "Cartesia-Version": constants.CARTESIA_API_VERSION} if provider == "cartesia" else {"x-goog-api-key": key})
    rows, seen, cursor = [], set(), None
    cursors = set()
    for _ in range(100):
        params = {"limit": 100} if provider == "cartesia" else {"page_size": 100, "type": "prebuilt"}
        if cursor:
            params["starting_after" if provider == "cartesia" else "page_token"] = cursor
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        body = response.json()
        items = body.get("data" if provider == "cartesia" else "voices")
        if not isinstance(items, list):
            raise ValueError("Invalid voice catalog response")
        for raw in items:
            if provider == "cartesia":
                row = normalize_cartesia_voice(raw)
            else:
                if raw.get("type") != "prebuilt":
                    continue  # Custom project voices are not a shared tenant catalog.
                voice_id = str(raw.get("id") or "")
                language = raw.get("language_code") or raw.get("languageCode")
                languages = [language] if language else list(constants.SUPPORTED_LANGUAGES)
                languages = [code for code in languages if str(code).endswith("-IN")]
                if voice_id and languages:
                    row = _row(voice_id, languages,
                        label=raw.get("display_name") or raw.get("displayName") or voice_id,
                        category=raw.get("context") or raw.get("persona") or "", gender=raw.get("gender") or "", tone=raw.get("description") or "")
                else:
                    row = None
            if row and row["id"] not in seen:
                seen.add(row["id"])
                rows.append(row)
        if provider == "cartesia":
            cursor = (body.get("next_page") or (items[-1].get("id") if items else None)) if body.get("has_more") else None
            if body.get("has_more") and not cursor:
                raise ValueError("Voice catalog pagination is incomplete")
        else:
            cursor = body.get("next_page_token") or body.get("nextPageToken")
        if not cursor:
            return rows
        if cursor in cursors:
            raise ValueError("Voice catalog pagination repeated")
        cursors.add(cursor)
    raise ValueError("Voice catalog pagination did not complete")


async def refresh_inventory() -> dict[str, Any]:
    global _cache, _loaded_path, _loaded_mtime
    from server.config.env import get_settings
    from server.services.dev_secrets_store import dev_secrets_store

    async with _refresh_lock:
        updated = copy.deepcopy(inventory())
        errors = []
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            try:
                responses = await asyncio.gather(*(client.get(url) for url in DOCUMENTS.values()))
                for response in responses:
                    response.raise_for_status()
                docs = parse_document_catalogs(dict(zip(DOCUMENTS, (r.text for r in responses))))
                for provider, entry in docs.items():
                    updated[provider] = {**updated.get(provider, {}), **entry}
            except (httpx.HTTPError, ValueError, AssertionError, IndexError, StopIteration):
                errors.append("Published voice documentation could not be refreshed; the verified snapshot was retained.")
            for provider in ("sarvam", "gemini", "cartesia"):
                key = dev_secrets_store.effective_secret(f"{provider}_api_key") or getattr(get_settings(), f"{provider}_api_key", "")
                if not key:
                    continue
                try:
                    if provider == "sarvam":
                        models = updated.setdefault(provider, {}).setdefault("models", {})
                        rows = await _sarvam_api_voices(client, key, models.get("bulbul:v4-flash") or [])
                        models["bulbul:v4-flash"] = rows
                    else:
                        rows = await _api_voices(client, provider, key)
                        updated.setdefault(provider, {})["voices"] = rows
                except (httpx.HTTPError, ValueError, TypeError):
                    errors.append(f"{provider} voice API could not be refreshed; the last verified inventory was retained.")
        updated["schemaVersion"] = 1
        updated["checkedAt"] = datetime.now(timezone.utc).isoformat()
        updated["sources"] = DOCUMENTS
        path = _cache_path()
        await asyncio.to_thread(_persist, path, updated)
        _cache = updated
        _loaded_path = str(path)
        _loaded_mtime = path.stat().st_mtime_ns if path.exists() else None
        return {"checkedAt": updated["checkedAt"], "errors": errors}


def _persist(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def provider_language(provider: str, model: str, voice_id: str, language: str) -> str:
    """Translate an application locale only when the supplier documents an alias."""
    voice = validate_voice(provider, model, voice_id, None if language == "auto" else language)
    return voice.get("providerLanguageMap", {}).get(language, language)
