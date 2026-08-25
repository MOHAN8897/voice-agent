# Voice Agent — Configurable Model Tiers & Plugin Testing Framework

Analyze the **existing voice-agent codebase and current implementation first**. Do not rewrite or replace working functionality unnecessarily. Preserve the existing architecture, APIs, WebSocket behavior, audio pipeline, logging, session handling, and frontend functionality unless a change is required for this feature.

The goal is to convert the current voice agent into a **flexible model-combination testing framework** where STT, LLM, and TTS providers/models can be independently configured and tested.

---

## 1. Core Objective

The voice-agent pipeline should support interchangeable:

**STT → LLM → TTS**

providers/models.

The system must allow us to test different combinations of:

### STT

* Sarvam STT
* Cartesia Ink
* Any existing STT integrations already present in the codebase

### LLM

* Existing LLM models currently supported by the project
* DeepSeek V4
* OpenAI models currently supported
* Gemini models currently supported
* Any other already-integrated models

### TTS

* Sarvam Bulbul
* Cartesia Sonic
* Any existing TTS integrations already present in the codebase

Do not assume model names or APIs blindly. Inspect the existing implementation and provider documentation/configuration before modifying integrations.

---

# 2. Create Three Voice-Agent Quality Tiers

Create exactly three configurable voice-agent modes:

### LOW

Designed for:

* Lowest possible cost
* High-volume calling
* Acceptable conversational quality
* Fast response time

### MEDIUM

Designed for:

* Good balance between cost, latency and quality
* Production-quality conversations
* Better reasoning and natural responses than LOW

### PREMIUM

Designed for:

* Highest conversational quality
* Best Telugu/Indian-language experience
* Best STT accuracy
* Best TTS naturalness
* Best LLM intelligence
* Cost is secondary

Each tier must contain:

```text
STT provider + STT model
LLM provider + LLM model
TTS provider + TTS model
```

For example:

```env
VOICE_LOW_STT_PROVIDER=...
VOICE_LOW_STT_MODEL=...

VOICE_LOW_LLM_PROVIDER=...
VOICE_LOW_LLM_MODEL=...

VOICE_LOW_TTS_PROVIDER=...
VOICE_LOW_TTS_MODEL=...
```

Repeat the same structure for:

```env
VOICE_MEDIUM_*
VOICE_PREMIUM_*
```

Do not hard-code these combinations in frontend or backend source code.

---

# 3. DeepSeek V4 Integration

Add DeepSeek V4 as an available LLM provider/model option.

Use the provider's current API structure and preserve streaming if supported.

The configuration must be environment-driven:

```env
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=...
```

and the selected DeepSeek model should be configurable:

```env
DEEPSEEK_MODEL=...
```

Do not hard-code a DeepSeek model name throughout the application.

The model registry should make DeepSeek available alongside the existing LLM providers.

---

# 4. Model Registry

Create a central model/provider registry instead of scattering provider names throughout the code.

The registry should expose metadata such as:

```text
provider
model
type
display_name
enabled
supports_streaming
supports_realtime
language_support
pricing_metadata
```

Example conceptual structure:

```text
STT
 ├── Sarvam
 │    └── Saaras
 └── Cartesia
      └── Ink

LLM
 ├── OpenAI
 ├── Gemini
 └── DeepSeek
      └── V4

TTS
 ├── Sarvam
 │    └── Bulbul
 └── Cartesia
      └── Sonic
```

The registry must be extensible so additional providers/models can be added later without redesigning the frontend.

---

# 5. Environment-Controlled Mode

Create a master environment switch:

```env
VOICE_AGENT_CONFIG_MODE=env
```

Supported values:

```text
env
frontend
```

### When:

```env
VOICE_AGENT_CONFIG_MODE=env
```

The frontend must NOT expose individual STT/LLM/TTS configuration controls.

Instead, the frontend should show only:

```text
LOW
MEDIUM
PREMIUM
```

The actual provider/model combination for each tier is determined entirely by the `.env` configuration.

For example:

```env
VOICE_LOW_STT_PROVIDER=cartesia
VOICE_LOW_STT_MODEL=ink

VOICE_LOW_LLM_PROVIDER=deepseek
VOICE_LOW_LLM_MODEL=deepseek-v4-flash

VOICE_LOW_TTS_PROVIDER=cartesia
VOICE_LOW_TTS_MODEL=sonic-3.5
```

The frontend should simply show:

```text
LOW
₹ Estimated Cost: ...
STT: Configured
LLM: Configured
TTS: Configured
```

Do not expose configuration controls in this mode.

---

# 6. Frontend-Controlled Configuration Mode

When:

```env
VOICE_AGENT_CONFIG_MODE=frontend
```

the frontend should expose a model-testing/configuration interface.

Allow the developer to independently select:

### STT

```text
Provider
Model
```

### LLM

```text
Provider
Model
```

### TTS

```text
Provider
Model
```

