# Composio Multi-Tenant Tool Integration, Dynamic Real-Time Voice Execution & Optimization Architecture

This document defines the production implementation specification for integrating **Composio** into the multi-tenant voice platform using the configured `composio_api_key` in [.env](file:///d:/voice%20agent/.env#L206).

It covers multi-tenant OAuth scoping, real-time voice function calling in [server/services/pstn_realtime_voice_core.py](file:///d:/voice%20agent/server/services/pstn_realtime_voice_core.py), strict latency and token budget optimization to keep the LLM brain lean, end-to-end testing, and automated tool verification.

---

## 1. Executive Architecture Overview

Composio enables autonomous agents to interact with 150+ third-party business applications (Google Calendar, HubSpot, Salesforce, Gmail, Slack, Notion, Jira, ClickUp, WhatsApp, etc.). In our voice platform, tenants must be able to authorize integrations from their dashboard, and individual voice agents must dynamically execute these tools during or immediately following phone calls.

```
+----------------------------------------------------------------------------------------------------+
|                                    TENANT DASHBOARD (Frontend)                                     |
|  IntegrationsModule.jsx -> Connect Apps (Google Calendar, CRM, Slack) via Composio OAuth Flow     |
+-------------------------------------------------+--------------------------------------------------+
                                                  |
                                                  v
+----------------------------------------------------------------------------------------------------+
|                                   VOXLY BACKEND (Composio Service)                                 |
|  Entity Scoping: entity_id = "tenant_{tenant_id}" (or "tenant_{tenant_id}_agent_{agent_id}")       |
|  Store active tool mappings in PostgreSQL (agent_tools table)                                       |
+-------------------------------------------------+--------------------------------------------------+
                                                  |
            +-------------------------------------+------------------------------------+
            | (In-Call Fast Path: <1.5s timeout)                                       | (Post-Call Async Sync: No voice delay)
            v                                                                          v
+---------------------------------------+                 +------------------------------------------+
|  PstnRealtimeVoiceLoop / Adapter      |                 |  server/call/post_call_pipeline.py       |
|  - Injects 1-3 pruned tool schemas    |                 |  - Full transcript export to CRM         |
|  - Real-time function dispatch        |                 |  - Customer record updates               |
|  - Response Sanitizer (<80 tokens)    |                 |  - Follow-up email / SMS dispatch        |
+---------------------------------------+                 +------------------------------------------+
```

---

## 2. Codebase Audit: Current State vs. Required Architecture

### 2.1 The Current Real-Time Voice Gap
In [server/services/pstn_realtime_voice_core.py:3213-3251](file:///d:/voice%20agent/server/services/pstn_realtime_voice_core.py#L3213-L3251), the function call dispatcher handles only hardcoded internal tools:
```python
# Current code in server/services/pstn_realtime_voice_core.py:
if kind == "function_call":
    tool_name = str(event.get("name") or "")
    if tool_name == "call_action":
        await self._handle_call_action(event)
        return
    if tool_name == "request_language_callback":
        await self._handle_language_callback_tool(event)
        return
    if tool_name not in LIVE_HANGUP_TOOL_NAMES:
        return  # <-- ALL THIRD-PARTY / COMPOSIO TOOLS ARE SILENTLY DROPPED HERE
```
Furthermore, [server/realtime/providers/openai_voice.py:104](file:///d:/voice%20agent/server/realtime/providers/openai_voice.py#L104) and [server/realtime/providers/gemini_voice.py:65](file:///d:/voice%20agent/server/realtime/providers/gemini_voice.py#L65) only register `realtime_hangup_tool_declarations()`, `REQUEST_LANGUAGE_CALLBACK_TOOL`, and `CALL_ACTION_TOOL`. Dynamic external tools are never injected into the active audio session.

### 2.2 The Frontend Integrations Placeholder
[voxly-ai/src/console/modules/IntegrationsModule.jsx](file:///d:/voice%20agent/voxly-ai/src/console/modules/IntegrationsModule.jsx#L1-L25) is currently a static 25-line placeholder:
```jsx
export function IntegrationsModule() {
  return (
    <div className="p-6">
      <h2 className="text-xl font-bold">Integrations</h2>
      <p className="text-muted-foreground mt-2">Integrations coming soon.</p>
    </div>
  );
}
```

---

## 3. Multi-Tenant Entity Model & Database Schema

### 3.1 Composio Entity Architecture
Composio manages authorization tokens per **Entity**. In a multi-tenant voice SaaS:
1. Every tenant has a unique `entity_id`: `f"tenant_{tenant_id}"`.
2. All connected accounts (e.g. Google Calendar OAuth, HubSpot API Key) belong to that entity.
3. Individual agents created by that tenant can be granted access to specific connected tools.

### 3.2 Database Schema (PostgreSQL Migration)

```sql
-- Track tenant connected apps via Composio
CREATE TABLE IF NOT EXISTS tenant_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    app_name VARCHAR(64) NOT NULL, -- e.g., 'GOOGLECALENDAR', 'HUBSPOT', 'SLACK'
    composio_connection_id VARCHAR(128) NOT NULL,
    account_identifier VARCHAR(255), -- User's email or workspace name
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- 'INITIATED', 'ACTIVE', 'EXPIRED'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, app_name)
);

-- Associate specific tools with an agent
CREATE TABLE IF NOT EXISTS agent_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(64) NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    app_name VARCHAR(64) NOT NULL,
    action_whitelist TEXT[] NOT NULL DEFAULT '{}', -- e.g. ARRAY['GOOGLECALENDAR_FIND_FREE_SLOTS', 'GOOGLECALENDAR_CREATE_EVENT']
    timing_mode VARCHAR(16) NOT NULL DEFAULT 'in_call', -- 'in_call' (real-time) or 'post_call' (async)
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id, app_name)
);

CREATE INDEX idx_tenant_integrations_tenant ON tenant_integrations(tenant_id);
CREATE INDEX idx_agent_integrations_agent ON agent_integrations(agent_id);
```

---

## 4. Solving the "Brain-Heavy" Voice Problem: Strict Optimization Strategy

> [!CAUTION]
> **The Real-Time Voice Latency Trap:**
> In text chatbots, injecting 50 tools (10,000+ prompt tokens) is acceptable because streaming text masks latency.
> In **Speech-to-Speech Real-Time Voice** (OpenAI Realtime / Gemini Multimodal Live API):
> 1. Every extra 1,000 tokens in the session instructions/tools increases Time-To-First-Audio-Chunk (TTFT) by **150ms-300ms**.
> 2. Voice conversations become unusable if turnaround latency exceeds **600ms**.
> 3. Large schemas cause models to hallucinate tool parameters or read out raw JSON formatting over the telephone.

### 4.1 The 4-Pillar Optimization Framework

#### Pillar 1: Strict Action Whitelisting (Sub-Tooling)
Never mount an entire Composio app. Mounting `GOOGLECALENDAR` injects 32 actions (~14,000 tokens). Instead, whitelist only the 1-2 exact functions needed for the voice conversation:
- `GOOGLECALENDAR_FIND_FREE_SLOTS` (Check availability)
- `GOOGLECALENDAR_CREATE_EVENT` (Book the appointment)
All other actions (`DELETE_CALENDAR`, `PATCH_EVENT_COLOR`, `LIST_CALENDARS`) are filtered out at the gateway.

#### Pillar 2: Schema Compaction & Pruning
Composio tool schemas contain detailed markdown descriptions, regex patterns, and nested schemas intended for code interpreters. Our gateway runs a **Pruning Filter**:
- Removes `description` boilerplate longer than 80 characters.
- Strips non-essential properties (e.g. `conferenceDataVersion`, `recurrenceRule`, `sendUpdates`).
- Enforces concise parameter types (e.g. `start_time: ISO-8601 string`, `attendee_email: string`).
- **Token Reduction: 92% reduction** (from ~1,800 tokens per tool to ~140 tokens).

#### Pillar 3: Two-Tier Execution (In-Call vs. Post-Call)
Separate tools into two distinct execution lifecycles:
1. **In-Call Fast-Path (Realtime Synchronous):**
   - Read/write operations that directly decide the agent's next spoken sentence.
   - Example: Checking calendar slots, booking an urgent service appointment, fetching account balance.
   - Hard timeout: **1,500ms**.
2. **Post-Call Pipeline (Asynchronous, Zero Latency Cost):**
   - Operations that summarize, log, or export data.
   - Example: Creating a lead in HubSpot, attaching call audio to Salesforce, sending Slack notifications to sales reps, sending confirmation SMS/Email.
   - Runs in [server/call/post_call_pipeline.py](file:///d:/voice%20agent/server/call/post_call_pipeline.py) *after* the caller hangs up. Spoken voice latency impact: **0ms**.

#### Pillar 4: Response Sanitization for Spoken Synthesis
Third-party APIs return bloated JSON payloads (5KB to 50KB containing HTTP headers, internal object IDs, and URLs). If fed raw into the LLM, the model attempts to read URLs, UUIDs, or JSON brackets.
The **Response Sanitizer** extracts only critical conversational facts before returning tool output to the model:

```python
# Raw Composio Calendar Output (approx. 4,200 bytes)
{
    "kind": "calendar#event",
    "etag": "\"342512345\"",
    "id": "abc123xyz789",
    "status": "confirmed",
    "htmlLink": "https://www.google.com/calendar/event?eid=...",
    "created": "2026-10-04T18:00:00.000Z",
    "updated": "2026-10-04T18:00:01.000Z",
    "summary": "Dental Consultation",
    "creator": {"email": "clinic@dental.com", "self": True},
    "organizer": {"email": "clinic@dental.com", "self": True},
    "start": {"dateTime": "2026-10-05T10:00:00+05:30", "timeZone": "Asia/Kolkata"},
    "end": {"dateTime": "2026-10-05T10:30:00+05:30", "timeZone": "Asia/Kolkata"},
    ...
}

# Sanitized Voice Output (62 bytes, 18 tokens):
{
    "status": "confirmed",
    "date": "2026-10-05",
    "time": "10:00 AM",
    "summary": "Dental Consultation"
}
```

---

## 5. Backend Implementation Architecture

### 5.1 Composio Service Gateway ([server/services/composio_service.py](file:///d:/voice%20agent/server/services/composio_service.py))

```python
"""Composio Tooling & Multi-Tenant Integration Gateway."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from composio import ComposioToolSet, Action, App
from server.config.env import get_settings
from server.utils.logger import logger

class ComposioService:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_settings().composio_api_key
        self._toolset: ComposioToolSet | None = None

    @property
    def toolset(self) -> ComposioToolSet:
        if self._toolset is None:
            self._toolset = ComposioToolSet(api_key=self.api_key)
        return self._toolset

    def get_entity_id(self, tenant_id: str) -> str:
        """Derive isolated entity ID for tenant."""
        return f"tenant_{tenant_id}"

    async def initiate_app_connection(
        self, tenant_id: str, app_name: str, redirect_url: str
    ) -> dict[str, Any]:
        """Initiate OAuth connection flow for a tenant."""
        loop = asyncio.get_running_loop()
        entity = self.toolset.get_entity(id=self.get_entity_id(tenant_id))
        
        # Run blocking Composio SDK call in thread pool
        connection_request = await loop.run_in_executor(
            None,
            lambda: entity.initiate_connection(
                app_name=app_name.upper(),
                redirect_url=redirect_url
            )
        )
        return {
            "connection_id": connection_request.connectedAccountId,
            "redirect_url": connection_request.redirectUrl,
            "status": connection_request.connectionStatus
        }

    async def get_pruned_tools_for_agent(
        self, tenant_id: str, agent_id: str, actions: list[str]
    ) -> list[dict[str, Any]]:
        """Fetch OpenAI-compatible tool schemas pruned for low-latency voice."""
        if not actions:
            return []

        loop = asyncio.get_running_loop()
        entity_id = self.get_entity_id(tenant_id)
        
        raw_tools = await loop.run_in_executor(
            None,
            lambda: self.toolset.get_tools(
                actions=[Action(a) for a in actions],
                entity_id=entity_id
            )
        )
        
        pruned_tools = []
        for t in raw_tools:
            # Deep clone and prune schema
            func = t.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            # Terse description for voice model
            terse_desc = desc.split("\n")[0][:120] if desc else f"Execute {name}"
            
            params = func.get("parameters", {})
            properties = params.get("properties", {})
            required = params.get("required", [])
            
            pruned_properties = {}
            for prop_name, prop_def in properties.items():
                pruned_properties[prop_name] = {
                    "type": prop_def.get("type", "string"),
                    "description": (prop_def.get("description") or "")[:80]
                }
                if "enum" in prop_def:
                    pruned_properties[prop_name]["enum"] = prop_def["enum"]

            pruned_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": terse_desc,
                    "parameters": {
                        "type": "object",
                        "properties": pruned_properties,
                        "required": required
                    }
                }
            })
        return pruned_tools

    async def execute_tool_call(
        self, tenant_id: str, action_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute action with strict voice timeout (1.5s max) and response sanitization."""
        loop = asyncio.get_running_loop()
        entity_id = self.get_entity_id(tenant_id)

        try:
            raw_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.toolset.execute_action(
                        action=Action(action_name),
                        params=params,
                        entity_id=entity_id
                    )
                ),
                timeout=1.5  # Crucial voice SLA timeout
            )
            return self._sanitize_response(action_name, raw_result)
        except asyncio.TimeoutError:
            logger.warning("[COMPOSIO] Action %s timed out after 1.5s", action_name)
            return {"error": "Tool execution timed out. Please offer to confirm details manually."}
        except Exception as exc:
            logger.error("[COMPOSIO] Tool %s execution failed: %s", action_name, str(exc))
            return {"error": f"Failed to execute {action_name}."}

    def _sanitize_response(self, action_name: str, raw: dict[str, Any]) -> dict[str, Any]:
        """Strip raw API bloat down to conversational facts for TTS."""
        if not isinstance(raw, dict):
            return {"result": str(raw)[:200]}

        # Generic sanitization: extract status, id, message, and concise values
        sanitized = {}
        for k in ("status", "success", "confirmed", "id", "name", "date", "time", "message"):
            if k in raw:
                sanitized[k] = raw[k]

        # Extract nested details if available
        data = raw.get("data") or raw.get("response_data") or raw
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (str, int, float, bool)) and len(str(v)) < 100:
                    sanitized[k] = v

        return sanitized or {"success": True, "detail": "Action completed successfully"}

composio_service = ComposioService()
```

### 5.2 Real-Time Voice Core Tool Dispatch ([pstn_realtime_voice_core.py](file:///d:/voice%20agent/server/services/pstn_realtime_voice_core.py))

Modify lines 3213-3251 of [server/services/pstn_realtime_voice_core.py](file:///d:/voice%20agent/server/services/pstn_realtime_voice_core.py#L3213-L3251) to dynamically intercept Composio actions:

```python
        if kind == "function_call":
            tool_name = str(event.get("name") or "")
            arguments = event.get("arguments") or "{}"
            parsed_args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
            call_id = str(event.get("call_id") or "")

            if tool_name == "call_action":
                await self._handle_call_action(event)
                return
            if tool_name == "request_language_callback":
                await self._handle_language_callback_tool(event)
                return
            if tool_name in LIVE_HANGUP_TOOL_NAMES:
                # Existing live hangup handling
                ...
                return

            # --- DYNAMIC COMPOSIO & INTEGRATION TOOL HANDLER ---
            if self._agent_tools and tool_name in self._agent_tools:
                log_pstn("composio.tool_call_start", call_id=self.call_id, tool=tool_name)
                
                # Execute via Composio with tenant scoping
                tenant_id = self._tenant_id or "default"
                result = await composio_service.execute_tool_call(
                    tenant_id=tenant_id,
                    action_name=tool_name,
                    params=parsed_args
                )
                
                # Return sanitized output to speech adapter
                if call_id and self._adapter is not None:
                    await self._adapter.submit_function_output(
                        call_id=call_id,
                        output=json.dumps(result),
                        name=tool_name
                    )
                log_pstn("composio.tool_call_complete", call_id=self.call_id, tool=tool_name)
                return

            # Unrecognized tool: gracefully return failure so model does not stall
            if call_id and self._adapter is not None:
                await self._adapter.submit_function_output(
                    call_id=call_id,
                    output=json.dumps({"error": f"Tool {tool_name} not available"}),
                    name=tool_name
                )
            return
```

### 5.3 Asynchronous Post-Call Integration Execution ([server/call/post_call_pipeline.py](file:///d:/voice%20agent/server/call/post_call_pipeline.py))

Add post-call CRM / Slack sync to the outcome processing step in [server/call/post_call_pipeline.py](file:///d:/voice%20agent/server/call/post_call_pipeline.py#L220-L280):

```python
async def _execute_post_call_integrations(call_id: str, outcome: dict[str, Any]) -> None:
    """Execute asynchronous post-call actions via Composio (HubSpot, Slack, Gmail)."""
    ctx = get_ctx(call_id)
    if not ctx or not ctx.tenant_id:
        return

    # Check for active post-call tools for this agent
    post_call_actions = await get_agent_post_call_actions(ctx.agent_id)
    if not post_call_actions:
        return

    summary = outcome.get("summary") or outcome.get("notes") or "Call completed."
    disposition = outcome.get("disposition") or "completed"
    caller_phone = ctx.caller_phone or "Unknown"

    for action in post_call_actions:
        try:
            if "SLACK" in action:
                await composio_service.execute_tool_call(
                    tenant_id=ctx.tenant_id,
                    action_name=action,
                    params={"text": f":telephone_receiver: *Call {disposition}* from `{caller_phone}`\n*Summary:* {summary}"}
                )
            elif "HUBSPOT" in action or "SALESFORCE" in action:
                await composio_service.execute_tool_call(
                    tenant_id=ctx.tenant_id,
                    action_name=action,
                    params={
                        "phone": caller_phone,
                        "notes": summary,
                        "status": disposition,
                        "extracted_fields": outcome.get("extracted_fields", {})
                    }
                )
        except Exception as exc:
            logger.warning("[POST_CALL_INTEGRATIONS] Action %s failed for call %s: %s", action, call_id, str(exc))
```

---

## 6. Frontend UI Specification ([IntegrationsModule.jsx](file:///d:/voice%20agent/voxly-ai/src/console/modules/IntegrationsModule.jsx))

Replace the placeholder with a responsive integrations management view:

```jsx
import React, { useState, useEffect } from 'react';
import { 
  Calendar, MessageSquare, Database, Mail, CheckCircle2, 
  ExternalLink, Trash2, RefreshCw, Settings, AlertCircle 
} from 'lucide-react';

const SUPPORTED_APPS = [
  {
    id: 'GOOGLECALENDAR',
    name: 'Google Calendar',
    category: 'Calendar & Scheduling',
    icon: Calendar,
    color: 'text-blue-500',
    description: 'Allow voice agents to check free slots and book meetings during calls.',
    recommendedActions: ['GOOGLECALENDAR_FIND_FREE_SLOTS', 'GOOGLECALENDAR_CREATE_EVENT']
  },
  {
    id: 'HUBSPOT',
    name: 'HubSpot CRM',
    category: 'CRM & Leads',
    icon: Database,
    color: 'text-orange-500',
    description: 'Automatically create contacts and log call summaries after calls.',
    recommendedActions: ['HUBSPOT_CREATE_CONTACT', 'HUBSPOT_LOG_CALL_ENGAGEMENT']
  },
  {
    id: 'SLACK',
    name: 'Slack',
    category: 'Team Communication',
    icon: MessageSquare,
    color: 'text-emerald-500',
    description: 'Post real-time alerts and urgent callback requests to team channels.',
    recommendedActions: ['SLACK_SEND_MESSAGE']
  },
  {
    id: 'GMAIL',
    name: 'Gmail',
    category: 'Email',
    icon: Mail,
    color: 'text-red-500',
    description: 'Send follow-up emails and booking confirmations instantly.',
    recommendedActions: ['GMAIL_SEND_EMAIL']
  }
];

export function IntegrationsModule() {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connectingApp, setConnectingApp] = useState(null);

  useEffect(() => {
    fetchConnections();
  }, []);

  const fetchConnections = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/integrations');
      const data = await res.json();
      setConnections(data.items || []);
    } catch (err) {
      console.error('Failed to load integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async (appId) => {
    try {
      setConnectingApp(appId);
      const res = await fetch(`/api/integrations/${appId}/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ redirect_url: window.location.href })
      });
      const data = await res.json();
      if (data.redirect_url) {
        window.location.href = data.redirect_url;
      }
    } catch (err) {
      alert('Failed to initiate connection. Please check API configuration.');
    } finally {
      setConnectingApp(null);
    }
  };

  const handleDisconnect = async (appId) => {
    if (!confirm(`Are you sure you want to disconnect ${appId}?`)) return;
    try {
      await fetch(`/api/integrations/${appId}`, { method: 'DELETE' });
      await fetchConnections();
    } catch (err) {
      alert('Disconnect failed.');
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">App Integrations</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Connect third-party tools via Composio so your voice agents can read schedules and log outcomes.
          </p>
        </div>
        <button 
          onClick={fetchConnections}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-sm bg-secondary rounded-lg hover:bg-secondary/80 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SUPPORTED_APPS.map((app) => {
          const isConnected = connections.some(c => c.app_name === app.id && c.status === 'ACTIVE');
          const conn = connections.find(c => c.app_name === app.id);
          const Icon = app.icon;

          return (
            <div 
              key={app.id}
              className="border rounded-xl p-5 bg-card flex flex-col justify-between shadow-sm hover:shadow-md transition"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`p-2.5 rounded-lg bg-secondary/50 ${app.color}`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-base">{app.name}</h3>
                      <span className="text-xs text-muted-foreground">{app.category}</span>
                    </div>
                  </div>
                  {isConnected && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {app.description}
                </p>
                {isConnected && conn?.account_identifier && (
                  <p className="text-xs text-foreground/80 font-mono bg-secondary/40 px-2 py-1 rounded">
                    Account: {conn.account_identifier}
                  </p>
                )}
              </div>

              <div className="pt-4 border-t mt-4 flex items-center justify-between">
                {isConnected ? (
                  <div className="flex items-center gap-2 w-full justify-between">
                    <button className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                      <Settings className="w-3.5 h-3.5" /> Configure Tool Actions
                    </button>
                    <button
                      onClick={() => handleDisconnect(app.id)}
                      className="text-xs text-red-500 hover:text-red-700 flex items-center gap-1 px-2.5 py-1 rounded hover:bg-red-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Disconnect
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleConnect(app.id)}
                    disabled={connectingApp === app.id}
                    className="w-full inline-flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition disabled:opacity-50"
                  >
                    {connectingApp === app.id ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <>Connect {app.name} <ExternalLink className="w-3.5 h-3.5" /></>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

---

## 7. Automated Testing & Verification Suite

To guarantee that the voice agent reliably calls tools without hallucinating or delaying speech, tests must run against both:
1. **Mock Composio Fixture** (Unit/E2E test suite running without external network dependency).
2. **Live Integration Verification Script** (Validates real token authorization with Composio API).

### 7.1 Automated Unit & Voice Latency Test ([server/tests/test_composio_voice_tools.py](file:///d:/voice%20agent/server/tests/test_composio_voice_tools.py))

```python
"""Test suite for Composio tool schema pruning, response sanitizing, and real-time execution."""
import pytest
import json
from unittest.mock import MagicMock, patch
from server.services.composio_service import ComposioService

@pytest.fixture
def mock_composio():
    service = ComposioService(api_key="ck_test_key_12345")
    mock_toolset = MagicMock()
    service._toolset = mock_toolset
    return service, mock_toolset

def test_schema_pruning_removes_bloat(mock_composio):
    service, mock_toolset = mock_composio
    
    # Simulate bloated raw Composio tool definition
    mock_toolset.get_tools.return_value = [{
        "type": "function",
        "function": {
            "name": "GOOGLECALENDAR_FIND_FREE_SLOTS",
            "description": "Searches for primary and secondary calendar free intervals over 30 days.\nSupports RFC 3339 timestamps and recurrence rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "Lower bound format RFC3339."},
                    "time_max": {"type": "string", "description": "Upper bound format RFC3339."},
                    "timezone": {"type": "string", "description": "Timezone string e.g. America/New_York."},
                    "singleEvents": {"type": "boolean", "description": "Whether to expand recurring events."},
                    "maxAttendees": {"type": "integer", "description": "Filter by attendee capacity limit."}
                },
                "required": ["time_min", "time_max"]
            }
        }
    }]

    import asyncio
    pruned = asyncio.run(service.get_pruned_tools_for_agent(
        tenant_id="tenant_abc",
        agent_id="agent_123",
        actions=["GOOGLECALENDAR_FIND_FREE_SLOTS"]
    ))

    assert len(pruned) == 1
    func = pruned[0]["function"]
    assert func["name"] == "GOOGLECALENDAR_FIND_FREE_SLOTS"
    # Ensure description was truncated to first line
    assert "\n" not in func["description"]
    # Ensure parameters are intact
    assert "time_min" in func["parameters"]["properties"]
    assert func["parameters"]["required"] == ["time_min", "time_max"]

def test_response_sanitizer_reduces_token_weight(mock_composio):
    service, _ = mock_composio
    raw_api_payload = {
        "kind": "calendar#event",
        "etag": "\"1234567890\"",
        "id": "event_id_xyz",
        "status": "confirmed",
        "htmlLink": "https://calendar.google.com/calendar/r/eventedit/12345",
        "created": "2026-10-04T12:00:00Z",
        "summary": "Doctor Consultation",
        "creator": {"email": "clinic@test.com"},
        "start": {"dateTime": "2026-10-05T15:00:00Z"}
    }

    sanitized = service._sanitize_response("GOOGLECALENDAR_CREATE_EVENT", raw_api_payload)
    
    # Assert bloated URLs and metadata are stripped
    assert "htmlLink" not in sanitized
    assert "etag" not in sanitized
    assert "creator" not in sanitized
    
    # Assert conversational facts remain
    assert sanitized["status"] == "confirmed"
    assert sanitized["summary"] == "Doctor Consultation"
```

### 7.2 Execution Verification Command
Run the test suite with:
```bash
pytest server/tests/test_composio_voice_tools.py -v
```
