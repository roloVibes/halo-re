"""Engage-mode engine tests for halo-re (ported from the halo-hacker
pack's suite, scoped to the ported state machinery).

Covers the engage/disengage lifecycle, window enforcement, double-engage
refusal, status reporting, and expiry flipping is_engaged. The source's
lineup-application and scope-guard/classify tests are intentionally not
ported — halo-re has neither feature (see the note in tools/engage.py).
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import engage  # noqa: E402

_VALID = Path(__file__).resolve().parent.parent / "examples" / "fixtures" / "valid"


def _engagement(window_start: str | None = None,
                window_expires: str | None = None,
                status: str = "active") -> dict:
    """A valid engagement whose window is derived from the clock at call time --
    never a hardcoded date, which would turn these tests into a time bomb."""
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    eng = json.loads((_VALID / "engagement.json").read_text())
    eng["engagement_id"] = "eng-re-test-001"
    eng["window"] = {
        "start": window_start or (now - _dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires": window_expires or (now + _dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    eng["status"] = status
    return eng


def _write_engagement(tmp_path: Path, engagement: dict) -> Path:
    root = tmp_path / "engagement"
    root.mkdir(parents=True, exist_ok=True)
    (root / "engagement.json").write_text(json.dumps(engagement), encoding="utf-8")
    return root


def test_engage_lifecycle(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))

    root = _write_engagement(tmp_path, _engagement())
    result = engage.engage(root)
    assert result["ok"] is True
    assert result["engagement_id"] == "eng-re-test-001"
    assert "window_end" in result

    state_path = data_dir / "engage-state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text())
    assert state["active"] is True
    assert state["engagement_root"] == str(root.resolve())

    status = engage.status()
    assert status["ok"] is True
    assert status["active"] is True
    assert status["engagement_id"] == "eng-re-test-001"
    assert status["window_remaining_seconds"] > 0

    dis = engage.disengage()
    assert dis["ok"] is True
    assert dis["active"] is False
    assert not state_path.exists()

    history = list((data_dir / "engage-history.jsonl").read_text().splitlines())
    assert len(history) == 1
    entry = json.loads(history[0])
    assert entry["engagement_id"] == "eng-re-test-001"
    assert "engaged_at" in entry
    assert "disengaged_at" in entry


def test_engage_window_fail_closed(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))

    root = _write_engagement(
        tmp_path,
        _engagement(window_start="2026-09-01T00:00:00Z", window_expires="2026-09-02T00:00:00Z"),
    )
    result = engage.engage(root)
    assert result["ok"] is False
    assert "expired" in result["error"]
    assert not (data_dir / "engage-state.json").exists()


def test_engage_double_refused(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))

    root = _write_engagement(tmp_path, _engagement())
    assert engage.engage(root)["ok"] is True

    second = engage.engage(root)
    assert second["ok"] is False
    assert "already engaged" in second["error"]
    assert "eng-re-test-001" in second["error"]


def test_status_remaining_seconds(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))

    root = _write_engagement(
        tmp_path,
        _engagement(window_start="2026-10-28T00:00:00Z", window_expires="3026-10-30T00:00:00Z"),
    )
    engage.engage(root)
    status = engage.status()
    assert status["ok"] is True
    assert status["active"] is True
    # Roughly a millennium remaining (in seconds).
    assert status["window_remaining_seconds"] > 30_000_000_000


def test_expiry_flips_is_engaged(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))

    root = _write_engagement(
        tmp_path,
        _engagement(window_start="2026-10-01T00:00:00Z", window_expires="2026-10-02T00:00:00Z"),
    )
    # Simulate a stale active state file left behind after the window expired.
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "engage-state.json").write_text(json.dumps({
        "engagement_id": "eng-re-test-001",
        "engagement_root": str(root.resolve()),
        "engaged_at": "2026-10-01T12:00:00Z",
        "active": True,
    }), encoding="utf-8")

    # State file exists, but window is expired.
    assert engage.current() is None
    assert engage.is_engaged() is False

    status = engage.status()
    assert status["ok"] is True
    assert status["active"] is False
    assert status["expired"] is True


def test_engage_refuses_missing_record(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALO_RE_DATA_DIR", str(data_dir))
    root = tmp_path / "empty-root"
    root.mkdir()
    with pytest.raises(ValueError):
        engage.engage(root)
