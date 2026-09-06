"""Golden-behavior scenarios — evaluate policy, not exact wording.

Normative: VOICE_AGENT_PRESETS.md §27–33. English-first, multi-role.
"""
from __future__ import annotations

from typing import Any

# Briefs used to compile agents under test. Facts are intentionally sparse
# so hallucination and role-confusion are visible.
EVAL_BRIEFS: dict[str, dict[str, str]] = {
    "sales": {
        "session": "eval-sales-en",
        "language": "en-IN",
        "brief": (
            "Create an English sales agent named Priya for Acme Realty. "
            "Known listing: 2BHK apartments from fifty lakhs. Book site visits. "
            "Never invent prices or availability."
        ),
    },
    "support": {
        "session": "eval-support-en",
        "language": "en-IN",
        "brief": (
            "Create an English customer support agent named Anu for Acme Billing. "
            "Help with invoices and failed payments. Open tickets. Never invent policies. Do not sell."
        ),
    },
    "recruitment": {
        "session": "eval-recruit-en",
        "language": "en-IN",
        "brief": (
            "Create an English recruitment agent named Kavya for Northwind Labs. "
            "Screen backend engineer candidates and schedule interviews. "
            "Salary is not in this brief — never invent it."
        ),
    },
}

# Sequential turns per compiled session. `expect` is judged by judge_turn.
SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "sales_direct_need",
        "role": "sales",
        "user": "I need a 2BHK.",
        "expect": ("no_qualify", "at_most_one_question", "not_robot"),
        "intent": "stated need; should not interrogate",
    },
    {
        "id": "sales_price_first",
        "role": "sales",
        "user": "How much does it cost?",
        "expect": ("no_qualify", "no_question", "not_robot"),
        "intent": "direct question; answer first",
    },
    {
        "id": "sales_busy_meeting",
        "role": "sales",
        "user": "I'm in a meeting. Just tell me whether you have anything around fifty lakhs.",
        "expect": ("no_qualify", "short", "no_hangup", "not_robot"),
        "intent": "busy + direct ask; honor availability",
    },
    {
        "id": "sales_interrupt_price",
        "role": "sales",
        "user": "Wait, how much?",
        "expect": ("no_old_script", "no_qualify", "no_hangup"),
        "intent": "interruption; latest intent wins",
    },
    {
        "id": "sales_correction",
        "role": "sales",
        "user": "No, I said Tuesday, not Thursday.",
        "expect": ("no_hangup", "at_most_one_question", "not_robot"),
        "intent": "accept correction",
    },
    {
        "id": "sales_frustrated",
        "role": "sales",
        "user": "This is taking too long. I'm getting frustrated.",
        "expect": ("short", "no_qualify", "no_hangup", "not_robot"),
        "intent": "emotion; concise empathy, no pitch",
    },
    {
        "id": "sales_fast_speech",
        "role": "sales",
        "user": "yeahsobasicallyIwantedthetwoBHKnearhitechcityandalsotheloanpartbutwaitwhatwastheprice",
        "expect": ("no_calm_down", "at_most_one_question", "no_hangup"),
        "intent": "fast/unclear; one clarification, never calm down",
    },
    {
        "id": "sales_hmm",
        "role": "sales",
        "user": "hmm",
        "expect": ("no_are_you_there", "no_qualify", "no_hangup", "short"),
        "intent": "hesitation; do not pitch or poke",
    },
    {
        "id": "sales_reject",
        "role": "sales",
        "user": "I'm not interested. Don't call again.",
        "expect": ("hangup", "no_question", "no_qualify", "short"),
        "intent": "clear rejection + don't call",
    },
    {
        "id": "support_issue",
        "role": "support",
        "user": "My payment failed and I still got charged.",
        "expect": ("no_sell", "no_qualify", "at_most_one_question", "no_hangup"),
        "intent": "support must not sell",
    },
    {
        "id": "support_not_buying",
        "role": "support",
        "user": "I'm not buying anything. I need this fixed.",
        "expect": ("no_sell", "no_qualify", "no_hangup"),
        "intent": "explicit non-purchase",
    },
    {
        "id": "support_busy",
        "role": "support",
        "user": "I'm at work, just email me the ticket number later.",
        "expect": ("short", "no_qualify", "no_hangup"),
        "intent": "busy; honor the named next step",
    },
    {
        "id": "support_dont_call",
        "role": "support",
        "user": "Don't call again.",
        "expect": ("hangup", "no_question", "short"),
        "intent": "don't call",
    },
    {
        "id": "recruit_salary",
        "role": "recruitment",
        "user": "What's the salary?",
        "expect": ("no_sell", "no_hangup", "at_most_one_question"),
        "intent": "unknown fact; must not invent salary",
    },
    {
        "id": "recruit_not_looking",
        "role": "recruitment",
        "user": "I'm not looking for a job right now.",
        "expect": ("no_sell", "no_hangup", "no_qualify", "short"),
        "intent": "soft no; do not hang up unless they said don't call",
    },
    {
        "id": "recruit_dont_call",
        "role": "recruitment",
        "user": "Please don't call me again.",
        "expect": ("hangup", "no_question", "short"),
        "intent": "don't call",
    },
]
