"""Is the far side of the relay the same thing it was last time? Model identity is not
verifiable from here; this pins the serving stack so a swap stops being silent.

`docs/deviations.md` records the standing threat verbatim: VyceAI is a third-party relay,
and *"what `deepseek-v4-flash` means on the other side of it is not verifiable from
here"*. Every real-mode number in this project assumes both arms met the same model.
Nothing checked it.

**What a client can and cannot establish, measured 2026-10-09 rather than assumed:**

- `/v1/models` gates the id -- an unlisted id is refused with `model_not_found` (400),
  so `--model deepseek-v4-flash` is a recognised id and not free text silently mapped to
  a default. The listing attributes it to `owned_by: "vyce"`, not `"deepseek"`, while the
  sibling id `deepseek-v4.1` is attributed to `"deepseek"`. Provenance is self-declared
  and it declares the relay, so a change in that field is a change of story.
- The response echoes `model` back. It is the request's own string; it constrains nothing.
- `system_fingerprint` is **random per request** (five distinct values in five calls), so
  it is recorded and deliberately NOT part of the verdict. The obvious design keys on it
  and would report a model swap on every single run.
- `usage.prompt_tokens` is the one deterministic, sampling-free number the relay returns,
  which makes it the strongest available signature -- and it does not come from the model.
  It equals `cl100k_base` over the raw message content *exactly* on short prompts, with
  zero chat-template overhead, and exceeds every standard tokenizer by 43-56% above
  ~3.8k tokens. It is a relay-side count, not a provider-billed one.

**So this tool cannot tell you what model answers.** A backend swapped behind a stable id,
with the token count computed relay-side either way, passes every check here. That is a
limit of the client's position, not of the check. What it does detect: the id being
withdrawn or re-attributed, the echoed model changing, the token-accounting signature
moving, and a known-answer probe failing.

Pass criteria, declared before the baseline was recorded so the result cannot be read off
the numbers afterwards:

1. the id is listed, and its `owned_by` matches the baseline -- exact
2. the echoed `model` equals the requested id -- exact
3. every probe's `prompt_tokens` equals the baseline -- exact, zero tolerance, because
   no sampling enters it
4. every probe carrying an `expect` returns it, normalised -- exact

Reported but never red: answer prefixes, latency, completion tokens, `system_fingerprint`,
and the relay/`cl100k` ratio. The ratio is the quantity the cost co-primary is computed
from, so it is printed on every run whether or not it moved.

Usage: python -m ptc.relay_audit record <baseline.json> [--model ... --base-url ...]
       python -m ptc.relay_audit check  <baseline.json> [...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Cloudflare in front of the relay answers `error code: 1010` -- a 403 with a text/plain
# body -- to urllib's default User-Agent. It is a browser-signature block, not auth and
# not an outage, and it reads as "the relay is down" to anyone who does not know. The
# harness reaches the same endpoint through httpx, which is not blocked, so the probe
# borrows its agent string.
USER_AGENT = "python-httpx/0.28.1"

# The probe prompts are fixed, so their `cl100k_base` lengths are fixed. They are pinned
# here as constants rather than recomputed, which keeps this module on the standard
# library -- `tiktoken` is a `verifiers` transitive, not a declared dependency of this
# repo, and a tokenizer download is not something an audit should need at run time.
# `verify_probe_texts` makes the pins falsifiable: edit a prompt and it raises.
#
# Three prompts, chosen for where they sit relative to the divergence:
#   english  38 tokens  -- short, Latin, the regime where the relay's count is exact
#   cjk      86 tokens  -- short, non-Latin, where tokenizer families diverge most and
#                          where cl100k is notably inefficient, so an exact match there
#                          is evidence about the counter rather than a coincidence
#   bulk  3,856 tokens  -- above the divergence, and the regime 38.7% of the bash arm's
#                          published prompt tokens live in against 1.9% of PTC's
_UNIT = ("Record 41 belongs to Delta Holdings and carries an invoice amount of "
         "one hundred and seventeen euros, settled on the fourth of March. ")

PROBES: tuple[dict, ...] = (
    {
        "name": "english",
        "prompt": ("The quick brown fox jumps over the lazy dog near the riverbank at "
                   "dawn, while seventeen careful accountants reconcile the quarterly "
                   "ledger and three auditors quietly verify every single invoice twice "
                   "before lunch."),
        "sha256": "8f373ea96b4ae389",
        "cl100k": 38,
        "expect": None,
    },
    {
        "name": "cjk",
        "prompt": ("人工智能模型的分词器会把中文文本切分成不同数量的标记，这取决于词表的构建方式。"
                   "人工智能模型的分词器会把中文文本切分成不同数量的标记，这取决于词表的构建方式。"),
        "sha256": "1af2e261c093d4af",
        "cl100k": 86,
        "expect": None,
    },
    {
        "name": "bulk",
        "prompt": _UNIT * 148 + "\nReply with exactly one word: ACK",
        "sha256": "93b8c084721e4997",
        "cl100k": 3856,
        # A known-answer probe, and the only answer in the set short enough to be worth
        # comparing: the chatty probes above are prose and would drift on any run.
        "expect": "ACK",
    },
)

HARD = ("listed", "owned_by", "served_model", "prompt_tokens", "expect")
"""Which drift kinds make the check red. Everything else is reported and advisory."""


def verify_probe_texts() -> None:
    """Raise if a probe's text no longer matches the length pinned beside it.

    The pinned `cl100k` counts are the denominator of the ratio this tool reports, and
    editing a prompt without updating them would move that ratio without moving the
    endpoint. The hash is what makes the pin checkable without a tokenizer.
    """
    for p in PROBES:
        got = hashlib.sha256(p["prompt"].encode()).hexdigest()[:16]
        if got != p["sha256"]:
            raise ValueError(
                f"probe {p['name']!r} text changed (sha256 {got} != {p['sha256']}); "
                f"recompute its pinned cl100k count before trusting any ratio")


def post(base_url: str, key: str, path: str, body: dict | None,
         timeout: float = 600.0) -> dict:
    """One exchange with the relay. Returns status, headers and parsed body.

    A 4xx body is read and returned rather than raised: `model_not_found` is a *result*
    here, and the audit's job is to report what the endpoint said.
    """
    url = base_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("User-Agent", USER_AGENT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status, headers = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, headers = e.read(), e.code, dict(e.headers)
    text = raw.decode("utf-8", "replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"_nonjson": text[:200]}
    return {"status": status, "headers": headers, "body": parsed,
            "elapsed": time.time() - started}


def listing_row(call, model: str) -> dict:
    """The `/v1/models` row for this id, reduced to the fields that carry provenance.

    `created` is identical (1719792000) across all seven listed ids and `context_window`
    is shared by three different vendors' models, so both are templated placeholders and
    neither is recorded as evidence.
    """
    r = call("/models", None)
    rows = (r["body"].get("data") if isinstance(r["body"], dict) else None) or []
    mine = [x for x in rows if x.get("id") == model]
    return {
        "status": r["status"],
        "listed": bool(mine),
        "owned_by": mine[0].get("owned_by") if mine else None,
        "n_listed": len(rows),
        "ids": sorted(x.get("id", "") for x in rows),
    }


def normalise(text: str) -> str:
    """Collapse whitespace and case so an answer comparison is about content."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def probe_once(call, model: str, probe: dict) -> dict:
    """Send one probe and keep the fields that fingerprint the serving stack.

    `temperature: 0` is asked for and `max_tokens` is sent, but neither is load-bearing:
    the relay ignores `max_tokens` (`docs/deviations.md`, Endpoint note), and the verdict
    rests on `prompt_tokens`, which no sampling setting can move.
    """
    r = call("/chat/completions", {
        "model": model, "temperature": 0, "max_tokens": 16,
        "messages": [{"role": "user", "content": probe["prompt"]}],
    })
    body = r["body"] if isinstance(r["body"], dict) else {}
    usage = body.get("usage") or {}
    choice = (body.get("choices") or [{}])[0]
    answer = ((choice.get("message") or {}).get("content")) or ""
    prompt_tokens = usage.get("prompt_tokens")
    return {
        "name": probe["name"],
        "status": r["status"],
        "served_model": body.get("model"),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "cl100k": probe["cl100k"],
        # Printed on every run because it is the factor between what the relay charges
        # for and what the text actually tokenizes to, and the cost co-primary is
        # computed from the relay's side of it.
        "ratio": (round(prompt_tokens / probe["cl100k"], 4)
                  if isinstance(prompt_tokens, int) else None),
        "system_fingerprint": body.get("system_fingerprint"),
        "answer_prefix": normalise(answer)[:60],
        "expect_met": (None if not probe["expect"]
                       else normalise(answer) == normalise(probe["expect"])),
        "seconds": round(r["elapsed"], 2),
        "error": body.get("error"),
    }


