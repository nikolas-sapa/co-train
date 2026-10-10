"""`relay_audit.py` is the only check in this repo that looks at the endpoint rather than
at a run, so what is tested here is the comparator -- which fields make it red and which
must not.

Both directions are pinned, because both have a way of being wrong that produces a
confident answer. A comparator that keyed on `system_fingerprint` would report a model
swap on every run (the relay issues a fresh one per request, measured). A comparator that
ignored `prompt_tokens` would stay green through a change to the one deterministic number
the relay returns. The second is the failure that matters: a silent swap is exactly what
this file exists to make loud.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ptc.relay_audit import (  # noqa: E402
    PROBES,
    compare,
    fingerprint,
    main,
    normalise,
    verdict,
    verify_probe_texts,
)

# What the live relay actually answered on 2026-10-09, so the fake is not wishful: the
# count equals `cl100k_base` exactly on the two short prompts and exceeds it by 43% on
# the bulk one, and the fingerprint differs on every call.
MEASURED = {"english": 38, "cjk": 86, "bulk": 5519}

# Global, not per-relay: `system_fingerprint` has to be distinct across the baseline run
# and the check run, which are two separate fakes.
_CALLS = iter(range(1, 10_000))


def _relay(*, model: str = "deepseek-v4-flash", served: str | None = None,
           owned_by: str = "vyce", listed: bool = True,
           tokens: dict | None = None, answers: dict | None = None,
           fingerprints: bool = True, status: int = 200):
    """A relay that answers from a dict instead of over the network.

    Everything the comparator reads is a parameter, so a test changes exactly one thing
    and the rest stays at what the real endpoint returned.
    """
    counts = {**MEASURED, **(tokens or {})}

    def call(path: str, body: dict | None) -> dict:
        if path == "/models":
            rows = [{"id": "deepseek-v4.1", "owned_by": "deepseek"},
                    {"id": "gpt-6-luna", "owned_by": "openai"}]
            if listed:
                rows.append({"id": model, "owned_by": owned_by})
            return {"status": 200, "headers": {}, "elapsed": 0.1,
                    "body": {"data": rows}}
        prompt = body["messages"][0]["content"]
        name = next(p["name"] for p in PROBES if p["prompt"] == prompt)
        answer = (answers or {}).get(name, "ACK" if name == "bulk" else "a reply")
        if status != 200:
            return {"status": status, "headers": {}, "elapsed": 0.1,
                    "body": {"error": {"code": "model_not_found"}}}
        return {"status": 200, "headers": {}, "elapsed": 0.1, "body": {
            "model": served or body["model"],
            # Fresh every call, which is what the relay does.
            "system_fingerprint": (f"fp_{next(_CALLS):012d}" if fingerprints else None),
            "usage": {"prompt_tokens": counts[name], "completion_tokens": 7},
            "choices": [{"message": {"role": "assistant", "content": answer}}],
        }}

    return call


def _fp(**kwargs) -> dict:
    return fingerprint(_relay(**kwargs), kwargs.get("model", "deepseek-v4-flash"))


def test_the_pinned_cl100k_counts_are_falsifiable():
    """The ratio this tool reports has a pinned constant as its denominator, so editing a
    prompt without recomputing the constant would move the ratio without the endpoint
    moving. The hash is what makes that an error instead of a silent drift."""
    verify_probe_texts()  # the committed texts match their pins
    original = PROBES[0]["prompt"]
    try:
        PROBES[0]["prompt"] = original + " and one more clause"
        with pytest.raises(ValueError, match="text changed"):
            verify_probe_texts()
    finally:
        PROBES[0]["prompt"] = original
    verify_probe_texts()


def test_a_fingerprint_records_the_relay_side_token_count_and_its_divergence():
    """`prompt_tokens` is the only sampling-free number the relay returns, and the ratio
    against the local count is the factor between what it charges for and what the text
    tokenizes to. The cost co-primary is computed from the relay's side of it."""
    fp = _fp()
    rows = {p["name"]: p for p in fp["probes"]}
    assert rows["english"]["prompt_tokens"] == 38
    assert rows["english"]["ratio"] == 1.0, "short prompts match cl100k exactly"
    assert rows["bulk"]["prompt_tokens"] == 5519
    assert rows["bulk"]["ratio"] == pytest.approx(1.4313, abs=1e-4), (
        "above ~3.8k tokens the relay's count exceeds every standard tokenizer")
    assert fp["listing"]["owned_by"] == "vyce"


def test_a_fresh_system_fingerprint_every_call_is_not_a_model_swap():
    """The trap. The relay issues a new `system_fingerprint` per request -- five distinct
    values in five calls -- so a comparator that keyed on it would be red on every run
    and the signal would be discarded as noise within a day."""
    base = _fp()
    now = _fp()
    seen = {p["system_fingerprint"] for p in base["probes"] + now["probes"]}
    assert len(seen) == len(base["probes"]) + len(now["probes"]), "all distinct"
    drift = compare(base, now)
    assert not [d for d in drift if d["hard"]]
    assert verdict(now, drift)[0] is True