The user should be able to construct combinations such as:

```text
Sarvam STT
+
DeepSeek V4
+
Cartesia Sonic
```

or:

```text
Cartesia Ink
+
GPT
+
Sarvam Bulbul
```

or:

```text
Sarvam STT
+
Gemini
+
Sarvam Bulbul
```

without changing the backend code.

---

# 7. Plugin Visibility

The frontend must NEVER display providers/models that are disabled or unavailable.

Create environment-level plugin switches such as:

```env
ENABLE_SARVAM_STT=true
ENABLE_CARTESIA_STT=true

ENABLE_OPENAI_LLM=true
ENABLE_GEMINI_LLM=true
ENABLE_DEEPSEEK_LLM=true

ENABLE_SARVAM_TTS=true
ENABLE_CARTESIA_TTS=true
```

If a plugin is:

```env
ENABLE_DEEPSEEK_LLM=false
```

then DeepSeek must disappear from the frontend completely.

Do not merely disable the button visually. The backend must also reject requests attempting to use a disabled provider/model.

---

# 8. API Keys

All provider API keys must remain server-side.

Never expose:

```text
OPENAI_API_KEY
GEMINI_API_KEY
DEEPSEEK_API_KEY
SARVAM_API_KEY
CARTESIA_API_KEY
```

to the browser.

The frontend should receive only safe configuration metadata.

Example:

```json
{
  "provider": "deepseek",
  "model": "v4-flash",
  "enabled": true,
  "supportsStreaming": true
}
```

Never return API keys.

---

# 9. Testing All Combinations

Build the architecture so I can test combinations systematically.

For example:

### Test A

```text
Sarvam STT
+
DeepSeek V4
+
Sarvam TTS
```

### Test B

```text
Sarvam STT
+
DeepSeek V4
+
Cartesia Sonic
```

### Test C

```text
Cartesia Ink
+
DeepSeek V4
+
Cartesia Sonic
```

### Test D

```text
Sarvam STT
+
Gemini
+
Sarvam TTS
```

### Test E

```text
Cartesia Ink
+
OpenAI
+
Cartesia Sonic
```

The system should make it easy to switch combinations without modifying application code.

---

# 10. Testing Metrics

For every test combination, collect useful metrics.

At minimum:

### STT

```text
STT latency
first transcript latency
transcription duration
final transcript latency
errors
```

### LLM

```text
time to first token
total generation latency
input tokens
output tokens
model used
errors
```

### TTS

```text
time to first audio
total generation latency
characters generated
audio duration
errors
```

### End-to-end

Calculate:

```text
User stops speaking
        ↓
STT final
        ↓
LLM first token
        ↓
TTS first audio
        ↓
User hears response
```

Record:

```text
End-to-end first-audio latency
Total response latency
```

This is extremely important because the goal is to determine which combination actually performs best for a real-time voice call.

---

# 11. Combination Score

Create a testing/benchmark result structure that can compare combinations based on:

```text
Cost
STT accuracy
LLM response quality
TTS naturalness
Time to first audio
Total latency
Error rate
Telugu quality
Conversation quality
```

Do NOT automatically declare a winner using arbitrary hard-coded weights.

Make the scoring weights configurable through environment variables or a configuration file.

For example:

```env
VOICE_SCORE_LATENCY_WEIGHT=...
VOICE_SCORE_COST_WEIGHT=...
VOICE_SCORE_QUALITY_WEIGHT=...
VOICE_SCORE_ACCURACY_WEIGHT=...
```

---

# 12. Configuration Priority

Implement configuration precedence clearly:

```text
ENV configuration
        ↓
Backend configuration resolver
        ↓
Frontend-safe configuration
        ↓
Voice-agent session
```

When `VOICE_AGENT_CONFIG_MODE=env`:

```text
ENV → selected tier → session
```

When `VOICE_AGENT_CONFIG_MODE=frontend`:

```text
ENV-enabled plugins
        ↓
Frontend selection
        ↓
Backend validation
        ↓
Session
```

The frontend must never be able to select a provider that the ENV has disabled.

---

# 13. Session-Level Configuration

Every voice-agent session should resolve its complete configuration at session start.

Example:

```json
{
  "mode": "premium",
  "stt": {
    "provider": "sarvam",
    "model": "saaras"
  },
  "llm": {
    "provider": "deepseek",
    "model": "v4"
  },
  "tts": {
    "provider": "cartesia",
    "model": "sonic"
  }
}
```

Log this configuration safely at session startup.

Do not log API keys.

---

# 14. Frontend UX

Create a clean developer/testing interface.

When ENV mode is enabled:

```text
VOICE AGENT

[ LOW ]
[ MEDIUM ]
[ PREMIUM ]
```

Selecting a tier should show:

```text
Current Configuration

STT
Sarvam Saaras

LLM
DeepSeek V4

TTS
Cartesia Sonic

[Start Test]
```

