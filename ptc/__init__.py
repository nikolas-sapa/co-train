"""The PTC arm as a loadable `verifiers` harness plugin.

`verifiers` resolves `--env.<role>.harness.id ptc` by importing the module `ptc`
and taking the single `Harness` subclass it exports through `__all__`
(`verifiers/v1/utils/loaders.py:145`, `_import_plugin`, `_plugin_class`). So this
file is the entire plugin contract: no fork of verifiers, no entry point, no
monkeypatch of a private name. The repo root just has to be importable.

`PTCHarness` is resolved lazily, through PEP 562's module `__getattr__`, for one
reason: `runtime.py` is pure stdlib and `test_ptc.py` must keep running on an
interpreter with no `verifiers` installed, which an eager
`from ptc.harness import ...` here would break -- importing `ptc.runtime` would
pull in httpx, pydantic and verifiers to reach a module that needs none of them.
`_plugin_class` uses `getattr(module, name)`, which triggers this, so the plugin
contract is unaffected. A test pins both halves.

Only `PTCHarness` is exported: `_plugin_class` rejects a module whose `__all__`
holds two `Harness` subclasses, so keeping the surface at one name makes that
impossible to do by accident.
"""

from ptc.runtime import Catalog, ProgramRejected, run, validate

__all__ = ["PTCHarness"]

_LAZY = {"PTCHarness", "PTCHarnessConfig"}


def __getattr__(name: str):
    if name in _LAZY:
        from ptc import harness

        return getattr(harness, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


_ = (Catalog, ProgramRejected, run, validate)  # re-exported for convenience
