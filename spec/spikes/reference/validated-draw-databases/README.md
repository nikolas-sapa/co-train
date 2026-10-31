# Admitted database projection control

Run with the qualified interpreter, offline, without bytecode:

```sh
PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY=127.0.0.1,localhost \
  /absolute/qualified/python -I -B \
  /absolute/co-train/spec/spikes/reference/validated-draw-databases/control.py \
  --artifacts-dir /absolute/scratch/projection-control
```

Two fixed finite children run the actual synthetic retained-draw consumer test.
The negative delegates to the original consumer, then substitutes exactly one
returned DB digest. It must fail `PROJECTED_DB_DIGEST_NOT_ADMITTED` once. The
fresh restored child has zero substitutions and passes.

Both receipts require unchanged source and retained document bytes, two actual
corpus loads, and zero consumer SQLite, selector, gold-validation or EX calls.
Fixture preparation uses committed synthetic SQLite helpers before sentries.
No on-disk source mutation, persisted schema change or source repinning.
This qualifies projection fidelity, not SDK/native execution or SQL accuracy.