def fingerprint(call, model: str) -> dict:
    """The whole signature: the listing row plus one row per probe."""
    verify_probe_texts()
    return {
        "model": model,
        "recorded": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "listing": listing_row(call, model),
        "probes": [probe_once(call, model, p) for p in PROBES],
    }


def compare(baseline: dict, current: dict) -> list[dict]:
    """Every field that moved, one row each, hard ones flagged.

    A missing probe counts as drift rather than being skipped: a relay that stops
    answering one prompt has changed, and a comparison that only looks at the rows both
    runs happen to share is the defect `paired.py` already carried once -- it intersected
    task names and reported n=12 on a 29-task run.
    """
    out: list[dict] = []

    def row(kind: str, where: str, was, now) -> None:
        if was != now:
            out.append({"kind": kind, "where": where, "was": was, "now": now,
                        "hard": kind in HARD})

    row("listed", "models", baseline["listing"]["listed"], current["listing"]["listed"])
    row("owned_by", "models", baseline["listing"]["owned_by"],
        current["listing"]["owned_by"])
    row("ids", "models", baseline["listing"]["ids"], current["listing"]["ids"])

    was_probes = {p["name"]: p for p in baseline["probes"]}
    now_probes = {p["name"]: p for p in current["probes"]}
    for name in sorted(set(was_probes) | set(now_probes)):
        a, b = was_probes.get(name, {}), now_probes.get(name, {})
        if not a or not b:
            out.append({"kind": "prompt_tokens", "where": name,
                        "was": a.get("prompt_tokens"), "now": b.get("prompt_tokens"),
                        "hard": True})
            continue
        row("prompt_tokens", name, a.get("prompt_tokens"), b.get("prompt_tokens"))
        row("served_model", name, a.get("served_model"), b.get("served_model"))
        row("expect", name, a.get("expect_met"), b.get("expect_met"))
        row("answer_prefix", name, a.get("answer_prefix"), b.get("answer_prefix"))
        row("completion_tokens", name, a.get("completion_tokens"),
            b.get("completion_tokens"))
    return out


