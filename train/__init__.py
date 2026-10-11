"""Step 4 — co-training the PTC arm.

Two things live here, and they are at different maturity levels on purpose:

- `dead_group_probe.py` + `verdict.py` are **finished and runnable**. The probe
  is the one GPU spend `docs/spec-cotrain.md` authorises (§270-298): it needs no
  working benchmark, because it measures the reward's geometry rather than the
  model's competence, and it aborts in 5-20 steps.
- `grpo_ptc.py` is **scaffolding with live guards and a live gate**. The spec is
  explicit that the pipeline must not be built first (§328-342) and names the
  precondition it waits on (§344): a taskset near a 0.6B model's frontier. That
  gate is implemented, it is unmet, and it fails loudly.

`guards.py` is shared by both and is pure stdlib, so every assertion in it is
checkable on a laptop with no GPU and no training stack installed.
"""
