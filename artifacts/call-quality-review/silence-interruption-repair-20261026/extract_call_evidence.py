"""Keep call-control evidence only; no phone numbers or credentials."""
import collections
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
lines = (ROOT / 'data/dev-logs/codex-capabilities-api-runtime.stdout.log').read_text(encoding='utf-8', errors='replace').splitlines()
call_ids = ['bdb7fe33-b962-4c79-aa98-0621875bca91', '92064910-e19a-46e5-ba19-420cd8041154']
records = []
keep = {'TURN_START', 'TURN_END', 'stt.transcript', 'stt.echo_drop', 'BARGE_TRIGGER',
        'PSTN_BARGE_FINAL', 'THINK_CANCEL', 'turn.cancelled', 'turn.error', 'llm.incomplete'}
for cid in call_ids:
    base = ROOT / 'data/calls' / cid
    meta = json.loads((base / 'meta.json').read_text(encoding='utf-8'))
    transcript = [json.loads(line) for line in (base / 'transcript.jsonl').read_text(encoding='utf-8').splitlines() if line]
    events = []
    for number, line in enumerate(lines, 1):
        if cid not in line:
            continue
        match = re.search(r'\[PSTN\] (\S+)', line)
        if match and match[1] in keep:
            events.append({'time': line[:19], 'event': match[1], 'source_log_line': number})
    records.append({'call_id': cid, 'started_at': meta['started_at'], 'ended_at': meta['ended_at'],
        'end_reason': meta['end_reason'], 'pipeline': meta['pipeline'], 'llm': meta['resolved_stack']['llm'],
        'transcript_role_counts': dict(collections.Counter(row['role'] for row in transcript)),
        'event_counts': dict(collections.Counter(row['event'] for row in events)), 'events': events})
Path(__file__).with_name('call-evidence.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps([{k: row[k] for k in ['call_id', 'end_reason', 'event_counts']} for row in records], indent=2))
