# Flow matrix flow-matrix-smoke2

Schema `sim_4a82de366f21490480669e23bbce9dde`. Brain pipeline `employee`. PASS needs every server-truth check and every judge check to pass.

| Scenario | Script | en-IN |
|---|---|---|
| objective_followthrough | solar | FAIL: judge:answered_question_with_facts:unknown, judge:offered_survey_objective:unknown |

Passed 0/1.

## Transcripts

### en-IN/objective_followthrough/solar FAIL — disposition interested ['judge:answered_question_with_facts:unknown', 'judge:offered_survey_objective:unknown']
- opening: Hello, my name is Priya calling from SunPeak Solar, a rooftop solar installer in Chennai. I am calling because you recently requested a solar quote on our website. Is now a good time to speak?
- caller: How much does it cost and is there any subsidy?
- agent: A 3 kW rooftop system costs 1,95,000 rupees before the government subsidy of 78,000 rupees, so the customer pays 1,17,000 rupees. EMI is available from 2,999 rupees per month for 48 months. Regarding other charges or terms, those details are unknown.
- caller: Okay, that sounds reasonable.
- agent: The draft does not fully answer the caller's implicit question about whether proceeding is reasonable.
- caller: Hmm, okay.
- agent: I understand. Since the pricing and subsidy details have already been shared and you find them reasonable, would you like to book a free site survey? For that, may I please take your name, your area, and your preferred day?
- judge answered_question_with_facts: None — judge_error:RateLimitError
- judge offered_survey_objective: None — judge_error:RateLimitError
