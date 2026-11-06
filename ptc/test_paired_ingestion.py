"""Strict legacy JSONL ingestion regressions, independent of the SDK."""

from __future__ import annotations

import io
import json

import pytest

import ptc.paired as paired_module


READERS = ("load", "rollouts")
SENTINEL = "CREDENTIAL_TASK_EXCEPTION_SENTINEL"


def _record(name="alpha", score=1.0):
    return {
        "ok": True,
        "task": {"data": {"name": name, "min_calls": 1}},
        "traces": [{"rewards": {"correct": {"score": score}}}],
    }


def _input(monkeypatch, text):
    def read_only(path, mode="r"):
        assert path == "memory.jsonl"
        assert mode == "r", "loader must never write"
        return io.StringIO(text)

    monkeypatch.setattr(paired_module, "open", read_only, raising=False)
    return "memory.jsonl"


def _refused(reader, path):
    with pytest.raises(ValueError) as caught:
        reader(path)
    message = str(caught.value)
    assert 1 <= len(message) <= 80
    assert SENTINEL not in message
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    return message


def _duplicate_refusal(reader, path):
    try:
        reader(path)
    except ValueError:
        return
    raise AssertionError("DUPLICATE_TASK_NOT_REFUSED")


def test_valid_records_preserve_exact_outputs(monkeypatch):
    first = _record()
    first["task"]["type"] = "arbitrary-sdk-task"
    first["task"]["data"]["extra"] = {"nested": [1, "opaque"]}
    first["traces"] = [
        {"rewards": {"correct": {"score": 2, "weight": 0.5, "extra": True},
                     "bonus": {"score": -0.25}},
         "messages": [{"role": "assistant", "content": "opaque SDK payload"}]},
        {"rewards": {"other": {"score": 4.0, "weight": 0.5}}},
    ]
    first["unknown"] = {"anything": [None, False, {}]}
    second = _record("beta", -3)
    second["ok"] = False
    second["task"]["data"]["min_calls"] = 40
    path = _input(monkeypatch, "\n \t\n" + json.dumps(first) + "\n\n"
                  + json.dumps(second) + "\n \n")
    assert paired_module.load(path) == {"alpha": 2.75, "beta": -3.0}
    assert paired_module.rollouts(path) == {
        "alpha": {"score": 2.75, "ok": True, "min_calls": 1},
        "beta": {"score": -3.0, "ok": False, "min_calls": 40},
    }


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("second_score", [1.0, -7.0], ids=["identical", "conflicting"])
def test_duplicate_task_names_refused(monkeypatch, reader_name, second_score):
    path = _input(monkeypatch, json.dumps(_record()) + "\n"
                  + json.dumps(_record(score=second_score)) + "\n")
    _duplicate_refusal(getattr(paired_module, reader_name), path)


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("duplicate", [
    '"ok":true,"ok":false',
    '"ok":true,"\\u006fk":false',
    '"task":{"data":{"name":"alpha"}},"task":{"data":{"name":"beta"}}',
    '"task":{"data":{"name":"alpha","name":"beta"}}',
    '"task":{"data":{"name":"alpha","\\u006eame":"beta"}}',
    '"traces":[{"rewards":{"x":{"score":1,"score":2}}}]',
    '"traces":[{"rewards":{"x":{"score":1,"\\u0073core":2}}}]',
    '"traces":[{"rewards":{"x":{"score":1},"x":{"score":2}}}]',
    '"extra":{"token":1,"token":2}',
])
def test_duplicate_json_keys_refused(monkeypatch, reader_name, duplicate):
    # Replace the corresponding field so every refusal has a duplicate, not a
    # missing required field or an incidental duplicate introduced by the fixture.
    record = _record()
    field = duplicate.split('"', 2)[1]
    record.pop(field, None)
    text = json.dumps(record)[:-1] + "," + duplicate + "}"
    path = _input(monkeypatch, text)
    _refused(getattr(paired_module, reader_name), path)


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("field", ["score", "weight"])
@pytest.mark.parametrize("token", [
    "NaN", "Infinity", "-Infinity", "1e309", "-1e309",
    "true", "false", '"1"', "null", "[]", "{}",
])
def test_invalid_score_or_weight_refused(monkeypatch, reader_name, field, token):
    component = '"score":1,"weight":1'
    component = component.replace(f'"{field}":1', f'"{field}":{token}')
    text = ('{"task":{"data":{"name":"' + SENTINEL + '"}},'
            '"ok":true,"traces":[{"rewards":{"x":{' + component + '}}}]}')
    path = _input(monkeypatch, text)
    _refused(getattr(paired_module, reader_name), path)


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("components", [
    [{"score": 1e308, "weight": 2}],
    [{"score": -1e308, "weight": 2}],
    [{"score": 1e308}, {"score": 1e308}],
    [{"score": -1e308}, {"score": -1e308}],
    [{"score": 1e308}, {"score": 1e308}, {"score": -1e308}],
    [{"score": 10 ** 400}],
    [{"score": 10 ** 200, "weight": 10 ** 200}],
])
def test_arithmetic_overflow_refused(monkeypatch, reader_name, components):
    record = _record()
    record["traces"] = [{"rewards": {str(i): component}}
                        for i, component in enumerate(components)]
    path = _input(monkeypatch, json.dumps(record))
    _refused(getattr(paired_module, reader_name), path)