def test_a_changed_prompt_token_count_is_red():
    """The swap detector. One probe's count moving is a change in the serving stack, and
    it is reported against the probe that moved rather than as a total."""
    base = _fp()
    now = _fp(tokens={"bulk": 5600})
    drift = compare(base, now)
    hard = [d for d in drift if d["hard"]]
    assert [(d["kind"], d["where"], d["was"], d["now"]) for d in hard] == [
        ("prompt_tokens", "bulk", 5519, 5600)]
    ok, reasons = verdict(now, drift)
    assert ok is False and "prompt_tokens on bulk" in reasons[0]


def test_re_attributing_the_id_to_a_different_owner_is_red():
    """`owned_by` is the only provenance the listing carries that is not a templated
    placeholder: `deepseek-v4-flash` is attributed to `vyce` while the sibling id
    `deepseek-v4.1` is attributed to `deepseek`. A change there is a change of story."""
    base = _fp()
    now = _fp(owned_by="deepseek")
    ok, reasons = verdict(now, compare(base, now))
    assert ok is False and "owned_by" in reasons[0]


def test_an_id_that_stops_resolving_is_red_even_with_everything_else_intact():
    base = _fp()
    now = _fp(listed=False)
    ok, reasons = verdict(now, compare(base, now))
    assert ok is False
    assert any("not in /v1/models" in r for r in reasons)


def test_serving_a_model_other_than_the_one_requested_is_red():
    """The echoed `model` constrains nothing on its own -- it is the request's own string
    coming back -- but a relay that answers a different id has stopped pretending."""
    now = _fp(served="deepseek-v4-flash-lr")
    ok, reasons = verdict(now, [])
    assert ok is False
    assert any("served 'deepseek-v4-flash-lr'" in r for r in reasons)


def test_a_probe_the_relay_stops_answering_counts_as_drift_rather_than_being_skipped():
    """`paired.py` already carried this defect once: it intersected the names both sides
    had and reported n=12 on a 29-task run. A comparison that only looks at the rows two
    runs happen to share cannot go red for a missing row."""
    base = _fp()
    now = _fp()
    now["probes"] = [p for p in now["probes"] if p["name"] != "cjk"]
    drift = compare(base, now)
    missing = [d for d in drift if d["where"] == "cjk"]
    assert missing and missing[0]["hard"] is True
    assert verdict(now, drift)[0] is False


def test_a_known_answer_probe_that_misses_is_red_and_prose_drift_is_not():
    """`bulk` is forced to one word, so its answer is worth comparing. The other two are
    prose and would drift on any run; they are recorded, and soft."""
    base = _fp()
    chatty = _fp(answers={"english": "a completely different reply about foxes"})
    drift = compare(base, chatty)
    assert drift and not [d for d in drift if d["hard"]]
    assert verdict(chatty, drift)[0] is True

    missed = _fp(answers={"bulk": "Sure! Here is my answer: acknowledged."})
    ok, reasons = verdict(missed, compare(base, missed))
    assert ok is False
    assert any("missed its known answer" in r for r in reasons)


def test_an_error_status_is_red_and_carries_the_endpoint_s_own_reason():
    now = _fp(status=400)
    ok, reasons = verdict(now, [])
    assert ok is False
    assert any("answered 400" in r and "model_not_found" in r for r in reasons)


def test_record_refuses_to_write_a_baseline_that_is_already_red(tmp_path, monkeypatch,
                                                               capsys):
    """A baseline captured while the id was unlisted would make every later `check` pass
    by agreeing with it. The instrument asserting its own soundness falsely is defect 2
    in this project's ledger; it is not getting a thirteenth."""
    out = tmp_path / "baseline.json"
    monkeypatch.setenv("VYCEAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr("ptc.relay_audit.post",
                        lambda base, key, path, body, timeout=600.0:
                        _relay(listed=False)(path, body))
    assert main(["relay_audit", "record", str(out)]) == 1
    assert not out.exists()
    assert "REFUSING" in capsys.readouterr().err


def test_record_then_check_round_trips_through_a_file(tmp_path, monkeypatch):
    out = tmp_path / "baseline.json"
    monkeypatch.setenv("VYCEAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr("ptc.relay_audit.post",
                        lambda base, key, path, body, timeout=600.0:
                        _relay()(path, body))
    assert main(["relay_audit", "record", str(out)]) == 0
    assert main(["relay_audit", "check", str(out)]) == 0

    # Same baseline, a relay whose count moved: the exit code has to carry it, because
    # this is meant to run unattended before a launch.
    monkeypatch.setattr("ptc.relay_audit.post",
                        lambda base, key, path, body, timeout=600.0:
                        _relay(tokens={"english": 39})(path, body))
    assert main(["relay_audit", "check", str(out)]) == 1
    assert json.loads(out.read_text())["probes"][0]["prompt_tokens"] == 38


def test_a_missing_key_var_exits_without_touching_the_network(tmp_path, monkeypatch):
    monkeypatch.delenv("VYCEAI_API_KEY", raising=False)

    def explode(*a, **k):
        raise AssertionError("must not reach the endpoint without a key")

    monkeypatch.setattr("ptc.relay_audit.post", explode)
    assert main(["relay_audit", "check", str(tmp_path / "nope.json")]) == 2


def test_normalise_compares_content_not_formatting():
    assert normalise("  ACK\n") == normalise("ack")
    assert normalise("A  C K") != normalise("ACK")