When frontend configuration mode is enabled:

```text
VOICE AGENT CONFIGURATION

STT
[ Provider ▼ ]
[ Model ▼ ]

LLM
[ Provider ▼ ]
[ Model ▼ ]

TTS
[ Provider ▼ ]
[ Model ▼ ]

[ Test Configuration ]
```

Only enabled providers/models should appear.

---

# 15. Do Not Break Existing Functionality

Before modifying anything:

1. Inspect the complete current voice-agent architecture.
2. Identify the existing STT integration.
3. Identify the existing TTS integration.
4. Identify the existing LLM integration.
5. Identify WebSocket/realtime streaming implementation.
6. Identify current environment variables.
7. Identify frontend configuration UI.
8. Identify current session lifecycle.
9. Identify logging/metrics.
10. Identify existing provider abstraction/interfaces.

Reuse existing abstractions wherever possible.

Do not duplicate existing provider logic.

Do not replace working WebSocket streaming implementations unnecessarily.

---

# 16. Backward Compatibility

Existing ENV variables and existing voice-agent functionality should continue working.

If the new configuration system is not configured, the application should fall back to the existing configuration rather than breaking.

Document every newly introduced ENV variable.

Create/update:

```text
.env.example
```

with clear descriptions.

---

# 17. Final Developer Configuration Example

The final system should support a configuration similar to:

```env
# ==========================================
# VOICE AGENT
# ==========================================

VOICE_AGENT_CONFIG_MODE=env

# ==========================================
# ENABLED PLUGINS
# ==========================================

ENABLE_SARVAM_STT=true
ENABLE_CARTESIA_STT=true

ENABLE_OPENAI_LLM=true
ENABLE_GEMINI_LLM=true
ENABLE_DEEPSEEK_LLM=true

ENABLE_SARVAM_TTS=true
ENABLE_CARTESIA_TTS=true

# ==========================================
# LOW
# ==========================================

VOICE_LOW_STT_PROVIDER=cartesia
VOICE_LOW_STT_MODEL=ink

VOICE_LOW_LLM_PROVIDER=deepseek
VOICE_LOW_LLM_MODEL=<configured-v4-model>

VOICE_LOW_TTS_PROVIDER=sarvam
VOICE_LOW_TTS_MODEL=<configured-bulbul-model>

# ==========================================
# MEDIUM
# ==========================================

VOICE_MEDIUM_STT_PROVIDER=sarvam
VOICE_MEDIUM_STT_MODEL=<configured-saaras-model>

VOICE_MEDIUM_LLM_PROVIDER=gemini
VOICE_MEDIUM_LLM_MODEL=<configured-gemini-model>

VOICE_MEDIUM_TTS_PROVIDER=cartesia
VOICE_MEDIUM_TTS_MODEL=<configured-sonic-model>

# ==========================================
# PREMIUM
# ==========================================

VOICE_PREMIUM_STT_PROVIDER=sarvam
VOICE_PREMIUM_STT_MODEL=<configured-saaras-model>

VOICE_PREMIUM_LLM_PROVIDER=openai
VOICE_PREMIUM_LLM_MODEL=<configured-openai-model>

VOICE_PREMIUM_TTS_PROVIDER=cartesia
VOICE_PREMIUM_TTS_MODEL=<configured-sonic-model>
```

Do not blindly use these example combinations as the final recommended combinations. The purpose of the implementation is to make them configurable so they can be benchmarked.

---

# 18. Deliverables

After implementation, provide:

### A. Architecture summary

Explain:

```text
Frontend
↓
Configuration resolver
↓
STT
↓
LLM
↓
TTS
↓
Audio
```

### B. All new ENV variables

Provide a complete table.

### C. Supported plugins

Show:

```text
STT
LLM
TTS
```

and which are enabled.

### D. Three tier configurations

Show the currently configured:

```text
LOW
MEDIUM
PREMIUM
```

combinations.

### E. Testing matrix

Provide a matrix of all currently enabled STT × LLM × TTS combinations that can be tested.

### F. Changes made

List every backend/frontend/configuration change.

### G. Validation

Run the existing tests and add tests for:

* provider selection
* ENV configuration
* frontend configuration
* disabled providers
* invalid provider/model
* DeepSeek integration
* session configuration resolution
* streaming
* API-key security
* fallback behavior

Do not claim a test passed unless it was actually executed.

---

## Important Implementation Principle

**The voice agent must become provider-agnostic.**

The core pipeline should not care whether the current session uses:

```text
Sarvam
Cartesia
OpenAI
Gemini
DeepSeek
```

It should only interact with standardized interfaces:

```text
STT interface
LLM interface
TTS interface
```

Provider-specific implementation must live behind those interfaces.

This will allow us to continuously test and fine-tune different:

**STT + LLM + TTS**

combinations without rewriting the voice-agent core.


cartesia documentation : https://docs.cartesia.ai/get-started/overview