@pytest.mark.parametrize("reader_name", READERS)
def test_finite_general_rewards_preserved(monkeypatch, reader_name):
    record = _record()
    record["traces"] = [{"rewards": {
        "negative": {"score": -2, "weight": -0.5},
        "general": {"score": 2.5},
        "zero": {"score": 0, "weight": 7},
        "fraction": {"score": 0.25, "weight": 2},
    }}]
    path = _input(monkeypatch, json.dumps(record))
    got = getattr(paired_module, reader_name)(path)["alpha"]
    assert (got if reader_name == "load" else got["score"]) == 4.0


def test_ok_booleans_and_missing_remain_compatible(monkeypatch):
    rows = [_record("true"), _record("false"), _record("missing")]
    rows[1]["ok"] = False
    rows[1]["traces"] = []
    rows[2].pop("ok")
    rows[2]["task"]["data"].pop("min_calls")
    path = _input(monkeypatch, "\n".join(map(json.dumps, rows)))
    got = paired_module.rollouts(path)
    assert got["true"]["ok"] is True
    assert got["false"] == {"score": 0.0, "ok": False, "min_calls": 1}
    assert got["false"]["ok"] is False
    assert got["missing"] == {"score": 1.0, "ok": False, "min_calls": None}
    assert got["missing"]["ok"] is False
    assert paired_module.load(path) == {"true": 1.0, "false": 0.0, "missing": 1.0}


@pytest.mark.parametrize("ok", [1, 0, "true", "false", "", None, [], {}, [True]])
def test_nonboolean_ok_refused_by_rollouts(monkeypatch, ok):
    record = _record()
    record["ok"] = ok
    path = _input(monkeypatch, json.dumps(record))
    _refused(paired_module.rollouts, path)
    assert paired_module.load(path) == {"alpha": 1.0}


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("fragment", [
    "null", "[]", "1", '"CREDENTIAL_TASK_EXCEPTION_SENTINEL"',
    "{}", '{"task":null}', '{"task":[]}', '{"task":{}}',
    '{"task":{"data":null}}', '{"task":{"data":[]}}',
    '{"task":{"data":{}}}',
    '{"task":{"data":{"name":null}}}', '{"task":{"data":{"name":true}}}',
    '{"task":{"data":{"name":7}}}', '{"task":{"data":{"name":[]}}}',
    '{"task":{"data":{"name":{}}}}',
    '{"traces":null}', '{"traces":{}}', '{"traces":"bad"}',
    '{"traces":[null]}', '{"traces":[[]]}', '{"traces":[{}]}',
    '{"traces":[{"rewards":null}]}', '{"traces":[{"rewards":[]}]}',
    '{"traces":[{"rewards":{"x":null}}]}',
    '{"traces":[{"rewards":{"x":[]}}]}',
    '{"traces":[{"rewards":{"x":{}}}]}',
    '{"task":', '{"extra":"CREDENTIAL_TASK_EXCEPTION_SENTINEL"',
])
def test_malformed_shapes_have_bounded_private_errors(monkeypatch, reader_name, fragment):
    value = None
    try:
        value = json.loads(fragment)
    except ValueError:
        pass
    if isinstance(value, dict) and value:
        record = _record(SENTINEL)
        record.update(value)
        text = json.dumps(record)
    else:
        text = fragment
    path = _input(monkeypatch, text)
    message = _refused(getattr(paired_module, reader_name), path)
    assert message not in text
    assert all(word not in message for word in ("KeyError", "TypeError", "JSONDecodeError"))


