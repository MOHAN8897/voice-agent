The architecture below is the version I would recommend for your production voice-agent SaaS.

1. Complete architecture
                           CUSTOMER ONBOARDING
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │ Customer enters         │
                    │ Business Prompt         │
                    │ on frontend             │
                    └────────────┬────────────┘
                                 │
                     Save exactly as entered
                                 │
                    ┌────────────▼────────────┐
                    │ RAW BUSINESS PROMPT     │
                    │ stored on your server   │
                    └────────────┬────────────┘
                                 │
                         ONE-TIME OPTIMIZER
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ OPTIMIZED BUSINESS      │
                    │ BRAIN                   │
                    │                         │
                    │ - business rules        │
                    │ - products              │
                    │ - qualification logic   │
                    │ - tone/style            │
                    │ - workflow              │
                    └────────────┬────────────┘
                                 │
                          Save + version
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│                    COMPILED LIVE BRAIN                     │
│                                                              │
│ YOUR PLATFORM BRAIN                                          │
│ +                                                            │
│ OPTIMIZED CUSTOMER BUSINESS BRAIN                            │
│ +                                                            │
│ STATIC OUTPUT / BEHAVIOR RULES                               │
│                                                              │
│              ↓ CACHE BREAKPOINT                              │
└──────────────────────────────────────────────────────────────┘
                                 │
                                 │
                           LIVE CALL
                                 │
                                 ▼
                         USER SPEAKS
                                 │
                                 ▼
                            STT STREAM
                                 │
                                 ▼
                           YOUR SERVER
                                 │
                 ┌───────────────┼────────────────┐
                 │               │                │
                 ▼               ▼                ▼
          Save full text    Update memory     Live LLM request
          to call ledger    JSON/state
                                 │
                                 ▼
                         WORKING MEMORY
                                 │
                                 ▼
                         OPENAI / OTHER LLM
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                  ▼                             ▼
           spoken_response                 memory_update
                  │                             │
                  ▼                             ▼
                 TTS                     YOUR SERVER
                  │                             │
                  ▼                             ▼
              USER HEARS                Merge into memory
                                                │
                                                ▼
                                        Next turn memory
2. There are THREE completely different types of information

This is the most important part of the whole architecture.

A. Stable Brain

This rarely changes during calls.

It contains:

YOUR PLATFORM BRAIN
+
CUSTOMER'S OPTIMIZED BUSINESS BRAIN
+
STATIC BEHAVIOR RULES

This belongs before the cache breakpoint.

B. Working Memory

This changes during the call.

Example:

{
  "customer": {
    "name": "Mohan"
  },
  "requirements": {
    "budget": ["50 lakhs"],
    "locations": ["Hyderabad"],
    "property_types": ["2BHK"]
  },
  "preferences": [],
  "objections": [],
  "important_context": []
}

This belongs after the cache breakpoint.

Your server owns this.

C. Full Call Ledger

This contains everything.

Turn 1
Turn 2
Turn 3
...
Turn 20

Plus:

user audio
agent audio
timestamps
interruptions
metadata

This is never used as the normal live context.

3. Customer onboarding architecture

When your customer types their instructions:

"We sell apartments in Hyderabad...
Speak Telugu...
Ask budget...
Ask preferred area...
Offer a site visit..."
Frontend

Show exactly what they typed.

Do not replace their text with the optimized version.

Backend

Save:

raw_business_prompt

Then run a one-time optimization step.

Result:

optimized_business_prompt

Example:

BUSINESS:
Residential property sales in Hyderabad.

PRODUCTS:
2BHK, 3BHK apartments.

QUALIFICATION:
Collect:
- budget
- preferred location
- property type
- purchase timeline
- parking requirement

LANGUAGE:
Conversational Telugu.

STYLE:
Concise, friendly, one question at a time.

CONVERSION:
If the customer agrees to a concrete next step,
treat the lead as qualified/high-interest.

Then save:

