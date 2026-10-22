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

# Five agentic conversation patterns — different businesses, same anti-checklist brain.
AGENTIC_BRIEFS: dict[str, dict[str, str]] = {
    "priya_estates": {
        "session": "eval-priya-estates",
        "language": "en-IN",
        "expected_role": "sales",
        "brief": (
            "Create an English sales agent named Priya for Priya Estates. "
            "Plots from 25 lakhs, villas from 80 lakhs around Hyderabad including Vanasthalipuram. "
            "Send WhatsApp details or book visits. Never invent prices."
        ),
    },
    "smilecare_dental": {
        "session": "eval-smilecare",
        "language": "en-IN",
        "expected_role": "appointment",
        "brief": (
            "Create an English appointment agent named Meera for SmileCare Dental. "
            "Book dentist appointments for tooth pain and checkups. "
            "Confirm preferred day and time, then lock the slot. Do not sell products."
        ),
    },
    "salesflow_crm": {
        "session": "eval-salesflow",
        "language": "en-IN",
        "expected_role": "sales",
        "brief": (
            "Create an English SaaS sales agent named Arjun for SalesFlow CRM. "
            "CRM software for small businesses. Plans start at five thousand rupees per month. "
            "Answer pricing first, understand team size and needs, then book a product demo."
        ),
    },
    "autocare_motors": {
        "session": "eval-autocare",
        "language": "en-IN",
        "expected_role": "support",
        "brief": (
            "Create an English service agent named Ravi for AutoCare Motors car service center. "
            "Book service requests for brake noise and inspections. Capture vehicle model, issue, "
            "preferred slot, and add-on checks. Do not sell cars."
        ),
    },
    "speakpro_academy": {
        "session": "eval-speakpro",
        "language": "en-IN",
        "expected_role": "education",
        "brief": (
            "Create an English education counselor named Sneha for SpeakPro Academy. "
            "Spoken English courses: beginner, intermediate, advanced. Evening batches available. "
            "Intermediate course is eight thousand rupees. Offer a free trial class. Do not hard-sell."
        ),
    },
}