@pytest.mark.parametrize("reader_name", READERS)
@pytest.mark.parametrize("keys", [
    ("task",), ("task", "data"), ("task", "data", "name"),
    ("traces",), ("traces", 0, "rewards"),
    ("traces", 0, "rewards", "correct", "score"),
])
def test_missing_required_fields_refused(monkeypatch, reader_name, keys):
    record = _record(SENTINEL)
    container = record
    for key in keys[:-1]:
        container = container[key]
    container.pop(keys[-1])
    path = _input(monkeypatch, json.dumps(record))
    _refused(getattr(paired_module, reader_name), path)


def test_ingested_scores_keep_paired_arithmetic_and_guards(monkeypatch):
    path = _input(monkeypatch, json.dumps(_record("x", 2)) + "\n"
                  + json.dumps(_record("y", -1)))
    a = paired_module.load(path)
    b = {"x": 1.0, "y": 0.0}
    got = paired_module.paired(a, b)
    assert got["tasks"] == ["x", "y"]
    assert got["diffs"] == [1.0, -1.0]
    assert (got["mean_a"], got["mean_b"], got["delta"]) == (0.5, 0.5, 0.0)
    assert (got["a_only"], got["b_only"], got["ties"], got["p"]) == (1, 1, 0, 1.0)
    with pytest.raises(SystemExit, match="pairing is broken"):
        paired_module.paired(a, {"x": 1.0})
    with pytest.raises(SystemExit, match="same taskset"):
        paired_module.paired(a, {"z": 1.0})
    record = _record()
    record.pop("ok")
    path = _input(monkeypatch, json.dumps(record))
    void = paired_module.rollouts(path)
    with pytest.raises(SystemExit, match="void"):
        paired_module.refuse_voids("a", void, "b", void)


@pytest.mark.parametrize("reader_name", READERS)
def test_readers_only_open_input_read_only(monkeypatch, reader_name):
    calls = []

    def read_only(path, mode="r"):
        calls.append((path, mode))
        assert mode == "r"
        return io.StringIO(json.dumps(_record()))

    monkeypatch.setattr(paired_module, "open", read_only, raising=False)
    getattr(paired_module, reader_name)("memory.jsonl")
    assert calls == [("memory.jsonl", "r")]


def test_duplicate_overwrite_negative_control_reaches_refusal_assertion(monkeypatch):
    def overwrite_reader(path):
        out = {}
        with paired_module.open(path) as fh:
            for line in fh:
                record = json.loads(line)
                out[record["task"]["data"]["name"]] = 1.0
        return out

    path = _input(monkeypatch, json.dumps(_record()) + "\n" + json.dumps(_record()))
    assert overwrite_reader(path) == {"alpha": 1.0}
    with pytest.raises(AssertionError, match="DUPLICATE_TASK_NOT_REFUSED"):
        _duplicate_refusal(overwrite_reader, path)