customer_id
prompt_version
raw_prompt
optimized_prompt
optimized_at
4. Compile the cached brain

Do not send the customer's prompt and your platform prompt as separate dynamic pieces.

Create one compiled version:

PLATFORM BRAIN
+
CUSTOMER BUSINESS BRAIN
+
STATIC OUTPUT RULES

Example:

=== PLATFORM BRAIN ===

You are a production Telugu voice agent.
Follow platform safety rules...
...

=== CUSTOMER BUSINESS BRAIN ===

Business:
Residential property sales in Hyderabad.
...

=== STATIC RESPONSE RULES ===

Return:
spoken_response
memory_update
...

This entire section becomes the stable prefix.

Then place the cache breakpoint after it.

5. What happens on the first call turn

Caller says:

“నా పేరు మోహన్. నాకు హైదరాబాద్‌లో 50 లక్షల 2BHK కావాలి.”

Step 1 — STT

Sarvam/Cartesia produces:

నా పేరు మోహన్. నాకు హైదరాబాద్‌లో 50 లక్షల 2BHK కావాలి.
Step 2 — Server creates initial memory

Your server may create:

{
  "customer": {
    "name": "Mohan"
  },
  "requirements": {
    "budget": ["50 lakhs"],
    "locations": ["Hyderabad"],
    "property_types": ["2BHK"]
  }
}

For simple fields, your backend can extract them directly; for ambiguous information, your main LLM can return the structured memory_update.

Step 3 — Send LLM request

Conceptually:

[CACHED]

Platform brain
+
Customer business brain
+
Static rules

--- CACHE BREAKPOINT ---

[DYNAMIC]

Working memory:
{
  "name": "Mohan",
  "budget": "50 lakhs",
  "location": "Hyderabad",
  "property_type": "2BHK"
}

Recent turns:
...

Current user message:
...
6. The LLM returns TWO things

This is the architecture you liked:

{
  "spoken_response": "హాయ్ మోహన్ గారు, హైదరాబాద్‌లో మీ 50 లక్షల బడ్జెట్‌కు సరిపోయే 2BHK options చూడొచ్చు.",
  "memory_update": {
    "operations": [
      {
        "action": "set",
        "field": "customer.name",
        "value": "Mohan"
      }
    ]
  }
}

The exact structured-output schema should be enforced through the API rather than relying on free-form model formatting.

7. Your server splits the output

Your backend receives the structured result.

Spoken response
హాయ్ మోహన్ గారు...

goes immediately to:

TTS
Memory update
{
  "operations": [...]
}

goes to:

Memory Manager

The Memory Manager merges it into the existing state.

8. Use operations instead of replacing the whole memory

This is an optimization I strongly recommend.

Don't make the LLM return:

{
  "name": "Mohan",
  "budget": "50 lakhs",
  "location": "Hyderabad"
}

every turn.

Instead return only changes:

{
  "memory_update": {
    "operations": [
      {
        "action": "add",
        "field": "requirements.locations",
        "value": "Bangalore"
      }
    ]
  }
}

Then your server performs:

existing memory
+
operations
=
new memory

This keeps the output smaller.

9. Example of memory evolution
Turn 1

User:

My name is Mohan.

{
  "customer": {
    "name": "Mohan"
  }
}
Turn 2

User:

I need around 50 lakhs.

{
  "customer": {
    "name": "Mohan"
  },
  "requirements": {
    "budget": ["50 lakhs"]
  }
}
Turn 3

User:

Hyderabad preferred.

{
  "customer": {
    "name": "Mohan"
  },
  "requirements": {
    "budget": ["50 lakhs"],
    "locations": ["Hyderabad"]
  }
}
Turn 4

User:

Bangalore is also fine.

Do NOT replace Hyderabad.

{
  "customer": {
    "name": "Mohan"
  },
  "requirements": {
    "budget": ["50 lakhs"],
    "locations": ["Hyderabad", "Bangalore"]
  }
}
Turn 5

User:

Actually Hyderabad is my first choice.

