# Bounded generation-stage diagnostic, not qualification

Two prior full-volume Linux experiments ended at30s/exit137. The second had durably closed two files/4GiB at26.057947410s and had not reached reader validation. It did not isolate hashing, writes, fsync or metadata costs. No storage or hashing cause is established.

This separate one-shot diagnostic uses at most64MiB of new synthetic files, not another8GiB case. An8KiB reservation covers the three tiny reporter fixtures (13 cumulative bytes written). Each eligible candidate gets one33550336B dense file (32MiB minus4KiB), so both files plus that reservation fit64MiB. Four counter blocks comprise three full8MiB writes and one8MiB-minus4KiB write. Only `/var/tmp` and `/mnt` candidate metadata and ancestry may be inspected. Ineligible, unsafe, unwritable, memory-backed or insufficient-capacity candidates are not measured. Eligible candidates get a private root, actual full writes/hash/fsync and streamed checksum readback. Existing preparer custody, ancestry, counter-block and write helpers are reused without changing them.

Raw per-stage wall/CPU measurements expose first and subsequent seed, build, write, hash, checkpoint, fsync, readback and close costs. Bounded phase records expose fixed names and numeric clocks/counters only. No data, seeds, hostname, IDs, private paths, environment or tracebacks enter the selected output. Small-file timings do not predict8GiB throughput or explain another VM by themselves.

Pinned private Python3.12.13 runtime setup is separate from the64MiB synthetic cap, as explicitly authorized. The immutable archive size/SHA and bounded data-filter extraction are retained. No vendor installer, pip, pytest, package installation, sudo, global trust/cache changes or existing asset access. Diagnostic time is one absolute29s with independent GNU KILL30 and complete-process wall<30s; setup and diagnostic together have a ten-minute job ceiling.

Publication/dispatch require independent source/security review, exact reviewed public main SHA, first workflow run/attempt and standard free hosted Ubuntu24.04 x64. One durable dispatch claim, no retry, paid/larger runner, caches, data artifacts, privilege/mount changes, tmpfs, native/compiler/SDK/provider/GPU or local rehearsal.

DIAGNOSTIC_COMPLETE only means the bounded measurement and custody gates completed. It is not a full-volume PASS, real SDK reaping proof, native ownership acceptance, target ABI admission or permission to run a GPU. Missing, malformed, failed or timed-out evidence is NONPASS with cleanup unproven.
