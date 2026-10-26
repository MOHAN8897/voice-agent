"""Live Premium control/memory calls; no telephony, CRM writes or real caller data."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# name prefix, quantity, acknowledgement, explicit end, unfinished address
UTTERANCES = {
    "te-IN": ("నా పేరు Sai Kiran.", "20 కాదు, 100 కార్డులు కావాలి.", "ఓకే అండి థ్యాంక్ యూ", "అంతే అంతే థ్యాంక్ యూ", "మా అడ్రస్ వచ్చేసి"),
    "hi-IN": ("मेरा नाम Sai Kiran है।", "20 नहीं, 100 कार्ड चाहिए।", "ठीक है धन्यवाद", "बस इतना ही, धन्यवाद", "मेरा पता है"),
    "ta-IN": ("என் பெயர் Sai Kiran.", "20 இல்லை, 100 கார்டுகள் வேண்டும்.", "சரி நன்றி", "அவ்வளவுதான் நன்றி", "என் முகவரி வந்து"),
    "kn-IN": ("ನನ್ನ ಹೆಸರು Sai Kiran.", "20 ಅಲ್ಲ, 100 ಕಾರ್ಡ್ ಬೇಕು.", "ಸರಿ ಧನ್ಯವಾದಗಳು", "ಇಷ್ಟೇ ಸಾಕು ಧನ್ಯವಾದಗಳು", "ನನ್ನ ವಿಳಾಸ ಅಂದರೆ"),
    "ml-IN": ("എന്റെ പേര് Sai Kiran.", "20 അല്ല, 100 കാർഡ് വേണം.", "ശരി നന്ദി", "ഇത്രയേ വേണ്ടൂ, നന്ദി", "എന്റെ വിലാസം എന്നു പറഞ്ഞാൽ"),
    "mr-IN": ("माझे नाव Sai Kiran आहे.", "20 नाही, 100 कार्ड हवे.", "ठीक आहे धन्यवाद", "एवढेच हवे होते, धन्यवाद", "माझा पत्ता म्हणजे"),
    "bn-IN": ("আমার নাম Sai Kiran।", "20 নয়, 100 কার্ড চাই।", "ঠিক আছে ধন্যবাদ", "এইটুকুই দরকার ছিল, ধন্যবাদ", "আমার ঠিকানা হলো"),
    "gu-IN": ("મારું નામ Sai Kiran છે.", "20 નહીં, 100 કાર્ડ જોઈએ.", "ઠીક છે આભાર", "બસ આટલું જ, આભાર", "મારું સરનામું એટલે"),
    "pa-IN": ("ਮੇਰਾ ਨਾਮ Sai Kiran ਹੈ।", "20 ਨਹੀਂ, 100 ਕਾਰਡ ਚਾਹੀਦੇ ਹਨ।", "ਠੀਕ ਹੈ ਧੰਨਵਾਦ", "ਬਸ ਐਨਾ ਹੀ ਚਾਹੀਦਾ ਸੀ, ਧੰਨਵਾਦ", "ਮੇਰਾ ਪਤਾ ਹੈ"),
    "en-IN": ("My name is Sai Kiran.", "Not 20, I need 100 cards.", "Okay, thank you", "That's all I needed, thank you", "My delivery address is"),
    "en-US": ("My name is Sai Kiran.", "Not 20, I need 100 cards.", "Okay, thank you", "That's all I needed, thank you", "My delivery address is"),
}


async def main():
    import pytest
    from server.config.env import Settings, get_settings
    from server.providers.sarvam_llm import SarvamLLMAdapter
    from server import providers
    from server.call.close_classifier import classify_close_turn
    from server.config.constants import constants

    configured = SarvamLLMAdapter()
    adapter = SarvamLLMAdapter(api_key=configured._api_key())
    model = json.loads((ROOT / "data/calls/a60ba6ec-cfd7-45f0-9876-8abd92f7f0e1/meta.json").read_text(encoding="utf-8"))["resolved_stack"]["llm"]["model"]
    languages = list(constants.SUPPORTED_LANGUAGES)
    assert set(languages) == set(UTTERANCES), "Add cases for a newly supported locale"
    Settings.model_config["env_file"] = None
    os.environ.pop("DATABASE_URL", None)
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="premium-control-")
    os.environ["SAAS_AUTH_ENABLED"] = "false"
    get_settings.cache_clear()
    registry = SimpleNamespace(is_provider_enabled=lambda *_: True, is_model_allowed=lambda *_: True,
                               get_llm=lambda *_: adapter)
    results = []
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(providers, "get_provider_registry", lambda: registry)
        for locale in languages:
            name, quantity, ack, end, fragment = UTTERANCES[locale]
            cases = [
                ("name", name, "What is your full name?", {}, False),
                ("quantity_correction", quantity, "How many visiting cards do you need?", {"quantity": "20"}, False),
                ("ack_with_missing_address", ack, "Please give the complete delivery address; I only have the village.", {}, True),
                ("explicit_end_with_unfinished_work", end, "Please give your complete address.", {}, True),
                ("unfinished_address", fragment, "Please give your delivery address.", {}, True),
            ]
            for kind, text, previous, facts, unfinished in cases:
                started = time.monotonic()
                result = await classify_close_turn(transcript=text, agent_previous=previous, language=locale,
                    llm=SimpleNamespace(provider="sarvam", model=model, config={}), extract_memory=True,
                    current_facts=facts, unfinished_request=unfinished)
                operations = (result or {}).get("memory_operations", [])
                if kind == "name":
                    passed = any(op["key"] == "caller_name" and op["value"] == "Sai Kiran" for op in operations)
                elif kind == "quantity_correction":
                    passed = any(op["key"] == "quantity" and op["value"] == "100" for op in operations)
                elif kind == "ack_with_missing_address":
                    passed = result is not None and result.get("decision") != "close" and not result.get("wait_for_caller")
                elif kind == "explicit_end_with_unfinished_work":
                    passed = (result or {}).get("decision") == "close"
                else:
                    passed = (result or {}).get("wait_for_caller") is True and not operations
                row = {"language": locale, "case": kind, "passed": passed, "elapsed_s": round(time.monotonic()-started, 3), "result": result}
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    destination = Path(__file__).with_name("live-control-results.json")
    destination.write_text(json.dumps({"model": model, "scope": "live pinned LLM control and grounded memory; no speech, telephony or external writes", "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = sum(not row["passed"] for row in results)
    print(f"{len(results)-failures}/{len(results)} passed", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
