# Critical Telnyx PSTN files (for ChatGPT)

Copied from D:\voice agent on 2026-09-09

| Copied name | Original path |
|-------------|---------------|
| services__telnyx_pstn_bridge.py | server/services/telnyx_pstn_bridge.py |
| services__pstn_voice_core.py | server/services/pstn_voice_core.py |
| routes__telnyx.py | server/routes/telnyx.py |
| routes__telnyx_ws.py | server/routes/telnyx_ws.py |
| services__telnyx_client.py | server/services/telnyx_client.py |
| services__telnyx_webhook_verify.py | server/services/telnyx_webhook_verify.py |
| services__audio_transcode.py | server/services/audio_transcode.py |
| services__pstn_media_flow.py | server/services/pstn_media_flow.py |
| config__env.py | server/config/env.py |
| server__app.py | server/app.py |
| TELNYX_PSTN_FULL_FLOW_AUDIT.md | TELNYX_PSTN_FULL_FLOW_AUDIT.md |

Flow: webhook (telnyx.py + webhook_verify) -> start_streaming (telnyx_client) -> WS (telnyx_ws) -> bridge (telnyx_pstn_bridge) -> voice loop (pstn_voice_core) + audio_transcode.