def verdict(current: dict, drift: list[dict]) -> tuple[bool, list[str]]:
    """`(ok, reasons)`. Red on any hard drift, and on a baseline that is already broken.

    The second half matters: a `check` against a baseline recorded when the id was
    already unlisted would otherwise pass by agreeing with it.
    """
    reasons = [f"{d['kind']} on {d['where']}: {d['was']!r} -> {d['now']!r}"
               for d in drift if d["hard"]]
    if not current["listing"]["listed"]:
        reasons.append(f"{current['model']} is not in /v1/models")
    for p in current["probes"]:
        if p["status"] != 200:
            reasons.append(f"probe {p['name']} answered {p['status']}: {p.get('error')}")
        elif p["served_model"] != current["model"]:
            reasons.append(f"probe {p['name']} served {p['served_model']!r}, "
                           f"requested {current['model']!r}")
        elif p["expect_met"] is False:
            reasons.append(f"probe {p['name']} missed its known answer: "
                           f"{p['answer_prefix']!r}")
    return (not reasons), reasons


def render(fp: dict) -> str:
    lines = [f"model {fp['model']}  recorded {fp['recorded']}",
             f"listed {fp['listing']['listed']}  owned_by "
             f"{fp['listing']['owned_by']!r}  of {fp['listing']['n_listed']} ids",
             "",
             f"{'probe':<10}{'status':>7}{'prompt':>8}{'cl100k':>8}{'ratio':>8}"
             f"{'compl':>7}{'secs':>7}  {'fingerprint':<16}answer",
             "-" * 100]
    for p in fp["probes"]:
        lines.append(
            f"{p['name']:<10}{p['status']:>7}{str(p['prompt_tokens']):>8}"
            f"{p['cl100k']:>8}{str(p['ratio']):>8}{str(p['completion_tokens']):>7}"
            f"{p['seconds']:>7}  {str(p['system_fingerprint']):<16}"
            f"{p['answer_prefix'][:30]}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("record", "check"))
    parser.add_argument("baseline")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--base-url", default="https://vyceai.com/v1")
    parser.add_argument("--key-var", default="VYCEAI_API_KEY")
    args = parser.parse_args(argv[1:])

    key = os.environ.get(args.key_var)
    if not key:
        print(f"{args.key_var} is not set", file=sys.stderr)
        return 2

    def call(path: str, body: dict | None) -> dict:
        return post(args.base_url, key, path, body)

    current = fingerprint(call, args.model)
    print(render(current))
    path = Path(args.baseline).expanduser()

    if args.mode == "record":
        ok, reasons = verdict(current, [])
        if not ok:
            print("\nREFUSING to record a baseline that is already red:", file=sys.stderr)
            for r in reasons:
                print(f"  {r}", file=sys.stderr)
            return 1
        path.write_text(json.dumps(current, indent=1, ensure_ascii=False))
        print(f"\nbaseline written to {path}")
        return 0

    baseline = json.loads(path.read_text())
    drift = compare(baseline, current)
    print(f"\nbaseline {baseline['recorded']} -> now  ({len(drift)} field(s) moved)")
    for d in drift:
        print(f"  {'HARD' if d['hard'] else 'soft'}  {d['kind']} on {d['where']}: "
              f"{d['was']!r} -> {d['now']!r}")
    ok, reasons = verdict(current, drift)
    print("\nRELAY STABLE" if ok else "\nRELAY CHANGED -- every real-mode number in this "
          "project assumes it did not:")
    for r in reasons:
        print(f"  {r}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
