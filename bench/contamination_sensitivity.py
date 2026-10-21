"""Sensitivity analyses for the contamination check, run on the recorded results.

**Why this file exists rather than being thrown away.** The primary run's gold-SQL
channel returned FAIL (AUC 0.765 / 0.829). The length-matched analysis below shows that
result is a **style/length confound**, not a contamination signal: BIRD's golds average
54.0 tokens against the fresh control's 21.2, the Min-K% score correlates with length
within BIRD itself (Pearson r = 0.50 and 0.57), and matching on length moves BIRD to or
below chance. The stratified estimate is near chance but its interval is too wide to
exclude a moderate effect, which is why the final verdict is **INCONCLUSIVE**, not PASS.

Run it after `--out` has produced a results JSON:

    ~/scratch/cotrain-contam/venv/bin/python -m bench.contamination_sensitivity \
        bench/contamination_results_v2.json

The fresh control is read from the results file's own `fresh_control.path`, so a v2 result
is analysed against v2 and a v1 result against v1 with no flag; a second positional
argument overrides it. The per-bin length table it prints is the measured length match,
not a claim about one.

It needs torch only for the tokenizer; the statistics are the same pure functions as
`bench.contamination`.
"""

from __future__ import annotations

import json
import sys

import numpy as np

from bench import contamination as C

# Fresh-gold token-length bins chosen to mirror the fresh set's own quartiles; the top bin
# is open-ended because BIRD's long tail has no fresh counterpart and the pair weight it
# receives is bounded by the fresh count in that bin.
LENGTH_BINS = ((1, 12), (13, 16), (17, 20), (21, 28), (29, 1000))


def token_lengths(sqls: list[str], tok) -> np.ndarray:
    return np.array([len(tok(s, add_special_tokens=False).input_ids) for s in sqls])


def stratified_auc(bird_scores, bird_lens, fresh_scores, fresh_lens) -> tuple[float, int]:
    """AUC computed only over BIRD/fresh pairs whose gold lengths fall in the same bin,
    pooled across bins. The estimator the primary statistic should have been: it asks
    whether BIRD is more likely than a fresh query **of comparable length**.

    Returns (auc, n_pairs). A bin with no fresh items contributes no pairs, which is the
    honest treatment: there is nothing to compare against there.
    """
    b = np.asarray(bird_scores)
    f = np.asarray(fresh_scores)
    wins = total = 0.0
    for lo, hi in LENGTH_BINS:
        bb = b[(bird_lens >= lo) & (bird_lens <= hi)]
        ff = f[(fresh_lens >= lo) & (fresh_lens <= hi)]
        if bb.size == 0 or ff.size == 0:
            continue
        diff = bb[:, None] - ff[None, :]
        wins += (diff > 0).sum() + 0.5 * (diff == 0).sum()
        total += diff.size
    if total == 0:
        raise ValueError("no same-bin pairs")
    return wins / total, int(total)


def stratified_ci(bird_scores, bird_lens, fresh_scores, fresh_lens, *,
                  n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Bootstrap the FRESH side (BIRD is the fixed reference set), percentile interval."""
    f = np.asarray(fresh_scores)
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(f), len(f))
        stats.append(stratified_auc(bird_scores, bird_lens, f[idx], fresh_lens[idx])[0])
    stats.sort()
    return stats[int(0.025 * (len(stats) - 1))], stats[int(0.975 * (len(stats) - 1))]


def bin_table(ls, label: str) -> list[dict]:
    """Per-bin count, share, mean and median for one length vector. The published
    length-match table is built from this and nothing else, so the numbers in
    `docs/contamination.md` are a rendering of it rather than a re-derivation."""
    out = []
    for lo, hi in LENGTH_BINS:
        xs = [x for x in ls if lo <= x <= hi]
        out.append({
            "bin": f"{lo}-{hi}" if hi < 1000 else f"{lo}+",
            "n": len(xs),
            "share": len(xs) / len(ls),
            "mean": float(np.mean(xs)) if xs else None,
            "median": float(np.median(xs)) if xs else None,
        })
    return out


def main(path: str, fresh_path: str | None = None) -> int:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("unsloth/Qwen3-0.6B")
    d = json.load(open(path))
    rs = d["raw_scores"]
    bird_lens = token_lengths([t["gold_sql"] for t in d["bird"]], tok)
    if fresh_path is None:
        fresh_path = (d.get("fresh_control") or {}).get("path") or str(C.FRESH_PATH)
    fresh = C.load_fresh(fresh_path)
    fresh_lens = token_lengths([p["sql"] for p in fresh], tok)

    print(f"lengths: BIRD mean {bird_lens.mean():.1f} median {np.median(bird_lens):.0f}"
          f" | fresh mean {fresh_lens.mean():.1f} median {np.median(fresh_lens):.0f}")
    print(f"fresh control: {fresh_path}")
    print("bin      BIRD n  share   mean  median | fresh n  share   mean  median")
    bt, ft = bin_table(bird_lens, "bird"), bin_table(fresh_lens, "fresh")
    for b, f in zip(bt, ft):
        print(f"{b['bin']:<8} {b['n']:6d}  {b['share']:.3f}  "
              f"{(b['mean'] or 0):5.1f}  {(b['median'] or 0):6.1f} | "
              f"{f['n']:6d}  {f['share']:.3f}  "
              f"{(f['mean'] or 0):5.1f}  {(f['median'] or 0):6.1f}")
    out = {"lengths": {"bird_mean": float(bird_lens.mean()),
                       "bird_median": float(np.median(bird_lens)),
                       "fresh_mean": float(fresh_lens.mean()),
                       "fresh_median": float(np.median(fresh_lens)),
                       "fresh_path": str(fresh_path)},
           "bins": {"bird": bt, "fresh": ft}}
    for method in ("min_k", "min_kpp"):
        b = rs[f"bird_sql_{method}"]
        f = rs[f"fresh_sql_{method}"]
        r = float(np.corrcoef(bird_lens, b)[0, 1])
        auc, n = stratified_auc(b, bird_lens, f, fresh_lens)
        lo, hi = stratified_ci(b, bird_lens, f, fresh_lens)
        print(f"{method}: pearson(len, score) within BIRD = {r:+.3f}")
        print(f"  unstratified AUC {C.auroc(b, f):.3f}; stratified AUC {auc:.3f}"
              f" over {n} same-bin pairs, 95% CI [{lo:.3f}, {hi:.3f}]")
        out[method] = {"pearson_len_score": r, "unstratified_auc": C.auroc(b, f),
                       "stratified_auc": auc, "n_pairs": n, "ci": [lo, hi]}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    fresh_arg = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(main(sys.argv[1], fresh_arg))