You can preserve both:

{
  "requirements": {
    "locations": [
      {
        "name": "Hyderabad",
        "priority": 1
      },
      {
        "name": "Bangalore",
        "priority": 2
      }
    ]
  }
}

This means your memory keeps the conversation's evolution instead of forgetting old information.

10. What the next LLM request contains

Suppose we're now at turn 10.

The full transcript might be:

3,000+ tokens

But your live request contains:

CACHED:
Platform brain
+
customer business brain
+
static rules

DYNAMIC:
Working memory ~150–300 tokens
+
last 1–2 turns
+
current user message

So the model knows:

Mohan
₹50L
Hyderabad
Bangalore alternative
2BHK
...

without receiving the whole 10-turn conversation again.

That is where your token savings come from.

11. Add a compact rolling summary

The JSON handles structured facts.

But some things don't fit naturally into fields.

For example:

“Mohan initially wanted Hyderabad, later considered Bangalore because his office might move. He prefers ready-to-move properties and is worried about parking.”

This belongs in:

important_context

or:

rolling_summary

Example:

{
  "rolling_summary": "Mohan is looking for a ready-to-move 2BHK around ₹50L. Hyderabad is preferred, but Bangalore is an alternative. Parking availability is important."
}

Keep this very small.

Approximately:

80–150 tokens

12. Don't generate a summary every turn

Use:

every 4–6 turns

or configurable interval.

And generate it asynchronously.

So:

LLM response
↓
TTS starts
↓
user hears response

meanwhile

rolling summary update

The caller never waits for the memory system.

13. The best memory structure

I would use something approximately like:

{
  "customer": {
    "name": "Mohan",
    "phone": null,
    "city": null
  },

  "requirements": {
    "budget": [
      {
        "value": "50 lakhs",
        "source": "user"
      }
    ],

    "locations": [
      {
        "name": "Hyderabad",
        "priority": 1
      },
      {
        "name": "Bangalore",
        "priority": 2
      }
    ],

    "property_types": [
      "2BHK"
    ],

    "timeline": null
  },

  "preferences": [
    "ready to move",
    "parking"
  ],

  "objections": [],

  "decisions": [],

  "important_context": [],

  "rolling_summary": "..."
}

Don't make this gigantic.

The goal is compressed conversational state, not another transcript.

14. Full transcript remains separate

Your server should simultaneously write:

data/calls/{call_id}/transcript.jsonl

with the complete text.

Example:

{"speaker":"user","text":"నా పేరు మోహన్."}
{"speaker":"agent","text":"హాయ్ మోహన్ గారు."}
{"speaker":"user","text":"నాకు 50 లక్షలలో property కావాలి."}
{"speaker":"agent","text":"ఏ location prefer చేస్తారు?"}
...

The full transcript is never sent to the live brain unless you specifically need it.

15. Audio is also separate

While the call is happening:

user PCM → server → user.pcm
agent TTS → server → agent.pcm

After the call:

user + agent
↓
mix.wav

So now you have:

memory
+
full transcript
+
audio
16. What happens after call completion

At hang-up:

FULL LEDGER
     ↓
Post-call LLM analysis
     ↓
outcome.json

The outcome can contain:

{
  "summary_te": "...",
  "summary_en": "...",
  "disposition": "interested",
  "confidence": 0.91,
  "next_action": "schedule site visit",
  "callback_time": null,
  "objections": ["parking"],
  "sentiment": "positive",
  "extracted": {
    "name": "Mohan",
    "city": "Hyderabad",
    "budget": "50 lakhs",
    "property_type": "2BHK"
  }
}

That is the final business result.

17. Your database should therefore have these layers

Conceptually:

CUSTOMER
│
├── Raw business prompt
├── Optimized business prompt
├── Business prompt version
│
└── CALLS
      │
      ├── Call 001
      │     ├── Working memory
      │     ├── Transcript
      │     ├── Audio
      │     └── Outcome
      │
      ├── Call 002
      │     ├── Working memory
      │     ├── Transcript
      │     ├── Audio
      │     └── Outcome
      │
      └── Call 003

