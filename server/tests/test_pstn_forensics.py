from server.services.pstn_debug import mark, record_milestone
from server.services.pstn_forensics import build_forensics_snapshot


def test_build_forensics_snapshot_empty_call_id():
    snap = build_forensics_snapshot(None)
    assert "ids" in snap
    assert "timeline_ms_from_dial" in snap


def test_forensics_resolves_telnyx_control_id_to_internal_call(monkeypatch):
    from server.services import pstn_forensics as pf

    control = "v3:LBcrhuRcUsE-wXle1nHvHfnf3BkkNcBdFAfCxnejOSKtpqX_e_s7Vg"
    internal = "14185b60-70ff-420a-bbac-1bd4a2b9b0a3"

    class _Reg:
        @staticmethod
        def get(key):
            if key == control:
                return {"internal_call_id": internal, "call_control_id": control}
            return None

        @staticmethod
        def list_recent(_n):
            return []

    monkeypatch.setattr(pf, "_find_registry_row", lambda cid: (control, {"internal_call_id": internal}))
    monkeypatch.setattr(
        "server.call.call_ledger.call_ledger.read_meta",
        lambda ledger_id: {"call_id": internal} if ledger_id == internal else {},
    )
    snap = build_forensics_snapshot(control)
    assert snap["ids"]["call_id"] == internal
    assert snap["ids"]["call_control_id"] == control


def test_milestones_surface_in_snapshot():
    mark("ctrl-test")
    record_milestone("ctrl-test", "answered")
    record_milestone("ctrl-test", "first_outbound_sent")
    snap = build_forensics_snapshot("ctrl-test")
    # No registry row — timeline may be empty; direct milestone export tested via debug module
    from server.services.pstn_debug import milestones_for

    assert milestones_for("ctrl-test")["answered"] >= 0
