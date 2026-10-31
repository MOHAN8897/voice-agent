// Isolated UI harness only. Never imported by the application or production API.
import http from 'node:http';
let stack = { pipeline: 'realtime_voice', language: 'te-IN', llm: { provider: 'gemini', model: 'gemini-3.8-live' }, realtime_voice: { voice: 'Zephyr' }, transcription: { live_enabled: true, post_call_enabled: false, live_model: 'gpt-4o-mini-transcribe' } };
const credentials = { openai: { configured: true }, sarvam: { configured: true }, gemini: { enabled: true, configured: true, ready: true } };
http.createServer(async (req, res) => {
  let response = { ok: true, authenticated: true, subject: 'isolated-admin', csrf_token: 'isolated-csrf', providers: [], tiers: [] };
  if (req.url === '/api/dev/stack/saas-phone') {
    if (req.method === 'PUT') {
      let body = '';
      for await (const chunk of req) body += chunk;
      try { stack = JSON.parse(body).stackOverride; }
      catch { res.writeHead(400).end(); return; }
    }
    response = { ok: true, saved: { stack_override: stack }, resolved: stack, credentials, warnings: [], adjustments: [], voices: [] };
  } else if (req.url === '/api/dev/telephony/status') response = { active_provider: 'vobiz', active_ready: true, providers: [] };
  res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify(response));
}).listen(8018, '127.0.0.1');
