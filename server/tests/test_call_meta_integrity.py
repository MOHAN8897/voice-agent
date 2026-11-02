"""meta.json writes are atomic, and one damaged file never breaks call history."""
import json
import threading

from server.call import call_ledger as ledger_module
from server.call.call_ledger import CallLedger


def ledger_in(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_module, "call_dir", lambda call_id: tmp_path / call_id)
    (tmp_path / "call-a").mkdir()
    return CallLedger()


def test_concurrent_writes_always_leave_one_whole_document(tmp_path, monkeypatch):
    ledger = ledger_in(tmp_path, monkeypatch)
    long, short = {"usage": "x" * 40000}, {"usage": "y"}

    def write(meta):
        for _ in range(40):
            ledger.write_meta("call-a", meta)

    threads = [threading.Thread(target=write, args=(meta,)) for meta in (long, short, long, short)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert json.loads((tmp_path / "call-a" / "meta.json").read_text(encoding="utf-8")) in (long, short)
    assert not list((tmp_path / "call-a").glob("*.tmp"))


def test_interleaved_legacy_file_reads_its_first_complete_copy(tmp_path, monkeypatch):
    ledger = ledger_in(tmp_path, monkeypatch)
    # What two overlapping in-place writes left behind (seen 2 Nov 2026).
    first = json.dumps({"call_id": "call-a", "agent_id": "agent"}, indent=2)
    (tmp_path / "call-a" / "meta.json").write_text(first + '\n          }\n        ],\n        "costUsd": "0.06', encoding="utf-8")
    assert ledger.read_meta("call-a") == {"call_id": "call-a", "agent_id": "agent"}
    assert ledger.review_fields("call-a") is not None


def test_unreadable_file_reads_as_empty(tmp_path, monkeypatch):
    ledger = ledger_in(tmp_path, monkeypatch)
    (tmp_path / "call-a" / "meta.json").write_text("{not json", encoding="utf-8")
    assert ledger.read_meta("call-a") == {}