This is much cleaner for your SaaS.

18. Prompt versioning is important

Use something like:

platform_brain_version = 8
customer_business_version = 14
compiled_brain_version = 8.14

If the customer edits their business prompt:

14 → 15

generate a new optimized prompt and new compiled brain.

Don't mutate the current live-call brain in the middle of a call.

Existing calls continue using the version they started with.

New calls use the new version.

That makes your system deterministic.

19. What is cached and what is NOT
Cached
Platform brain
+
Optimized customer business brain
+
Static instructions
Not cached/stable
Working memory
Recent turns
Current user input

OpenAI's prompt caching is based on repeated prefixes, so keeping this boundary stable is important.

20. The complete live request

Conceptually:

┌─────────────────────────────────────────────┐
│                  CACHED                     │
│                                             │
│ PLATFORM BRAIN                              │
│                                             │
│ CUSTOMER OPTIMIZED BUSINESS BRAIN           │
│                                             │
│ STATIC BEHAVIOR / SAFETY RULES              │
│                                             │
│ OUTPUT BEHAVIOR                             │
│                                             │
│ >>> CACHE BREAKPOINT <<<                    │
├─────────────────────────────────────────────┤
│                  DYNAMIC                    │
│                                             │
│ WORKING MEMORY                              │
│                                             │
│ ROLLING SUMMARY                             │
│                                             │
│ LAST 1–2 TURNS                              │
│                                             │
│ CURRENT USER MESSAGE                        │
└─────────────────────────────────────────────┘

Then:

LLM
↓
Structured output
├── spoken_response
└── memory_update.operations[]
21. The server's memory loop

This is the most important loop:

Turn N
  ↓
Receive STT transcript
  ↓
Send memory + recent context + current message
  ↓
LLM
  ↓
spoken_response + memory_update
  ↓
spoken_response → TTS
memory_update → merge
  ↓
save new memory
  ↓
Turn N+1
  ↓
send updated memory

So every turn gets the latest knowledge.

22. Token optimization hierarchy

I would optimize costs in this order:

Biggest optimization

Don't send full transcript every turn.

Second

Keep the platform + business brain stable and cached.

Third

Optimize customer's raw business instructions once.

Fourth

Keep working memory compact.

Fifth

Only include recent 1–2 turns.

Sixth

Use structured memory updates instead of returning the entire memory every turn.

Seventh

Run summaries asynchronously every few turns instead of every turn.

This is much more effective than trying to squeeze every possible word out of the main prompt.

23. One thing I would NOT do

Don't keep saying:

“This is the dynamic cache.”

Use these names in your code:

cached_brain_prompt
working_memory
rolling_summary
call_ledger

because they are actually different systems.

That naming will save you a lot of confusion when you build the backend.

24. Recommended backend modules

Based on the architecture in your uploaded specification, I'd organize it roughly like:

server/
├── agent/
│   ├── working_memory.py
│   ├── call_ledger.py
│   ├── call_audio.py
│   ├── instruction_builder.py
│   └── openai_brain_service.py
│
├── services/
│   ├── business_prompt_optimizer.py
│   ├── call_outcome.py
│   └── memory_manager.py
│
├── routes/
│   ├── calls.py
│   └── ws.py
│
└── storage/
    ├── business_prompts/
    └── calls/

You can adapt the exact module names to your existing repo rather than creating duplicate abstractions.

25. Cost picture

The goal is:

STABLE:
large prompt
↓
cached
↓
low recurring cost

DYNAMIC:
small memory
+
small recent context
+
current message
↓
uncached

The uploaded specification similarly estimates that adding working memory should only add a relatively small amount to live LLM cost, rather than turning each turn into a full-transcript request.

