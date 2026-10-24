"""Data-only executable-skill acceptance; missing APIs fail after collection."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


MAX_BYTES = 8 * 1024 * 1024
REJECT = (TypeError, ValueError)
PROGRAM = '''tables = execute_sql(query="SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
if len(tables) == 1:
    name = tables[0]["name"]
    quoted = '"'
    for character in name:
        quoted = quoted + ('""' if character == '"' else character)
    quoted = quoted + '"'
    print("FINAL_SQL:SELECT COUNT(*) FROM " + quoted)
'''


def api(name="sql_skills"):
    try:
        return importlib.import_module("train." + name)
    except ModuleNotFoundError as exc:
        if exc.name != "train." + name:
            raise
        pytest.fail("train." + name + " is not implemented", pytrace=False)


def ids(label="source", split="origin", **changes):
    from train.sql_episodes import EpisodeIds

    values = dict(
        corpus_id="caller-row-count-fixtures", split_id=split, run_id="skills-run",
        episode_id=label, policy_id="trusted-caller", policy_revision="v1",
    )
    values.update(changes)
    return EpisodeIds(**values)


def task_at(directory, label, rows, table=None):
    from bench.task import SqlTask

    directory.mkdir(parents=True, exist_ok=True)
    table = label if table is None else table
    quoted = '"' + table.replace('"', '""') + '"'
    path = directory / (label + ".sqlite")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE " + quoted + " (value INTEGER)")
        connection.executemany(
            "INSERT INTO " + quoted + " VALUES (?)", [(i,) for i in range(rows)],
        )
    return SqlTask(
        name="row-count-" + label, question="Count rows in the only user table.",
        evidence="", gold_sql="SELECT COUNT(*) FROM " + quoted,
        db_id=label, db_path=str(path), tier="simple", tier_source="derived",
        shape="select-count", coarse_shape="aggregate", source="fixture",
    )


def source_at(directory):
    from train.sql_capture import start_capture

    task = task_at(directory, "origin", 2)
    capture = start_capture(task, ids=ids(), allow_execution=True).finish("SELECT -1")
    assert capture.result.valid is True and capture.result.score == 0
    return task, capture


def proposed(module, task, capture, program=PROGRAM):
    return module.create_candidate(
        capture, source_task=task, source_ids=capture.ids,
        skill_id="single-user-table-row-count", program=program,
    )


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def pin(data):
    return hashlib.sha256(data).hexdigest()


def envelope(payload, format="sql_skill_candidate", **changes):
    value = dict(
        format=format, schema_version=1, payload=payload,
        sha256=pin(canonical(payload)),
    )
    value.update(changes)
    return canonical(value)


def sentries(monkeypatch):
    from bench import score
    from ptc import sql_arms
    from train import sql_episodes

    counts = dict(build=0, dispatch=0, score=0)
    originals = (
        sql_arms.build_sql_arms, sql_arms.ArmPair.run, score.execution_accuracy,
    )

    def build(*args, **kwargs):
        counts["build"] += 1
        return originals[0](*args, **kwargs)

    def dispatch(*args, **kwargs):
        counts["dispatch"] += 1
        return originals[1](*args, **kwargs)

    def execute(*args, **kwargs):
        counts["score"] += 1
        return originals[2](*args, **kwargs)

    monkeypatch.setattr(sql_arms, "build_sql_arms", build)
    monkeypatch.setattr(sql_arms.ArmPair, "run", dispatch)
    monkeypatch.setattr(score, "execution_accuracy", execute)
    monkeypatch.setattr(sql_episodes, "execution_accuracy", execute)
    return counts


def world(directory, module=None, evaluator=None):
    module = api() if module is None else module
    evaluator = api("sql_skill_eval") if evaluator is None else evaluator
    task, capture = source_at(directory)
    candidate = proposed(module, task, capture)
    source = evaluator.SkillCase("source_failure", task, capture.ids)
    cases = tuple(
        evaluator.SkillCase(
            "qualification", task_at(directory, label, rows),
            ids(label, "qualification"),
        )
        for label, rows in (("empty", 0), ("singleton", 1), ("triple", 3), ("seven", 7))
    )
    return SimpleNamespace(
        task=task, capture=capture, candidate=candidate, source=source,
        cases=cases, approval_ids=ids("approval", "approval"),
        source_pin=pin(__import__("train.sql_capture", fromlist=["encode_capture"])
                       .encode_capture(capture)),
    )


def promote(module, evaluator, state, **changes):
    values = dict(
        source_capture=state.capture,
        expected_source_capture_sha256=state.source_pin,
        source_case=state.source, qualification_cases=state.cases,
        ids=state.approval_ids, allow_execution=True,
    )
    values.update(changes)
    return evaluator.promote_candidate(state.candidate, **values)


def test_data_only_creation_canonical_immutable_and_host_only(tmp_path, monkeypatch):
    module = api()
    task, capture = source_at(tmp_path)
    counts = sentries(monkeypatch)
    sentinel = tmp_path / "must-not-exist"
    program = "open(" + repr(str(sentinel)) + ", 'w').write('executed')"
    candidate = proposed(module, task, capture, program)
    encoded = module.encode_candidate(candidate)
    assert module.decode_candidate(encoded) == candidate
    assert module.encode_candidate(module.decode_candidate(encoded)) == encoded
    assert counts == dict(build=0, dispatch=0, score=0)
    assert not sentinel.exists()
    assert candidate.scope == module.SkillScope(task.source, task.shape, task.coarse_shape)
    assert candidate.source.capture_sha256 == pin(
        __import__("train.sql_capture", fromlist=["encode_capture"]).encode_capture(capture),
    )
    assert candidate.source.task_fingerprint == capture.task_fingerprint
    assert task.gold_sql.encode() not in encoded
    assert b"source_task" not in encoded and b"db_path" not in encoded
    assert not hasattr(candidate, "task") and not hasattr(candidate, "gold_sql")
    for record in (candidate, candidate.scope, candidate.source,
                   candidate.source.ids, candidate.source.instrument):
        field = dataclasses.fields(record)[0].name
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(record, field, None)
    value = json.loads(encoded)
    assert set(value) == {"format", "schema_version", "payload", "sha256"}
    assert value["sha256"] == pin(canonical(value["payload"]))
    assert pin(encoded) != value["sha256"]


@pytest.mark.parametrize("change", (
    "wrong_type", "name", "question", "gold_sql", "source", "shape", "coarse_shape",
    "ids", "success", "aborted", "invalid",
))
def test_creation_rejects_inconsistent_declarations_without_execution(
    tmp_path, monkeypatch, change,
):
    module = api()
    task, capture = source_at(tmp_path)
    source_task, source_ids = task, capture.ids
    if change == "wrong_type":
        source_task = dataclasses.asdict(task)
    elif change in {"name", "question", "gold_sql", "source", "shape", "coarse_shape"}:
        source_task = dataclasses.replace(task, **{change: "changed"})
    elif change == "ids":
        source_ids = ids("not-source")
    elif change == "aborted":
        capture = dataclasses.replace(
            capture, terminal_label="aborted", final_answer=None,
            extracted_sql=None, result=None,
        )
    else:
        from bench.score import ExResult

        result = (
            ExResult(1, "match", True, "", 1, 1) if change == "success"
            else ExResult(0, "gold_error", False, "invalid gold", 0, 0)
        )
        capture = dataclasses.replace(capture, result=result)
    counts = sentries(monkeypatch)
    with pytest.raises(REJECT):
        module.create_candidate(
            capture, source_task=source_task, source_ids=source_ids,
            skill_id="row-count", program=PROGRAM,
        )
    assert counts == dict(build=0, dispatch=0, score=0)


def test_creation_requires_explicit_host_source_task(tmp_path):
    module = api()
    task, capture = source_at(tmp_path)
    with pytest.raises(TypeError):
        module.create_candidate(
            capture, source_ids=capture.ids, skill_id="count", program=PROGRAM,
        )


@pytest.mark.parametrize("alphabet", ("ascii", "utf8"))
def test_program_utf8_exact_65536_and_plus_one(tmp_path, alphabet):
    module = api()
    task, capture = source_at(tmp_path)
    program = "x" * 65536 if alphabet == "ascii" else "é" * 32768
    assert len(program.encode()) == 65536
    candidate = proposed(module, task, capture, program)
    assert module.decode_candidate(module.encode_candidate(candidate)) == candidate
    with pytest.raises(ValueError):
        proposed(module, task, capture, program + "x")


@pytest.mark.parametrize("value", (None, 1, True, b"print(1)", "\ud800"))
def test_bad_program_types_and_encoding_fail_closed(tmp_path, value):
    module = api()
    task, capture = source_at(tmp_path)
    with pytest.raises(REJECT):
        proposed(module, task, capture, value)


def mutate_path(payload, path, value):
    obj = payload
    for name in path[:-1]:
        obj = obj[name]
    obj[path[-1]] = value


BAD_FIELDS = (
    (("schema_version",), True), (("schema_version",), 2),
    (("skill_id",), ""), (("skill_id",), 1), (("program",), []),
    (("scope",), []), (("scope", "source"), False),
    (("scope", "shape"), ""), (("scope", "coarse_shape"), 1),
    (("source", "capture_sha256"), "A" * 64),
    (("source", "task_fingerprint"), "g" * 64),
    (("source", "db_sha256"), 1), (("source", "task_id"), ""),
    (("source", "ids", "run_id"), 1),
    (("source", "instrument", "action_cap"), True),
    (("source", "instrument", "action_max_rows"), 0),
    (("source", "instrument", "scorer_timeout_s"), True),
    (("source", "instrument", "source_paths"), "not-array"),
    (("source", "instrument", "source_sha256"), "x"),
)


@pytest.mark.parametrize("path,value", BAD_FIELDS)
def test_candidate_strict_field_graph(tmp_path, monkeypatch, path, value):
    module = api()
    task, capture = source_at(tmp_path)
    payload = json.loads(module.encode_candidate(proposed(module, task, capture)))["payload"]
    mutate_path(payload, path, value)
    counts = sentries(monkeypatch)
    with pytest.raises(REJECT):
        module.decode_candidate(envelope(payload))
    assert counts == dict(build=0, dispatch=0, score=0)


@pytest.mark.parametrize("path", (
    (), ("scope",), ("source",), ("source", "ids"), ("source", "instrument"),
))
@pytest.mark.parametrize("operation", ("unknown", "missing", "duplicate"))
def test_candidate_rejects_unknown_missing_duplicate_at_every_level(
    tmp_path, path, operation,
):
    module = api()
    task, capture = source_at(tmp_path)
    payload = json.loads(module.encode_candidate(proposed(module, task, capture)))["payload"]
    obj = payload
    for name in path:
        obj = obj[name]
    if operation == "unknown":
        obj["surprise"] = "untrusted"
        encoded = envelope(payload)
    elif operation == "missing":
        obj.pop(next(iter(obj)))
        encoded = envelope(payload)
    else:
        encoded = envelope(payload)
        key = next(iter(obj))
        needle = canonical(key) + b":"
        index = encoded.index(needle)
        encoded = encoded[:index] + needle + b"null," + encoded[index:]
    with pytest.raises(REJECT):
        module.decode_candidate(encoded)


@pytest.mark.parametrize("data", (
    b'{"format":NaN}', b'{"format":Infinity}', b"\xff",
    b"[" * 2000 + b"0" + b"]" * 2000, b"{", b"null", b"[]",
    "not-bytes", bytearray(b"{}"),
))
def test_candidate_malformed_nonfinite_deep_json(tmp_path, data):
    module = api()
    with pytest.raises(REJECT):
        module.decode_candidate(data)


@pytest.mark.parametrize("field,value", (
    ("format", "other"), ("schema_version", True), ("schema_version", 2),
    ("sha256", "0" * 64), ("payload", []),
))
def test_candidate_envelope_admission(tmp_path, field, value):
    module = api()
    task, capture = source_at(tmp_path)
    obj = json.loads(module.encode_candidate(proposed(module, task, capture)))
    obj[field] = value
    with pytest.raises(REJECT):
        module.decode_candidate(canonical(obj))


def test_candidate_envelope_exact_eight_mib_and_plus_one(tmp_path):
    module = api()
    task, capture = source_at(tmp_path)
    candidate = proposed(module, task, capture)
    baseline = len(module.encode_candidate(candidate))
    candidate = dataclasses.replace(
        candidate, skill_id="x" * (len(candidate.skill_id) + MAX_BYTES - baseline),
    )
    encoded = module.encode_candidate(candidate)
    assert len(encoded) == MAX_BYTES
    assert module.decode_candidate(encoded) == candidate
    with pytest.raises(ValueError):
        module.encode_candidate(dataclasses.replace(candidate, skill_id=candidate.skill_id + "x"))
    with pytest.raises(ValueError):
        module.decode_candidate(encoded + b" ")


def test_manually_corrupted_record_and_recursive_encoding_fail_closed(tmp_path):
    module = api()
    task, capture = source_at(tmp_path)
    candidate = proposed(module, task, capture)
    object.__setattr__(candidate, "program", "\ud800")
    with pytest.raises(REJECT):
        module.encode_candidate(candidate)
    object.__setattr__(candidate, "program", candidate)
    with pytest.raises(REJECT):
        module.encode_candidate(candidate)


def test_promotion_data_roundtrip_complete_result_and_immutability(tmp_path, monkeypatch):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    receipt, captures = promote(module, evaluator, state)
    assert receipt is not None and len(captures) == 4
    counts = sentries(monkeypatch)
    encoded = module.encode_promotion(receipt)
    assert module.decode_promotion(encoded) == receipt
    assert module.encode_promotion(module.decode_promotion(encoded)) == encoded
    assert counts == dict(build=0, dispatch=0, score=0)
    assert receipt.candidate_sha256 == pin(module.encode_candidate(state.candidate))
    assert receipt.scope == state.candidate.scope and receipt.source == state.candidate.source
    assert receipt.binding.source_paths == (
        "train/sql_skills.py", "train/sql_skill_eval.py",
    )
    for ref, captured in zip(receipt.qualifications, captures):
        assert ref.result == captured.result
        assert set(dataclasses.asdict(ref.result)) == {
            "score", "status", "valid", "detail", "n_pred_rows", "n_gold_rows",
        }
        assert ref.capture_sha256 == pin(
            __import__("train.sql_capture", fromlist=["encode_capture"]).encode_capture(captured),
        )
        for record in (ref, ref.ids, ref.result):
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(record, dataclasses.fields(record)[0].name, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        receipt.qualifications = ()


@pytest.mark.parametrize("path,value", (
    (("schema_version",), True), (("candidate_sha256",), "x"),
    (("ids", "episode_id"), False), (("binding", "source_paths"), []),
    (("binding", "source_sha256"), "x"),
    (("binding", "instrument", "program_timeout_s"), False),
    (("qualifications",), []),
    (("qualifications", 0, "role"), "reuse"),
    (("qualifications", 0, "result", "score"), True),
    (("qualifications", 0, "result", "valid"), 1),
    (("qualifications", 0, "result", "n_gold_rows"), True),
    (("qualifications", 0, "result", "status"), "made-up"),
))
def test_promotion_strict_field_graph(tmp_path, path, value):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    receipt, _ = promote(module, evaluator, state)
    payload = json.loads(module.encode_promotion(receipt))["payload"]
    mutate_path(payload, path, value)
    with pytest.raises(REJECT):
        module.decode_promotion(envelope(payload, "sql_skill_promotion"))


@pytest.mark.parametrize("path", (
    (), ("scope",), ("source",), ("ids",), ("binding",),
    ("binding", "instrument"), ("qualifications", 0),
    ("qualifications", 0, "ids"), ("qualifications", 0, "result"),
))
@pytest.mark.parametrize("operation", ("unknown", "missing", "duplicate"))
def test_promotion_rejects_unknown_missing_nested_fields(tmp_path, path, operation):
    module, evaluator = api(), api("sql_skill_eval")
    receipt, _ = promote(module, evaluator, world(tmp_path, module, evaluator))
    payload = json.loads(module.encode_promotion(receipt))["payload"]
    obj = payload
    for name in path:
        obj = obj[name]
    if operation == "unknown":
        obj["surprise"] = 0
    elif operation == "missing":
        obj.pop(next(iter(obj)))
    else:
        encoded = envelope(payload, "sql_skill_promotion")
        key = next(iter(obj))
        needle = canonical(key) + b":"
        index = encoded.index(needle)
        encoded = encoded[:index] + needle + b"null," + encoded[index:]
        with pytest.raises(REJECT):
            module.decode_promotion(encoded)
        return
    with pytest.raises(REJECT):
        module.decode_promotion(envelope(payload, "sql_skill_promotion"))


@pytest.mark.parametrize("data", (
    b'{"format":NaN}', b'{"format":-Infinity}', b"\xff",
    b"[" * 2000 + b"0" + b"]" * 2000, b"{", b"null", "not-bytes",
))
def test_promotion_malformed_json(data):
    module = api()
    with pytest.raises(REJECT):
        module.decode_promotion(data)


def test_creation_checks_declarations_not_origin_database(tmp_path, monkeypatch):
    module = api()
    task, capture = source_at(tmp_path)
    Path(task.db_path).unlink()
    counts = sentries(monkeypatch)
    candidate = proposed(module, task, capture)
    assert candidate.source.db_sha256 == capture.db_sha256
    assert counts == dict(build=0, dispatch=0, score=0)


@pytest.mark.parametrize("kind", ("candidate", "promotion"))
@pytest.mark.parametrize("path", ("envelope", "payload"))
def test_reject_duplicate_top_level_keys(tmp_path, kind, path):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    if kind == "candidate":
        encoded = module.encode_candidate(state.candidate)
        decoder = module.decode_candidate
    else:
        receipt, _ = promote(module, evaluator, state)
        encoded = module.encode_promotion(receipt)
        decoder = module.decode_promotion
    needle = b'"format":' if path == "envelope" else b'"candidate_sha256":'
    if kind == "candidate" and path == "payload":
        needle = b'"skill_id":'
    index = encoded.index(needle)
    with pytest.raises(REJECT):
        decoder(encoded[:index] + needle + b'null,' + encoded[index:])


@pytest.mark.parametrize("field,value", (
    ("format", "other"), ("schema_version", True), ("schema_version", 2),
    ("sha256", "0" * 64), ("payload", []),
))
def test_promotion_envelope_admission(tmp_path, field, value):
    module, evaluator = api(), api("sql_skill_eval")
    receipt, _ = promote(module, evaluator, world(tmp_path, module, evaluator))
    obj = json.loads(module.encode_promotion(receipt))
    obj[field] = value
    with pytest.raises(REJECT):
        module.decode_promotion(canonical(obj))


@pytest.mark.parametrize("number", (b"NaN", b"Infinity", b"-Infinity", b"1e999"))
@pytest.mark.parametrize("kind", ("candidate", "promotion"))
def test_nonfinite_deep_in_record_graph(tmp_path, number, kind):
    module, evaluator = api(), api("sql_skill_eval")
    state = world(tmp_path, module, evaluator)
    if kind == "candidate":
        encoded = module.encode_candidate(state.candidate)
        decoder = module.decode_candidate
    else:
        receipt, _ = promote(module, evaluator, state)
        encoded = module.encode_promotion(receipt)
        decoder = module.decode_promotion
    needle = b'"scorer_timeout_s":'
    begin = encoded.index(needle) + len(needle)
    end = encoded.index(b",", begin)
    with pytest.raises(REJECT):
        decoder(encoded[:begin] + number + encoded[end:])


def test_promotion_envelope_exact_eight_mib_and_plus_one(tmp_path):
    module, evaluator = api(), api("sql_skill_eval")
    receipt, _ = promote(module, evaluator, world(tmp_path, module, evaluator))
    baseline = len(module.encode_promotion(receipt))
    refs = list(receipt.qualifications)
    detail = refs[0].result.detail
    refs[0] = dataclasses.replace(
        refs[0], result=dataclasses.replace(
            refs[0].result, detail=detail + "x" * (MAX_BYTES - baseline),
        ),
    )
    receipt = dataclasses.replace(receipt, qualifications=tuple(refs))
    encoded = module.encode_promotion(receipt)
    assert len(encoded) == MAX_BYTES
    assert module.decode_promotion(encoded) == receipt
    refs[0] = dataclasses.replace(
        refs[0], result=dataclasses.replace(refs[0].result, detail=refs[0].result.detail + "x"),
    )
    with pytest.raises(ValueError):
        module.encode_promotion(dataclasses.replace(receipt, qualifications=tuple(refs)))
    with pytest.raises(ValueError):
        module.decode_promotion(encoded + b" ")


def test_promotion_rejects_corrupted_encoding_without_recursing(tmp_path):
    module, evaluator = api(), api("sql_skill_eval")
    receipt, _ = promote(module, evaluator, world(tmp_path, module, evaluator))
    object.__setattr__(receipt.qualifications[0].result, "detail", "\ud800")
    with pytest.raises(REJECT):
        module.encode_promotion(receipt)
    object.__setattr__(receipt.qualifications[0].result, "detail", receipt)
    with pytest.raises(REJECT):
        module.encode_promotion(receipt)


def test_workflow_paths_reject_objects_before_equality(tmp_path, monkeypatch):
    module = api()
    task, capture = source_at(tmp_path)
    counts = sentries(monkeypatch)
    comparisons = []

    class PathImpostor:
        def __eq__(self, other):
            comparisons.append(other)
            return True

    with pytest.raises(TypeError):
        module.SkillBinding(
            capture.instrument, (PathImpostor(), "train/sql_skill_eval.py"), "0" * 64,
        )
    assert comparisons == [], "field-graph sentry: opaque object comparison executed"
    assert counts == dict(build=0, dispatch=0, score=0)
