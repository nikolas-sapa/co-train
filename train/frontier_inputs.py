"""Hash-pinned synthetic frontier fixtures. Deliberately not a training gate.

Expected pins and identities belong to the caller, not the documents. Admission
delegates corpus/database identity to bench.prepare, never executes scoring SQL
or generation, and never writes a legacy/canonical manifest. Source hashes bind
selected local bytes, not authorship, genuine measurement or authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from types import MappingProxyType
from collections.abc import Mapping

from bench import prepare
from bench.frontier.probe import ProbeResult, dead_group_fraction, trainable_band
from bench.task import SqlTask, TIERS
from train import guards

_ROOT = Path(__file__).resolve().parents[1]
_MAX_BYTES = 16 << 20
_MANIFEST_BYTES = 64 << 10
_MAX_PLANNED = 100000
_MAX_SLOTS = 1000000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_EXTRA_SOURCES = (
    "bench/frontier/__init__.py", "bench/frontier/probe.py", "ptc/harness.py",
    "ptc/sql_arms.py", "ptc/sql_runtime.py", "train/__init__.py",
    "train/dead_group_probe.py", "train/ex_reward.py", "train/frontier_inputs.py",
    "train/grpo_ptc.py", "train/guards.py", "train/native_model.py",
    "train/native_runtime.py", "train/native_training.py", "train/sql_bridge.py",
    "train/verdict.py",
)
_SOURCE_PATHS = tuple(sorted(set(prepare.SOURCE_KEYS) | set(_EXTRA_SOURCES)))
_TOP = frozenset((
    "kind", "version", "fixture", "evidence_kind", "run_id", "manifest_sha256",
    "draw_sha256", "supplement_sha256", "raw_evidence_sha256", "identity",
    "settings", "sources", "candidates", "diagnostic", "counts",
))
_IDENTITY = frozenset((
    "policy", "runtime", "template", "generation_route_id",
    "generation_config_sha256", "prompt_config_sha256",
))
_POLICY = frozenset(("id", "revision", "artifact_inventory_sha256", "adapter_sha256"))
_RUNTIME = frozenset(("id", "revision", "environment_sha256"))
_TEMPLATE = frozenset((
    "tokenizer_inventory_sha256", "chat_template_sha256", "renderer_sha256",
    "tool_schema_sha256",
))
_SETTINGS = frozenset((
    "g", "dead_ceiling", "comparison", "scorer", "extractor", "timeout_s", "max_rows",
))
_CANDIDATE = frozenset((
    "id", "task_sha256", "db_id", "tier", "state", "exclusion", "prompt_sha256",
    "samples", "successes", "rate", "retained",
))
_SAMPLE = frozenset(("index", "status", "valid", "score", "evidence_sha256"))
_COUNTS = frozenset((
    "planned", "preparation_excluded", "eligible", "measured", "measurement_void",
    "retained", "sample_slots", "attempted_samples",
))
_DIAGNOSTIC = frozenset((
    "policy", "g", "dead_ceiling", "band_lo", "band_hi", "rates", "retained",
    "void", "compare",
))
_MANIFEST = frozenset((
    "policy", "pre_registration_amendment", "n_tasks", "solve_rate_min",
    "solve_rate_max", "measurement",
))
_MEASUREMENT = frozenset((
    "g", "dead_ceiling", "trainable_band", "n_candidates", "retention",
    "mean_dead_fraction", "n_void_tasks", "scorer", "compare",
))
_CATEGORIES = {
    "gold_error": "gold_execution_rejection",
    "gold_timeout": "configured_deadline",
    "gold_truncated": "configured_row_bound",
    "db_missing": "database_availability",
}
_VALID_ZERO = frozenset((
    "mismatch", "pred_error", "pred_timeout", "pred_truncated", "pred_empty",
))
_UNATTEMPTED = "not_attempted_after_void"


class FrontierInputsError(ValueError):
    """Bounded generic refusal, never raw document/task/error contents."""


class FrontierPublicationIndeterminateError(FrontierInputsError):
    """Commit occurred; complete final document preserved, do not retry."""


@dataclass(frozen=True)
class FrontierVoid:
    id: str
    status: str
    category: str


@dataclass(frozen=True)
class FixtureFrontierInputs:
    planned: tuple[SqlTask, ...]
    eligible: tuple[SqlTask, ...]
    retained: tuple[SqlTask, ...]
    preparation_exclusions: tuple[prepare.DrawExclusion, ...]
    measurement_voids: tuple[FrontierVoid, ...]
    artifact_digests: Mapping[str, str]
    raw_evidence_sha256: str
    counts: Mapping
    diagnostic: Mapping
    count_qualified: bool
    fixture: bool


def _fail(message="invalid frontier inputs"):
    raise FrontierInputsError(message)


def _boundary(fn):
    @wraps(fn)
    def checked(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except FrontierInputsError:
            raise
        except (OSError, ValueError, TypeError, RecursionError, OverflowError, MemoryError):
            raise FrontierInputsError("frontier inputs unavailable or invalid") from None
    return checked


def _keys(value, fields):
    if type(value) is not dict or value.keys() != fields:
        _fail()


def _id(value, limit=256):
    if type(value) is not str or not value or len(value.encode("utf-8")) > limit:
        _fail()


def _digest(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail("invalid retained digest")


def _integer(value, lo=0, hi=10 ** 20 - 1):
    if type(value) is not int or not lo <= value <= hi:
        _fail()


def _number(value, lo=None, hi=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        _fail()
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        _fail()


def _canonical(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _snapshot(value, *, limit=_MAX_BYTES):
    """Copy only ordinary JSON-shaped values, without calling supplied hooks.

    Account canonical encoding size while copying, so a caller cannot supply an
    unbounded in-memory producer ledger. No deepcopy/JSON default callbacks.
    """
    used = 0

    def charge(n):
        nonlocal used
        used += n
        if used > limit:
            _fail("frontier document exceeds bounds")

    def string(v):
        if len(v) > 256 or len(v.encode("utf-8")) > 256:
            _fail("frontier string exceeds bounds")
        charge(len(json.dumps(v, ensure_ascii=False).encode("utf-8")))

    def visit(v, depth):
        if type(v) is dict:
            if depth >= 32 or len(v) > _MAX_PLANNED:
                _fail("frontier document exceeds bounds")
            charge(2 + max(0, len(v) - 1))
            result = {}
            for key, item in v.items():
                if type(key) is not str:
                    _fail()
                string(key)
                charge(1)
                result[key] = visit(item, depth + 1)
            return result
        if type(v) in (list, tuple):
            if depth >= 32 or len(v) > _MAX_SLOTS:
                _fail("frontier document exceeds bounds")
            charge(2 + max(0, len(v) - 1))
            return [visit(item, depth + 1) for item in v]
        if type(v) is str:
            string(v)
        elif type(v) is bool or v is None:
            charge(len(json.dumps(v)))
        elif type(v) is int:
            if len(str(abs(v))) > 20:
                _fail("frontier integer exceeds bounds")
            charge(len(str(v)))
        elif type(v) is float:
            if not math.isfinite(v):
                _fail()
            charge(len(json.dumps(v, allow_nan=False)))
        else:
            _fail()
        return v

    return visit(value, 0)


def _preflight(raw):
    """Bound depth/numeric tokens outside strings BEFORE the JSON decoder."""
    text = raw.decode("utf-8", errors="strict")
    depth, quoted, escaped, i = 0, False, False, 0
    while i < len(text):
        c = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in "[{":
            depth += 1
            if depth > 32:
                _fail("frontier nesting exceeds bounds")
        elif c in "]}":
            depth -= 1
        elif c in "-0123456789":
            end = i + 1
            while end < len(text) and text[end] in "+-.0123456789eE":
                end += 1
            token = text[i:end]
            if len(token) > 128:
                _fail("frontier numeric token exceeds bounds")
            if not any(x in token for x in ".eE") and len(token.lstrip("-")) > 20:
                _fail("frontier integer exceeds bounds")
            i = end
            continue
        i += 1
    return text


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate frontier field")
        result[key] = value
    return result


def _constant(value):
    _fail("nonfinite frontier number")


def _parse(raw, *, canonical=False):
    text = _preflight(raw)
    doc = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    doc = _snapshot(doc)
    if canonical and raw != _canonical(doc):
        _fail("noncanonical frontier sidecar")
    return doc


def _preparation_documents(raws):
    """Validate retained metadata locally, never task question/evidence text.

    Call only after the complete artifact digest gate. Preparation owns its
    strict canonical schemas; these fixture APIs additionally own bounded
    collections, identifiers and counts before any delegated corpus admission.
    Do not apply the sidecar's blanket string snapshot to preparation documents.
    """
    for kind in ("draw", "supplement"):
        _preflight(raws[kind])
    draw = prepare._parse_draw(raws["draw"])
    supplement = prepare._parse_supplement(raws["supplement"])
    for collection in (draw["planned"], draw["identity"]["databases"],
                       supplement["planned_ids"], supplement["eligible_ids"],
                       supplement["exclusions"]):
        if len(collection) > _MAX_PLANNED:
            _fail("preparation collection bound exceeded")
    for entry in draw["planned"]:
        _id(entry["id"])
        _id(entry["db_id"])
    for entry in draw["identity"]["databases"]:
        _id(entry["db_id"])
    for key in draw["identity"]["source_sha256"]:
        _id(key, 128)
    for key in ("planned_ids", "eligible_ids"):
        for identifier in supplement[key]:
            _id(identifier)
    for entry in supplement["exclusions"]:
        _id(entry["id"])
    tier_counts = (
        draw["settings"]["per_tier"], draw["actual_per_tier"],
        draw["shortfall_per_tier"], *supplement["counts"].values(),
    )
    for counts in tier_counts:
        for count in counts.values():
            _integer(count, 0, _MAX_PLANNED)
        if sum(counts.values()) > _MAX_PLANNED:
            _fail("preparation count bound exceeded")
    for shapes in supplement["shapes"].values():
        for count in shapes.values():
            _integer(count, 0, _MAX_PLANNED)


def _identity(value):
    _keys(value, _IDENTITY)
    _keys(value["policy"], _POLICY)
    _keys(value["runtime"], _RUNTIME)
    _keys(value["template"], _TEMPLATE)
    for block in ("policy", "runtime"):
        _id(value[block]["id"])
        _id(value[block]["revision"])
    _digest(value["policy"]["artifact_inventory_sha256"])
    if value["policy"]["adapter_sha256"] is not None:
        _digest(value["policy"]["adapter_sha256"])
    _digest(value["runtime"]["environment_sha256"])
    for item in value["template"].values():
        _digest(item)
    _id(value["generation_route_id"])
    _digest(value["generation_config_sha256"])
    _digest(value["prompt_config_sha256"])


def _parameters(identity, amendment, raw_pin, g, ceiling, fixture):
    if fixture is not True:
        _fail("explicit synthetic fixture opt-in required")
    identity = _snapshot(identity)
    _identity(identity)
    _id(amendment)
    _digest(raw_pin)
    _integer(g, 2, _MAX_SLOTS)
    _number(ceiling)
    if not 0 < ceiling < 1:
        _fail()
    if not guards._amendment_is_signed(amendment, _ROOT):
        _fail("frontier amendment is not signed")
    return identity


def _no_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            _fail("frontier path traversal refused")


def _protected(path):
    canonical = _ROOT / "bench/frontier/manifest.json"
    if path == canonical or (path.exists() and canonical.exists() and path.samefile(canonical)):
        _fail("protected frontier manifest")
    # A broad caller-owned fixture root must not make a sibling checkout's
    # canonical manifest writable. Inspect repository markers, never its code.
    if path.name == "manifest.json" and path.parent.name == "frontier":
        if path.parent.parent.name == "bench":
            repository = path.parent.parent.parent
            if (repository / "bench/prepare.py").exists() and (
                repository / "train/__init__.py"
            ).exists():
                _fail("protected repository frontier manifest")


def _paths(fixture_root, corpus_root, artifacts, output=None):
    root = Path(os.path.abspath(fixture_root))
    _no_symlinks(root)
    if not root.is_dir():
        _fail("fixture directory unavailable")
    if root == _ROOT or root.is_relative_to(_ROOT) or (
        (root / "bench/prepare.py").exists() and (root / "train/__init__.py").exists()
    ):
        _fail("repository fixture root refused")
    corpus = Path(os.path.abspath(corpus_root))
    paths = {k: Path(os.path.abspath(v)) for k, v in artifacts.items()}
    for path in (corpus, *paths.values()):
        if not path.is_relative_to(root):
            _fail("frontier path outside fixture root")
        _no_symlinks(path)
        _protected(path)
    if not corpus.is_dir():
        _fail("fixture corpus unavailable")
    for path in paths.values():
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _fail("frontier artifact must be a private regular file")
    out = None
    if output is not None:
        out = Path(os.path.abspath(output))
        if not out.is_relative_to(root):
            _fail("frontier output outside fixture root")
        _no_symlinks(out)
        _protected(out)
        if not out.parent.is_dir():
            _fail("frontier output directory unavailable")
        for path in paths.values():
            if out == path or (out.exists() and out.samefile(path)):
                _fail("frontier output aliases an input")
    return root, corpus, paths, out


def _read_artifacts(paths, pins):
    # Complete the entire retained-digest gate before ANY decoder/admission call.
    raws = {}
    for kind, path in paths.items():
        _digest(pins[kind])
        _no_symlinks(path)
        _protected(path)
        st = path.stat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            _fail("frontier artifact identity unavailable")
        limit = _MANIFEST_BYTES if kind == "manifest" else _MAX_BYTES
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            _fail("frontier artifact exceeds bounds")
        expected_sha256 = pins[kind]
        actual_sha256 = hashlib.sha256(raw).hexdigest()
        if actual_sha256 != expected_sha256:
            _fail("retained artifact digest mismatch")
        raws[kind] = raw
    return raws


def _sources():
    result = {}
    for rel in _SOURCE_PATHS:
        path = _ROOT / rel
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        result[rel] = digest.hexdigest()
    return result


def _settings(settings, g, ceiling):
    _keys(settings, _SETTINGS)
    _integer(settings["g"], 2, _MAX_SLOTS)
    _number(settings["dead_ceiling"])
    if settings["g"] != g or settings["dead_ceiling"] != ceiling:
        _fail("frontier settings mismatch")
    if settings["comparison"] != "set" or settings["scorer"] != "bench.score.execution_accuracy":
        _fail()
    if settings["extractor"] != "bench.score.extract_sql":
        _fail()
    _number(settings["timeout_s"])
    _integer(settings["max_rows"], 1)
    if settings["timeout_s"] <= 0:
        _fail()


def _slots(slots, g):
    if type(slots) is not list or len(slots) != g:
        _fail("incomplete frontier sample ledger")
    wins, attempts, void = 0, 0, None
    for index, sample in enumerate(slots):
        _keys(sample, _SAMPLE)
        _integer(sample["index"])
        if sample["index"] != index:
            _fail()
        status = sample["status"]
        if type(status) is not str:
            _fail()
        if void is not None:
            if status != _UNATTEMPTED or any(
                sample[key] is not None for key in ("valid", "score", "evidence_sha256")
            ):
                _fail("attempted sample after measurement void")
            continue
        _digest(sample["evidence_sha256"])
        attempts += 1
        if status == "match" or status in _VALID_ZERO:
            _integer(sample["score"], 0, 1)
            if sample["valid"] is not True or sample["score"] != int(status == "match"):
                _fail()
            wins += sample["score"]
        elif status in _CATEGORIES:
            if sample["valid"] is not False or sample["score"] is not None:
                _fail()
            if status == "db_missing":
                _fail("database unavailable for frontier projection")
            void = status
        else:
            _fail("unsupported frontier sample status")
    return wins, attempts, void


def _ledger(candidates, identity, g, ceiling):
    if type(candidates) is not list or not 1 <= len(candidates) <= _MAX_PLANNED:
        _fail("frontier candidate count exceeds bounds")
    rates, retained, voids, seen = {}, [], [], set()
    excluded, attempts, eligible = 0, 0, 0
    for entry in candidates:
        _keys(entry, _CANDIDATE)
        _id(entry["id"])
        _id(entry["db_id"])
        _digest(entry["task_sha256"])
        if entry["id"] in seen or entry["tier"] not in TIERS:
            _fail()
        seen.add(entry["id"])
        if type(entry["retained"]) is not bool:
            _fail()
        state = entry["state"]
        if state == "preparation_excluded":
            excluded += 1
            _keys(entry["exclusion"], frozenset(("status", "category")))
            status = entry["exclusion"]["status"]
            if type(status) is not str or status not in _CATEGORIES:
                _fail()
            if status == "db_missing" or entry["exclusion"]["category"] != _CATEGORIES[status]:
                _fail()
            if entry["samples"] != [] or any(
                entry[k] is not None for k in ("prompt_sha256", "successes", "rate")
            ) or entry["retained"]:
                _fail()
            continue
        if state not in ("measured", "measurement_void") or entry["exclusion"] is not None:
            _fail()
        eligible += 1
        if eligible * g > _MAX_SLOTS:
            _fail("frontier sample slots exceed bounds")
        _digest(entry["prompt_sha256"])
        wins, attempted, void = _slots(entry["samples"], g)
        attempts += attempted
        if void is not None:
            if state != "measurement_void" or entry["successes"] is not None:
                _fail()
            if entry["rate"] is not None or entry["retained"]:
                _fail()
            voids.append(FrontierVoid(entry["id"], void, _CATEGORIES[void]))
        else:
            _integer(entry["successes"], 0, g)
            _number(entry["rate"], 0, 1)
            rate = wins / g
            keep = dead_group_fraction(rate, g) <= ceiling
            if state != "measured" or entry["successes"] != wins or entry["rate"] != rate:
                _fail()
            if entry["retained"] is not keep:
                _fail("frontier retention inequality mismatch")
            rates[entry["id"]] = rate
            if keep:
                retained.append(entry["id"])
    lo, hi = trainable_band(ceiling, g)
    probe = ProbeResult(
        policy=identity["policy"]["id"], g=g, dead_ceiling=ceiling,
        band_lo=lo, band_hi=hi, rates=rates, retained=retained,
        void={v.id: v.status for v in voids}, compare="set",
    )
    counts = dict(
        planned=len(candidates), preparation_excluded=excluded, eligible=eligible,
        measured=len(rates), measurement_void=len(voids), retained=len(retained),
        sample_slots=eligible * g, attempted_samples=attempts,
    )
    return probe, counts, tuple(voids)


def _check_diagnostic(diagnostic, reconstructed):
    _keys(diagnostic, _DIAGNOSTIC)
    _integer(diagnostic["g"], 2, _MAX_SLOTS)
    for key in ("dead_ceiling", "band_lo", "band_hi"):
        _number(diagnostic[key], 0, 1)
    if type(diagnostic["rates"]) is not dict or type(diagnostic["void"]) is not dict:
        _fail()
    for key, value in diagnostic["rates"].items():
        _id(key)
        _number(value, 0, 1)
    for key, value in diagnostic["void"].items():
        _id(key)
        if type(value) is not str or value not in _CATEGORIES:
            _fail()
    if type(diagnostic["retained"]) is not list:
        _fail()
    for key in diagnostic["retained"]:
        _id(key)
    # Separate exact membership guard: never a tolerance or a set intersection.
    if diagnostic["retained"] != reconstructed.retained:
        _fail("frontier retained membership mismatch")
    report = reconstructed.report()
    for key in _DIAGNOSTIC - {"retained"}:
        if diagnostic[key] != report[key]:
            _fail("frontier diagnostic reconstruction mismatch")


def _manifest(manifest, probe, amendment):
    _keys(manifest, _MANIFEST)
    measurement = manifest["measurement"]
    _keys(measurement, _MEASUREMENT)
    expected = probe.manifest(amendment)  # Existing empty-frontier refusal.
    for key in ("n_tasks",):
        _integer(manifest[key], 1, _MAX_PLANNED)
    for key in ("solve_rate_min", "solve_rate_max"):
        _number(manifest[key], 0, 1)
    for key in _MANIFEST - {"measurement"}:
        if manifest[key] != expected[key]:
            _fail("frontier manifest reconstruction mismatch")
    for key in ("g", "n_candidates", "n_void_tasks"):
        _integer(measurement[key])
    for key in ("dead_ceiling", "retention", "mean_dead_fraction"):
        _number(measurement[key], 0, 1)
    band = measurement["trainable_band"]
    if type(band) is not list or len(band) != 2:
        _fail()
    for endpoint in band:
        _number(endpoint, 0, 1)
    for key in _MEASUREMENT:
        actual, want = measurement[key], expected["measurement"][key]
        if key == "trainable_band":
            if any(abs(a - b) > 1e-6 for a, b in zip(actual, want)):
                _fail("frontier manifest band mismatch")
        elif key == "retention":
            if abs(actual - want) > 1e-6:
                _fail("frontier manifest retention mismatch")
        elif actual != want:
            _fail("frontier manifest measurement mismatch")


def _check_document(doc, pins, raw_pin, identity, g, ceiling, sources):
    _keys(doc, _TOP)
    _integer(doc["version"], 1, 1)
    if doc["kind"] != "cotrain-frontier-sidecar" or doc["fixture"] is not True:
        _fail()
    if doc["evidence_kind"] != "synthetic_fixture":
        _fail("real measurement evidence is not accepted")
    _id(doc["run_id"])
    for kind in ("draw", "supplement", "manifest"):
        _digest(doc[kind + "_sha256"])
        if doc[kind + "_sha256"] != pins[kind]:
            _fail("frontier artifact link mismatch")
    _digest(doc["raw_evidence_sha256"])
    if doc["raw_evidence_sha256"] != raw_pin:
        _fail("frontier raw evidence pin mismatch")
    _identity(doc["identity"])
    if doc["identity"] != identity:
        _fail("frontier identity mismatch")
    _settings(doc["settings"], g, ceiling)
    if type(doc["sources"]) is not dict:
        _fail()
    for key, value in doc["sources"].items():
        _id(key, 128)
        _digest(value)
    if doc["sources"] != sources:
        _fail("frontier source binding mismatch")
    _keys(doc["counts"], _COUNTS)
    for key, value in doc["counts"].items():
        _integer(value, 0, _MAX_SLOTS if key in ("sample_slots", "attempted_samples") else _MAX_PLANNED)
    probe, counts, voids = _ledger(doc["candidates"], identity, g, ceiling)
    if doc["counts"] != counts:
        _fail("frontier count reconstruction mismatch")
    _check_diagnostic(doc["diagnostic"], probe)
    return probe, counts, voids


def _admit(corpus, paths, pins):
    try:
        return prepare.load_validated_draw(
            corpus, paths["draw"], paths["supplement"],
            expected_draw_sha256=pins["draw"],
            expected_supplement_sha256=pins["supplement"], fixture=True,
        )
    except (KeyError, AttributeError):
        # The actual corpus loader can encounter missing question fields or
        # nonstring evidence. Normalize only this delegated admission boundary.
        raise FrontierInputsError("frontier corpus records rejected") from None


def _join(doc, admitted):
    if [c["id"] for c in doc["candidates"]] != [t.name for t in admitted.planned]:
        _fail("frontier planned membership mismatch")
    settings = doc["settings"]
    if (settings["timeout_s"] != admitted.timeout_s or
            settings["max_rows"] != admitted.max_rows or
            settings["comparison"] != admitted.comparison):
        _fail("frontier preparation settings mismatch")
    excluded = {e.id: e for e in admitted.exclusions}
    for entry, task in zip(doc["candidates"], admitted.planned):
        if (entry["task_sha256"] != prepare._task_sha256(task) or
                entry["db_id"] != task.db_id or entry["tier"] != task.tier):
            _fail("frontier task identity mismatch")
        exclusion = excluded.get(task.name)
        if exclusion is not None:
            if entry["state"] != "preparation_excluded" or entry["exclusion"] != {
                "status": exclusion.status, "category": exclusion.category,
            }:
                _fail("frontier preparation exclusion mismatch")
        elif entry["state"] == "preparation_excluded":
            _fail("frontier eligible membership mismatch")


def _recheck(corpus, paths, pins, sources, doc):
    _read_artifacts(paths, pins)
    if _sources() != sources:
        _fail("frontier source drift")
    fresh = _admit(corpus, paths, pins)
    _join(doc, fresh)
    # Also catch changes during the final admission, before returning/publishing.
    _read_artifacts(paths, pins)
    if _sources() != sources:
        _fail("frontier source drift")
    return fresh


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if type(value) is list:
        return tuple(_freeze(v) for v in value)
    return value


@_boundary
def load_fixture_frontier_inputs(
    fixture_root, corpus_root, draw_path, supplement_path, manifest_path, sidecar_path,
    *, expected_draw_sha256, expected_supplement_sha256, expected_manifest_sha256,
    expected_sidecar_sha256, expected_raw_evidence_sha256, expected_identity,
    expected_amendment, expected_g, expected_dead_ceiling, fixture=False,
) -> FixtureFrontierInputs:
    identity = _parameters(
        expected_identity, expected_amendment, expected_raw_evidence_sha256,
        expected_g, expected_dead_ceiling, fixture,
    )
    _, corpus, paths, _ = _paths(fixture_root, corpus_root, dict(
        draw=draw_path, supplement=supplement_path, manifest=manifest_path, sidecar=sidecar_path,
    ))
    pins = dict(draw=expected_draw_sha256, supplement=expected_supplement_sha256,
                manifest=expected_manifest_sha256, sidecar=expected_sidecar_sha256)
    raws = _read_artifacts(paths, pins)
    _preparation_documents(raws)
    doc = _parse(raws["sidecar"], canonical=True)
    manifest = _parse(raws["manifest"])
    sources = _sources()
    probe, counts, voids = _check_document(
        doc, pins, expected_raw_evidence_sha256, identity,
        expected_g, expected_dead_ceiling, sources,
    )
    _manifest(manifest, probe, expected_amendment)
    admitted = _admit(corpus, paths, pins)
    _join(doc, admitted)
    fresh = _recheck(corpus, paths, pins, sources, doc)
    keep = frozenset(probe.retained)
    return FixtureFrontierInputs(
        planned=fresh.planned, eligible=fresh.eligible,
        retained=tuple(t for t in fresh.planned if t.name in keep),
        preparation_exclusions=fresh.exclusions, measurement_voids=voids,
        artifact_digests=_freeze(pins), raw_evidence_sha256=expected_raw_evidence_sha256,
        counts=_freeze(counts), diagnostic=_freeze(probe.report()),
        count_qualified=len(keep) >= guards.MIN_FRONTIER_TASKS, fixture=True,
    )


def _records(records, g):
    if type(records) is not list or not 1 <= len(records) <= _MAX_PLANNED:
        _fail()
    if len(records) * g > _MAX_SLOTS:
        _fail("frontier sample slots exceed bounds")
    for record in records:
        _keys(record, frozenset(("id", "prompt_sha256", "samples")))
        _id(record["id"])
        _digest(record["prompt_sha256"])
        _slots(record["samples"], g)


def _assemble(admitted, records, run_id, identity, pins, raw_pin, g, ceiling, sources):
    if [r["id"] for r in records] != [t.name for t in admitted.eligible]:
        _fail("frontier producer eligible membership mismatch")
    by_id = {r["id"]: r for r in records}
    excluded = {e.id: e for e in admitted.exclusions}
    ledger = []
    for task in admitted.planned:
        entry = dict(
            id=task.name, task_sha256=prepare._task_sha256(task), db_id=task.db_id,
            tier=task.tier, state="preparation_excluded", exclusion=None,
            prompt_sha256=None, samples=[], successes=None, rate=None, retained=False,
        )
        if task.name in excluded:
            e = excluded[task.name]
            entry["exclusion"] = dict(status=e.status, category=e.category)
        else:
            record = by_id[task.name]
            wins, _, void = _slots(record["samples"], g)
            entry.update(prompt_sha256=record["prompt_sha256"], samples=record["samples"])
            if void is not None:
                entry["state"] = "measurement_void"
            else:
                rate = wins / g
                entry.update(
                    state="measured", successes=wins, rate=rate,
                    retained=dead_group_fraction(rate, g) <= ceiling,
                )
        ledger.append(entry)
    probe, counts, _ = _ledger(ledger, identity, g, ceiling)
    return dict(
        kind="cotrain-frontier-sidecar", version=1, fixture=True,
        evidence_kind="synthetic_fixture", run_id=run_id,
        manifest_sha256=pins["manifest"], draw_sha256=pins["draw"],
        supplement_sha256=pins["supplement"], raw_evidence_sha256=raw_pin,
        identity=identity,
        settings=dict(g=g, dead_ceiling=ceiling, comparison=admitted.comparison,
                      scorer="bench.score.execution_accuracy", extractor="bench.score.extract_sql",
                      timeout_s=admitted.timeout_s, max_rows=admitted.max_rows),
        sources=sources, candidates=ledger, diagnostic=probe.report(), counts=counts,
    ), probe


def _publish(data, output):
    """Create-only hard-link commit. No overwrite-capable rename or retry."""
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=".frontier-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    try:
        os.unlink(temporary)
        fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        raise FrontierPublicationIndeterminateError(
            "frontier publication indeterminate; complete final document preserved"
        ) from None
    return hashlib.sha256(data).hexdigest()


@_boundary
def write_fixture_frontier_sidecar(
    fixture_root, corpus_root, draw_path, supplement_path, manifest_path, output,
    *, expected_draw_sha256, expected_supplement_sha256, expected_manifest_sha256,
    expected_raw_evidence_sha256, expected_identity, expected_amendment,
    samples, run_id, g, dead_ceiling, fixture=False,
) -> str:
    identity = _parameters(
        expected_identity, expected_amendment, expected_raw_evidence_sha256,
        g, dead_ceiling, fixture,
    )
    records = _snapshot(samples)
    _id(run_id)
    _records(records, g)
    root, corpus, paths, out = _paths(
        fixture_root, corpus_root,
        dict(draw=draw_path, supplement=supplement_path, manifest=manifest_path), output,
    )
    pins = dict(draw=expected_draw_sha256, supplement=expected_supplement_sha256,
                manifest=expected_manifest_sha256)
    raws = _read_artifacts(paths, pins)
    _preparation_documents(raws)
    manifest = _parse(raws["manifest"])
    sources = _sources()
    admitted = _admit(corpus, paths, pins)
    doc, probe = _assemble(
        admitted, records, run_id, identity, pins, expected_raw_evidence_sha256,
        g, dead_ceiling, sources,
    )
    _join(doc, admitted)
    _manifest(manifest, probe, expected_amendment)
    _recheck(corpus, paths, pins, sources, doc)
    data = _canonical(doc)
    if len(data) > _MAX_BYTES:
        _fail("frontier sidecar exceeds bounds")
    # Recheck output traversal/aliases immediately before create-only publication.
    _paths(root, corpus, paths, out)
    return _publish(data, out)


__all__ = [
    "FixtureFrontierInputs", "FrontierVoid", "FrontierInputsError",
    "FrontierPublicationIndeterminateError", "load_fixture_frontier_inputs",
    "write_fixture_frontier_sidecar",
]