# Critical multi-turn scripts. Each turn lists prior user utterances in `history`
# so the offline judge can catch re-asks of known facts.
AGENTIC_SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "priya_estates": [
        {
            "id": "re_plot_need",
            "user": "Hi, I'm actually looking for a plot around Hyderabad.",
            "history": "",
            "expect": ("at_most_one_question", "not_robot", "no_hangup", "no_reask_known"),
            "bad": "Are you interested in buying a plot with us?",
            "good": "Got it — Hyderabad plots. What's your budget range?",
            "intent": "need clear; never ask are-you-interested",
        },
        {
            "id": "re_budget",
            "user": "My budget is around 25 lakhs.",
            "history": "Hi, I'm actually looking for a plot around Hyderabad.",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "What's your budget? And are you interested?",
            "good": "Perfect, 25 lakhs fits our plots. Is this for investment or to build?",
            "intent": "use budget; do not re-ask interest",
        },
        {
            "id": "re_purpose",
            "user": "It's mainly for investment.",
            "history": (
                "Hi, I'm actually looking for a plot around Hyderabad. "
                "My budget is around 25 lakhs."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "What's your budget again?",
            "good": "Investment focus noted. Which area around Hyderabad works best?",
            "intent": "purpose known; do not re-ask budget",
        },
        {
            "id": "re_area",
            "user": "I'm looking around Vanasthalipuram side.",
            "history": (
                "looking for a plot around Hyderabad. budget is around 25 lakhs. "
                "mainly for investment."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "Which area are you looking at?",
            "good": "Vanasthalipuram works. We have plots from 25 lakhs there — want details?",
            "intent": "area known; recommend relevant option",
        },
        {
            "id": "re_options",
            "user": "What options do you have?",
            "history": (
                "looking for a plot around Hyderabad. budget 25 lakhs. "
                "investment. Vanasthalipuram side."
            ),
            "expect": ("at_most_one_question", "no_qualify", "no_reask_known", "no_hangup"),
            "bad": "Before I share options, may I know your budget and location?",
            "good": (
                "Around Vanasthalipuram we have plots from 25 lakhs that suit investment. "
                "I can send the details on WhatsApp."
            ),
            "intent": "answer options from known facts",
        },
        {
            "id": "re_whatsapp",
            "user": "Okay, can you send me the details on WhatsApp?",
            "history": (
                "plot Hyderabad. budget 25 lakhs. investment. Vanasthalipuram. "
                "What options do you have?"
            ),
            "expect": ("at_most_one_question", "no_hangup", "no_reask_known"),
            "bad": "Are you interested? What's your budget?",
            "good": "Sure — share your WhatsApp number and I'll send the plot details.",
            "intent": "honor WhatsApp next step",
        },
        {
            "id": "re_followup",
            "user": "I'll check them and get back to you.",
            "history": "send me the details on WhatsApp",
            "expect": ("short", "no_hangup", "no_qualify", "at_most_one_question"),
            "bad": "Goodbye. Are you still interested?",
            "good": "Sounds good — take a look and we can talk when you're ready.",
            "intent": "soft close; stay on line",
        },
    ],
    "smilecare_dental": [
        {
            "id": "dent_need",
            "user": "I need to see a dentist.",
            "history": "",
            "expect": ("at_most_one_question", "no_sell", "no_hangup", "no_reask_known"),
            "bad": "Why are you calling today?",
            "good": "Sure — what's bothering you, or shall we book a checkup?",
            "intent": "dentist need clear",
        },
        {
            "id": "dent_pain",
            "user": "I've been having tooth pain since yesterday.",
            "history": "I need to see a dentist.",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "How can I help you today? Why are you calling?",
            "good": "Sorry about the pain. When can you come in?",
            "intent": "symptom known; do not re-ask why",
        },
        {
            "id": "dent_tomorrow_evening",
            "user": "I can come tomorrow evening.",
            "history": "I need to see a dentist. I've been having tooth pain since yesterday.",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "When would you like to come?",
            "good": "Tomorrow evening works. What time around evening suits you?",
            "intent": "CRITICAL: do not re-ask when after tomorrow evening",
        },
        {
            "id": "dent_six",
            "user": "Around 6 would be good.",
            "history": (
                "dentist. tooth pain since yesterday. I can come tomorrow evening."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "What time works for you? When would you like to come?",
            "good": "We can do tomorrow at 6 PM for the tooth pain. Shall I book it?",
            "intent": "time known; offer confirm",
        },
        {
            "id": "dent_availability",
            "user": "Do you have an appointment available?",
            "history": "tooth pain. tomorrow evening. Around 6 would be good.",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "When would you like to come?",
            "good": "Yes — tomorrow 6 PM is open for the tooth-pain visit.",
            "intent": "answer availability for known slot",
        },
        {
            "id": "dent_book",
            "user": "Yes, book it.",
            "history": "tomorrow evening around 6. tooth pain. Do you have an appointment available?",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "Why are you calling? When would you like to come?",
            "good": "Booked for tomorrow at 6 PM for tooth pain. See you then.",
            "intent": "confirm booking details",
        },
    ],
    "salesflow_crm": [
        {
            "id": "crm_team",
            "user": "I'm looking for a CRM for my 10-person sales team.",
            "history": "",
            "expect": ("at_most_one_question", "no_hangup", "not_robot", "no_reask_known", "no_qualify"),
            "bad": "First, may I know your company size?",
            "good": "A 10-person sales team fits SalesFlow well. What do you need most?",
            "intent": "team size already given",
        },
        {
            "id": "crm_needs",
            "user": "We mainly need lead tracking and follow-ups.",
            "history": "I'm looking for a CRM for my 10-person sales team.",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "How many people are on your team?",
            "good": "Lead tracking and follow-ups are core. Want pricing or a quick walkthrough?",
            "intent": "use team size + needs",
        },
        {
            "id": "crm_price",
            "user": "How much does it cost?",
            "history": (
                "CRM for my 10-person sales team. We mainly need lead tracking and follow-ups."
            ),
            "expect": ("no_qualify", "no_question", "no_reask_known", "no_hangup"),
            "bad": "Before I tell you the price, may I know your company size?",
            "good": "Plans start at five thousand rupees a month for small sales teams.",
            "intent": "CRITICAL: answer price before more qualify",
        },
        {
            "id": "crm_reasonable",
            "user": "That sounds reasonable.",
            "history": "10-person sales team. lead tracking. How much does it cost?",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup", "no_qualify"),
            "bad": "First, may I know your company size?",
            "good": "Great — I can set up a demo for your sales team this week.",
            "intent": "move toward demo",
        },
        {
            "id": "crm_demo",
            "user": "Can I see a demo?",
            "history": "10-person team. lead tracking. That sounds reasonable.",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "How many people are on your team?",
            "good": "Absolutely — what day this week works for the demo?",
            "intent": "honor demo request",
        },
        {
            "id": "crm_this_week",
            "user": "Sure, sometime this week works.",
            "history": "10-person CRM. Can I see a demo?",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup", "no_qualify"),
            "bad": "First, may I know your company size?",
            "good": "Perfect — share a day and time this week and I'll lock the demo.",
            "intent": "confirm demo window",
        },
    ],
    "autocare_motors": [
        {
            "id": "auto_noise",
            "user": "My car is making a strange noise when I brake.",
            "history": "",
            "expect": ("at_most_one_question", "no_sell", "no_hangup"),
            "bad": "Would you like to buy a new car?",
            "good": "Brake noise noted — what's the car model and year?",
            "intent": "capture issue",
        },
        {
            "id": "auto_model",
            "user": "It's a 2022 Hyundai Creta.",
            "history": "My car is making a strange noise when I brake.",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "Which car do you drive?",
            "good": "Got the 2022 Creta. When can you bring it in?",
            "intent": "model known",
        },
        {
            "id": "auto_saturday",
            "user": "I'm free Saturday morning.",
            "history": "strange noise when I brake. It's a 2022 Hyundai Creta.",
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "When are you free? What is your car model?",
            "good": "Saturday morning works. Any preferred time?",
            "intent": "day known; ask only missing time",
        },
        {
            "id": "auto_ten",
            "user": "Do you have any slots around 10?",
            "history": (
                "brake noise. 2022 Hyundai Creta. I'm free Saturday morning."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "When would you like to come? Which car is it?",
            "good": "Yes — Saturday at 10 AM is open for the Creta brake check.",
            "intent": "answer slot for known day",
        },
        {
            "id": "auto_book",
            "user": "Okay, book it for 10.",
            "history": (
                "brake noise. 2022 Hyundai Creta. Saturday morning. slots around 10."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "What's your car model? When are you free?",
            "good": "Booked Saturday 10 AM for the Creta brake noise check.",
            "intent": "confirm booking",
        },
        {
            "id": "auto_addon",
            "user": "Actually, can you also check the brakes?",
            "history": (
                "strange noise when I brake. 2022 Hyundai Creta. "
                "Saturday morning around 10. book it for 10."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
            "bad": "Sorry, let's start over. What's wrong with your car? Which car is it?",
            "good": (
                "Updated — Saturday 10 AM for brake noise plus a full brake inspection "
                "on the 2022 Creta."
            ),
            "intent": "CRITICAL: latest intent override; no restart",
        },
    ],
    "speakpro_academy": [
        {
            "id": "eng_goal",
            "user": "I want to improve my English speaking.",
            "history": "",
            "expect": ("at_most_one_question", "no_hangup", "not_robot", "no_reask_known"),
            "bad": "Are you interested in buying our course?",
            "good": "Happy to help with spoken English. What's the main struggle?",
            "intent": "goal clear",
        },
        {
            "id": "eng_problem",
            "user": "I can understand English pretty well, but I struggle to speak confidently.",
            "history": "I want to improve my English speaking.",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "Why do you want to learn English? Why are you calling?",
            "good": "Confidence while speaking — got it. Mornings or evenings better?",
            "intent": "problem known",
        },
        {
            "id": "eng_evenings",
            "user": "I work during the day, so evenings are better.",
            "history": (
                "improve my English speaking. understand well but struggle to speak confidently."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "When are you available?",
            "good": "Evening batches work. Want to hear what courses we have?",
            "intent": "availability known",
        },
        {
            "id": "eng_courses",
            "user": "What courses do you have?",
            "history": (
                "improve English speaking. struggle to speak confidently. evenings are better."
            ),
            "expect": ("at_most_one_question", "no_qualify", "no_reask_known", "no_hangup"),
            "bad": "Before I tell you, what's your budget?",
            "good": (
                "We have beginner, intermediate, and advanced spoken English — "
                "evening batches available."
            ),
            "intent": "answer courses directly",
        },
        {
            "id": "eng_price",
            "user": "How much is the intermediate course?",
            "history": (
                "spoken English. evenings. What courses do you have?"
            ),
            "expect": ("no_qualify", "no_question", "no_reask_known", "no_hangup"),
            "bad": "Before I share the fee, may I know your availability?",
            "good": "The intermediate course is eight thousand rupees.",
            "intent": "answer price directly",
        },
        {
            "id": "eng_ok",
            "user": "Okay, I think that could work.",
            "history": "intermediate course price. evenings. speak confidently.",
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "When are you available for classes?",
            "good": "Great — we also offer a free trial class in the evening batch.",
            "intent": "soft yes → natural next step",
        },
        {
            "id": "eng_trial",
            "user": "Can I attend a trial class first?",
            "history": (
                "improve English speaking. evenings better. intermediate course. "
                "Okay, I think that could work."
            ),
            "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
            "bad": "First tell me your goal again. Are you interested?",
            "good": "Yes — I'll book an evening trial class for spoken English. Which day works?",
            "intent": "trial class is the close",
        },
    ],
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15-CHARACTERISTIC CRITICAL SCENARIOS
# Tests every characteristic from the human-salesperson evaluation checklist.
# Each entry has good/bad pairs and strict expect tags.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# -- Characteristic 1: Understands meaning, not just keywords --
CHAR1_MEANING: list[dict[str, Any]] = [
    {
        "id": "c1_implicit_plot_interest",
        "user": "I'm actually looking for something around 25 lakhs. Maybe a plot for investment.",
        "history": "",
        "expect": ("no_reask_known", "at_most_one_question", "no_hangup"),
        "bad": "Are you looking for a plot?",
        "good": "Got it — plot around 25 lakhs for investment. Which area works best?",
        "intent": "agent must understand plot+budget+purpose from one sentence, not re-ask",
    },
    {
        "id": "c1_implicit_crm_team",
        "user": "I'm looking for a CRM for my 10-person sales team.",
        "history": "",
        "expect": ("no_reask_known", "at_most_one_question", "no_qualify", "no_hangup"),
        "bad": "First, may I know your company size?",
        "good": "A 10-person sales team fits SalesFlow well. What do you need most — lead tracking, pipeline, or reporting?",
        "intent": "team size is already stated; must not re-ask",
    },
    {
        "id": "c1_implicit_dental_need",
        "user": "I need to see a dentist. I've been having tooth pain since yesterday.",
        "history": "",
        "expect": ("no_reask_known", "at_most_one_question", "no_sell", "no_hangup"),
        "bad": "Why are you calling today?",
        "good": "Sorry about the pain. When can you come in?",
        "intent": "dentist+tooth pain is clear; never ask why calling",
    },
]

# -- Characteristic 2: Answers before asking --
CHAR2_ANSWER_FIRST: list[dict[str, Any]] = [
    {
        "id": "c2_plot_price_question",
        "user": "How much are your plots?",
        "history": "",
        "expect": ("no_qualify", "no_hangup"),
        "bad": "May I know your budget first?",
        "good": "Our plots start around 25 lakhs. If you're around that range, I can narrow down the best options.",
        "intent": "answer the price question BEFORE asking budget",
    },
    {
        "id": "c2_crm_cost_question",
        "user": "How much does it cost?",
        "history": "I'm looking for a CRM for my 10-person sales team. We mainly need lead tracking.",
        "expect": ("no_qualify", "no_question", "no_reask_known", "no_hangup"),
        "bad": "Before I tell you the price, may I know your company size?",
        "good": "Plans start at five thousand rupees a month for small sales teams.",
        "intent": "CRITICAL: answer price, don't delay with qualify",
    },
    {
        "id": "c2_course_price_question",
        "user": "How much is the intermediate course?",
        "history": "spoken English. evenings. What courses do you have?",
        "expect": ("no_qualify", "no_question", "no_reask_known", "no_hangup"),
        "bad": "Before I share the fee, may I know your availability?",
        "good": "The intermediate course is eight thousand rupees.",
        "intent": "answer the price directly, availability is already known",
    },
]

# -- Characteristic 3: Every question has a reason --
CHAR3_USEFUL_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "c3_budget_already_known",
        "user": "It's mainly for investment.",
        "history": "I'm looking for a plot around Hyderabad. My budget is around 25 lakhs.",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
        "bad": "What is your budget?",
        "good": "Got it. Since you're looking mainly for investment, are you looking to hold for a few years, or thinking of building later?",
        "intent": "budget is known — question must change the recommendation",
    },
    {
        "id": "c3_dont_ask_when_after_day_time",
        "user": "Around 6 would be good.",
        "history": "dentist. tooth pain since yesterday. I can come tomorrow evening.",
        "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        "bad": "What time works for you? When would you like to come?",
        "good": "We can do tomorrow at 6 PM for the tooth pain. Shall I book it?",
        "intent": "time+day known; only useful question is confirming the booking",
    },
]

# -- Characteristic 5: Combines multiple pieces of information (dense dump) --
CHAR5_DENSE_DUMP: list[dict[str, Any]] = [
    {
        "id": "c5_realty_dense_dump",
        "user": "I'm looking for a 200-square-yard plot near Vanasthalipuram, around 30 lakhs, mainly for investment.",
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "no_hangup", "spoken_short"),
        "bad": "What size? What location? What's your budget? What's the purpose?",
        "good": "That gives me a clear picture. A plot in that range for investment makes sense. Let me narrow down options for you.",
        "intent": "CRITICAL: agent must process ALL facts in one turn, not unpack into checklist",
    },
    {
        "id": "c5_autocare_dense_dump",
        "user": "My car is a 2022 Hyundai Creta, it's making a strange noise when I brake, and I'm free Saturday morning around 10.",
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "no_sell", "no_hangup"),
        "bad": "What's your car model? When are you free? What's the issue?",
        "good": "Got it — 2022 Creta, brake noise, Saturday 10 AM. I'll book that for you.",
        "intent": "agent must use all three facts without re-asking any",
    },
    {
        "id": "c5_crm_dense_dump",
        "user": "I need a CRM for my 10-person sales team, mainly for lead tracking and follow-ups, and I'd like to see it this week.",
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "no_hangup"),
        "bad": "How many people are on your team? What features do you need? When can you meet?",
        "good": "Perfect — 10-person team, lead tracking and follow-ups, demo this week. Which day works best?",
        "intent": "agent must acknowledge all three pieces, ask only the one missing detail",
    },
]

# -- Characteristic 6: Reacts to what was JUST said (emotional/intent state) --
CHAR6_REACT_TO_EMOTION: list[dict[str, Any]] = [
    {
        "id": "c6_not_sure_about_buying",
        "user": "I'm not sure if I want to buy yet.",
        "history": "looking for a plot around Hyderabad.",
        "expect": ("react_hesitation", "no_hangup", "at_most_one_question"),
        "bad": "What's your budget?",
        "good": "That's completely fine. Are you mainly comparing prices right now, or would you like to understand what's available first?",
        "intent": "CRITICAL: react to emotional/intent state, not the next script question",
    },
    {
        "id": "c6_expensive_reaction",
        "user": "That's too expensive.",
        "history": "looking for a plot. budget 25 lakhs.",
        "expect": ("no_qualify", "no_hangup", "at_most_one_question"),
        "bad": "What is your budget?",
        "good": "I understand. If 25 lakhs is your comfortable range, I can show you options closer to that budget.",
        "intent": "objection — acknowledge price concern, don't ask budget again",
    },
    {
        "id": "c6_just_browsing",
        "user": "I'm just looking around, not sure if I want to commit yet.",
        "history": "spoken English. struggle to speak confidently.",
        "expect": ("no_hangup", "at_most_one_question", "no_sell"),
        "bad": "Would you like to buy our course? When can you start?",
        "good": "No pressure at all. If you'd like, you can attend a free trial class first to see if it works for you.",
        "intent": "react to soft hesitation — offer low-commitment next step",
    },
]

# -- Characteristic 7: Has conversational direction --
CHAR7_DIRECTION: list[dict[str, Any]] = [
    {
        "id": "c7_progress_after_interest",
        "user": "I'm looking for a villa.",
        "history": "",
        "expect": ("at_most_one_question", "no_hangup", "no_reask_known"),
        "bad": "Are you interested in buying? What's your budget? Which location?",
        "good": "Sure. We have villas starting around 80 lakhs. If that's within your range, I can narrow it down based on location.",
        "intent": "move conversation forward — answer + one discovery, not a question list",
    },
    {
        "id": "c7_progress_after_crm_interest",
        "user": "That sounds reasonable.",
        "history": "10-person sales team. lead tracking. How much does it cost?",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup", "no_qualify"),
        "bad": "First, may I know your company size?",
        "good": "Great — I can set up a demo for your sales team this week.",
        "intent": "move toward demo — don't restart qualify",
    },
]

# -- Characteristic 8: Recommends instead of endlessly qualifying --
CHAR8_RECOMMEND: list[dict[str, Any]] = [
    {
        "id": "c8_enough_known_recommend",
        "user": "What options do you have?",
        "history": "plot. 25 lakhs. investment. Vanasthalipuram side.",
        "expect": ("at_most_one_question", "no_qualify", "no_reask_known", "no_hangup"),
        "bad": "Before I share options, may I know your budget and location?",
        "good": "Around Vanasthalipuram we have plots from 25 lakhs that suit investment. I can send the details on WhatsApp.",
        "intent": "CRITICAL: enough is known — recommend, don't ask 10 more questions",
    },
    {
        "id": "c8_dental_enough_known_book",
        "user": "Do you have an appointment available?",
        "history": "tooth pain. tomorrow evening. Around 6.",
        "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        "bad": "When would you like to come?",
        "good": "Yes — tomorrow 6 PM is open for the tooth-pain visit.",
        "intent": "all details known — answer and confirm, don't re-ask",
    },
    {
        "id": "c8_speakpro_recommend_trial",
        "user": "Okay, I think that could work.",
        "history": "spoken English. evenings. intermediate course price.",
        "expect": ("at_most_one_question", "no_reask_known", "no_hangup"),
        "bad": "When are you available for classes?",
        "good": "Great — we also offer a free trial class in the evening batch.",
        "intent": "soft yes → recommend next step (trial), don't restart qualifying",
    },
]

# -- Characteristic 9: Knows when to stop selling --
CHAR9_STOP_SELLING: list[dict[str, Any]] = [
    {
        "id": "c9_send_details_stop",
        "user": "Just send me the details. I'll check them later.",
        "history": "plot Hyderabad. 25 lakhs. investment. Vanasthalipuram.",
        "expect": ("honor_next_step", "short", "no_hangup", "no_qualify"),
        "bad": "Sure. May I know your budget? And when can I call you? And what is your preferred location?",
        "good": "Absolutely. I'll send you the details. Have a look when you're free, and we can take it from there.",
        "intent": "CRITICAL: customer said stop — don't keep interrogating",
    },
    {
        "id": "c9_check_and_get_back",
        "user": "I'll check them and get back to you.",
        "history": "send me the details on WhatsApp.",
        "expect": ("short", "no_hangup", "no_qualify", "at_most_one_question"),
        "bad": "Are you still interested? What's your budget?",
        "good": "Sounds good — take a look and we can talk when you're ready.",
        "intent": "customer closing — stop selling, short acknowledgment",
    },
]

# -- Characteristic 10: Handles objections like a human --
CHAR10_OBJECTIONS: list[dict[str, Any]] = [
    {
        "id": "c10_too_expensive",
        "user": "That's too expensive.",
        "history": "looking for a plot. 25 lakhs. investment.",
        "expect": ("no_qualify", "no_hangup", "at_most_one_question"),
        "bad": "What is your budget?",
        "good": "I understand. If 25 lakhs is your comfortable range, I can show you options closer to that budget.",
        "intent": "acknowledge → respond → adapt. Never just re-ask budget",
    },
    {
        "id": "c10_already_decided",
        "user": "I've already decided to go with someone else.",
        "history": "looking for plots. 25 lakhs.",
        "expect": ("no_qualify", "no_hangup", "at_most_one_question", "short"),
        "bad": "Would you like to arrange a site visit? We have great options.",
        "good": "Fair enough. If anything changes, we're always here. Good luck with your purchase.",
        "intent": "acknowledge their decision — don't pitch harder",
    },
    {
        "id": "c10_ill_think_about_it",
        "user": "I'll think about it.",
        "history": "CRM. 10-person team. pricing.",
        "expect": ("no_qualify", "no_hangup", "short"),
        "bad": "May I know what's holding you back? First, what's your company size?",
        "good": "Of course, take your time. I'll send the pricing summary so you have it when you're ready.",
        "intent": "soft objection — offer one helpful step, don't interrogate",
    },
]

# -- Characteristic 11: Handles unexpected conversation jumps --
CHAR11_CONVERSATION_JUMP: list[dict[str, Any]] = [
    {
        "id": "c11_villa_to_plot_switch",
        "user": "Actually forget the villa. Do you have plots?",
        "history": "looking for a villa. budget around 80 lakhs.",
        "expect": ("at_most_one_question", "no_hangup", "no_reask_known", "no_qualify"),
        "bad": "Before we discuss plots, may I know why you're interested in a villa?",
        "good": "Sure — we have plots starting from 25 lakhs around Hyderabad. Any preferred area?",
        "intent": "CRITICAL: latest requirement wins. Switch immediately, no 'before we discuss'",
    },
    {
        "id": "c11_checkup_to_pain",
        "user": "Actually, it's not a checkup. I have a sharp tooth pain.",
        "history": "I need a dental checkup.",
        "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        "bad": "So you want a checkup? When would you like to come?",
        "good": "Got it — tooth pain, not a checkup. When can you come in?",
        "intent": "latest correction wins — agent must switch from checkup to pain",
    },
    {
        "id": "c11_addon_brakes",
        "user": "Actually, can you also check the brakes?",
        "history": "strange noise when I brake. 2022 Hyundai Creta. Saturday morning around 10. book it for 10.",
        "expect": ("at_most_one_question", "no_reask_known", "no_sell", "no_hangup"),
        "bad": "Sorry, let's start over. What's wrong with your car? Which car is it?",
        "good": "Updated — Saturday 10 AM for brake noise plus a full brake inspection on the 2022 Creta.",
        "intent": "add-on to existing booking — never restart the conversation",
    },
]

# -- Characteristic 12: Detects frustration --
CHAR12_FRUSTRATION: list[dict[str, Any]] = [
    {
        "id": "c12_already_told_budget",
        "user": "I already told you my budget is 25 lakhs.",
        "history": "looking for a plot. budget 25 lakhs. investment.",
        "expect": ("ack_frustration", "no_reask_known", "no_hangup", "at_most_one_question"),
        "bad": "Okay. And may I know your budget?",
        "good": "Yes, you're right. You mentioned 25 lakhs. Let me work with that and narrow this down.",
        "intent": "CRITICAL: acknowledge + move forward. NEVER re-ask the stated fact",
    },
    {
        "id": "c12_too_many_questions",
        "user": "You're asking too many questions. Just tell me what you have.",
        "history": "plot. 25 lakhs. Vanasthalipuram.",
        "expect": ("no_qualify", "no_hangup", "short", "at_most_one_question"),
        "bad": "Sure, but first may I know your preferred size? And timeline?",
        "good": "Sorry about that. We have plots from 25 lakhs near Vanasthalipuram. Want me to share the details?",
        "intent": "frustration at interrogation — stop asking, give info",
    },
    {
        "id": "c12_taking_too_long",
        "user": "This is taking too long. I'm getting frustrated.",
        "history": "brake noise. 2022 Creta.",
        "expect": ("short", "no_qualify", "no_hangup"),
        "bad": "I completely understand how you feel. Would you like to arrange a site visit?",
        "good": "Sorry about that. Let me quickly book your Creta for a brake check. When works?",
        "intent": "short apology + fast action, no pitch, no robot empathy",
    },
]

# -- Characteristic 13: Uses short spoken sentences --
CHAR13_SHORT_SPOKEN: list[dict[str, Any]] = [
    {
        "id": "c13_no_brochure_speech",
        "user": "What do you offer?",
        "history": "",
        "expect": ("spoken_short", "at_most_one_question", "no_hangup"),
        "bad": "We offer a comprehensive range of premium residential plots strategically located across multiple emerging areas with excellent connectivity and strong appreciation potential.",
        "good": "We have plots and villas around Hyderabad. If you have a budget in mind, I can narrow those down for you.",
        "intent": "CRITICAL: brochure copy is a FAIL. Short, spoken, speakable sentences only",
    },
    {
        "id": "c13_speakpro_no_brochure",
        "user": "What courses do you have?",
        "history": "improve English speaking. evenings.",
        "expect": ("spoken_short", "no_qualify", "no_reask_known", "no_hangup"),
        "bad": "We offer a comprehensive range of premium spoken English programs designed to enhance your communication skills with strategic methodology and progressive curriculum paths.",
        "good": "We have beginner, intermediate, and advanced spoken English — evening batches available.",
        "intent": "brochure copy is a FAIL. Short factual answer",
    },
]

# -- Characteristic 14: Doesn't use the same sentence repeatedly --
CHAR14_VARIED_ACKS: list[dict[str, Any]] = [
    {
        "id": "c14_no_sure_absolutely_repeat",
        "user": "Okay.",
        "history": "plot. 25 lakhs.",
        "expect": ("not_robot", "no_hangup", "at_most_one_question"),
        "bad": "Sure, absolutely. May I know your preferred location?",
        "good": "Got it. Which area works best for you?",
        "intent": "varied ack — not 'Sure, absolutely' or 'I completely understand'",
    },
]

# -- Characteristic 15: Sounds like it's actually listening (whole-thought response) --
CHAR15_WHOLE_THOUGHT: list[dict[str, Any]] = [
    {
        "id": "c15_ultimate_test_realty",
        "user": (
            "I'm looking for a plot around Hyderabad, preferably near Vanasthalipuram. "
            "My budget is around 25 lakhs and it's mainly for investment. "
            "I'm not in a huge hurry though, so I just want to understand what options are available."
        ),
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "spoken_short", "no_hangup"),
        "bad": "Are you interested in plots? What is your budget? Which location? Is it for investment? When are you planning to buy?",
        "good": (
            "Got it. So you're looking around Vanasthalipuram, around 25 lakhs, mainly as an investment. "
            "Since you're not in a hurry, I can give you a couple of options that fit that range."
        ),
        "intent": "ULTIMATE TEST: agent must synthesize ALL facts and form an opinion",
    },
    {
        "id": "c15_parents_villa",
        "user": (
            "I'm looking for something for my parents. They'd probably prefer a villa "
            "because they don't want to deal with construction. My budget is around 80 lakhs, "
            "and I'd prefer somewhere not too far from the city."
        ),
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "spoken_short", "no_hangup"),
        "bad": "Are you looking for a villa? What's your budget? Who is it for?",
        "good": (
            "That makes sense. A ready-to-move villa would suit your parents if you don't want the hassle of construction. "
            "I can narrow down villa options around 80 lakhs, not too far from the city."
        ),
        "intent": "agent understood → formed opinion → recommended. Not a checklist",
    },
    {
        "id": "c15_autocare_full_context",
        "user": (
            "My Creta's been making a weird grinding noise when I brake, especially at low speed. "
            "I think it might be the brake pads. I'm free Saturday morning, around 10 would work. "
            "Can you also do a general checkup while it's there?"
        ),
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "no_sell", "no_hangup"),
        "bad": "What's your car model? What's the issue? When are you free? Anything else?",
        "good": (
            "Sounds like brake pads — we'll check that plus a general checkup. "
            "Saturday 10 AM for the Creta. I'll book it."
        ),
        "intent": "full context given — agent should process everything and confirm",
    },
    {
        "id": "c15_speakpro_full_context",
        "user": (
            "I understand English well but I struggle to speak confidently. "
            "I work during the day so only evenings work. "
            "I saw you have an intermediate course — how much is it and can I try a class first?"
        ),
        "history": "",
        "expect": ("use_all_facts", "at_most_one_question", "no_hangup"),
        "bad": "What's your goal? When are you available? Which course are you interested in?",
        "good": (
            "The intermediate course is eight thousand rupees, and yes — we offer a free trial class in the evening batch. "
            "Which day works for you?"
        ),
        "intent": "answer both questions (price + trial) from the dense context",
    },
]
