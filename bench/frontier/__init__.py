"""`bench.frontier` -- the solve-rate probe and the TRAIN lane's gate manifest.

`manifest.json` is deliberately ABSENT from this directory. It holds measurements on the
policy being trained, and this lane cannot run them. Its absence keeps
`train/guards.py:frontier_taskset_status` shut, which is the correct state until someone
with policy access runs `bench.frontier.probe`.

See `probe.py`'s docstring for why a hand-written manifest would be a fabrication rather
than a shortcut.
"""

from bench.frontier.probe import (DEFAULT_DEAD_CEILING, DEFAULT_G, MANIFEST_PATH,
                                  ProbeResult, dead_group_fraction, probe, render,
                                  trainable_band, write_manifest)

__all__ = [
    "DEFAULT_DEAD_CEILING",
    "DEFAULT_G",
    "MANIFEST_PATH",
    "ProbeResult",
    "dead_group_fraction",
    "probe",
    "render",
    "trainable_band",
    "write_manifest",
]