And because cache writes/reads themselves are billed at model-specific rates, reducing unnecessary stable-prompt tokens still has value. The exact pricing should be verified against the model you're actually using before implementing cost projections.



                         CUSTOMER
                            │
                            ▼
                 ┌────────────────────┐
                 │ Raw Business Prompt│
                 └─────────┬──────────┘
                           │
                     ONE-TIME AI
                    OPTIMIZATION
                           │
                           ▼
                 Optimized Business Brain
                           │
                           ▼
                 ┌───────────────────────┐
                 │      CACHED BRAIN     │
                 │                       │
                 │ Platform Brain        │
                 │ +                     │
                 │ Optimized Business    │
                 │ Brain                 │
                 │ +                     │
                 │ Static Output Rules   │
                 └───────────┬───────────┘
                             │
                      CACHE BREAKPOINT
                             │
                             ▼
                    ┌─────────────────┐
                    │ WORKING MEMORY  │
                    │                 │
                    │ JSON state      │
                    │ + summary       │
                    └────────┬────────┘
                             │
                    + last 1–2 turns
                    + current message
                             │
                             ▼
                         LLM / Luna
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
          spoken_response          memory_update
                 │                       │
                 ▼                       ▼
                TTS                 Memory Manager
                 │                       │
                 ▼                       ▼
               USER               Updated JSON
                                         │
                                         └──────→ NEXT TURN


Meanwhile:

USER AUDIO ───────────────┐
                          ▼
                    CALL LEDGER
                          ▲
AGENT AUDIO ──────────────┘

FULL TRANSCRIPT ──────────► CALL LEDGER


After call:

CALL LEDGER
     │
     ▼
POST-CALL LLM
     │
     ├── Telugu summary
     ├── English summary
     ├── disposition
     ├── next action
     ├── extracted information
     └── sentiment




     1. Biggest change: separate “Provider Configuration” from “Agent Brain Configuration”

Right now the document is very focused on:

STT
LLM
TTS

I would add another independent layer:

VOICE ENGINE
│
├── Provider configuration
│   ├── STT
│   ├── LLM
│   └── TTS
│
├── Brain configuration
│   ├── Platform brain
│   └── Customer business brain
│
└── Conversation state
    ├── Working memory
    ├── Rolling summary
    └── Recent turns

Why?

Because changing the LLM model should not require changing the business brain, and changing the customer's business prompt should not require touching the STT/TTS configuration.

Your current document already has a model registry and session-level configuration, which is good; I would extend that same concept to the brain itself.

2. Add a “compiled brain” layer

This is probably the biggest optimization I'd add.

Instead of constructing this on every call:

Platform prompt
+
Customer raw prompt
+
output instructions

do this once when the customer saves/updates their agent:

Customer raw business prompt
        ↓
Prompt optimizer
        ↓
Optimized business brain
        ↓
Platform brain
+
Optimized business brain
+
static rules
        ↓
COMPILED BRAIN VERSION

Store:

platform_brain_version
business_brain_version
compiled_brain_version
compiled_prompt

Then the live call uses the compiled prompt directly as the stable cached prefix.

This is better than having the live request assemble a large business prompt repeatedly.

3. Do NOT make the customer’s optimized prompt the only source of truth

Store both:

raw_business_prompt
optimized_business_prompt

The frontend always displays:

raw prompt

The backend uses:

optimized prompt

That way:

customer sees exactly what they entered
you can re-optimize later
you can compare original vs optimized
you can regenerate after optimizer improvements
you never lose the original business instructions

This is an important SaaS design improvement over simply overwriting the customer's prompt.

4. Add prompt versioning

Your current model configuration has ENV-based versioning implicitly, but the brain prompt also needs versioning.

Use something like:

platform_brain_version = 3
business_brain_version = 12
compiled_brain_version = 3.12

When the customer changes:

“We now sell villas too.”

don't alter the current live brain.

Instead:

business_brain_version 12 → 13
compiled_brain_version 3.13

New calls get version 13.

Existing calls continue using version 12.

This is extremely useful for debugging and reproducibility.