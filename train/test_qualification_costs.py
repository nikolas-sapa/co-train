import ast
import builtins
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import importlib
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import types

import pytest


def api():
    assert importlib.util.find_spec("train.qualification_costs") is not None, (
        "missing all-charge arithmetic helper"
    )
    module = importlib.import_module("train.qualification_costs")
    for name in ("Charge", "CostLedger", "evaluate_costs", "compare_h200"):
        assert callable(getattr(module, name, None)), f"missing cost API: {name}"
    return module


def fixture():
    module = api()
    from train.native_qualification import AttemptBounds

    bounds = AttemptBounds(
        Decimal("25"), Decimal("5"), Decimal("20"), 10, 1048576, 1073741824, 20
    )
    charge = module.Charge
    charges = {
        name: charge(Decimal("0"), "item", Decimal("0"), "USD/item", None)
        for name in (
            "preparation", "build", "provisioning", "teardown", "replay", "ancillary"
        )
    }
    charges.update({
        "gpu": charge(Decimal("1"), "gpu", Decimal("0.1"), "USD/gpu-second", Decimal("15")),
        "cpu": charge(Decimal("2"), "physical-core", Decimal("0.01"),
                      "USD/physical-core-second", Decimal("15")),
        "ram": charge(Decimal("1024"), "MiB", Decimal("0.01"),
                      "USD/GiB-second", Decimal("15")),
        "storage": charge(Decimal("1"), "GiB", Decimal("0.001"),
                          "USD/GiB-second", Decimal("15")),
        "retention": charge(Decimal("1"), "GiB", Decimal("0.001"),
                            "USD/GiB-second", Decimal("20")),
        "egress": charge(Decimal("1026"), "MiB", Decimal("0.01"), "USD/GiB", None),
    })
    ledger = module.CostLedger(Decimal("2"), Decimal("3"), 2, 3, charges)
    return module, bounds, ledger


def test_missing_each_charge_blocks():
    module, bounds, ledger = fixture()
    for name in ledger.charges:
        for missing in (True, False):
            charges = dict(ledger.charges)
            if missing:
                del charges[name]
            else:
                charges[name] = None
            with pytest.raises(ValueError):
                module.evaluate_costs(bounds, replace(ledger, charges=charges))
    with pytest.raises(ValueError):
        module.evaluate_costs(bounds, replace(ledger, charges={**ledger.charges, "extra": None}))


def test_prior_cash_and_credits_are_gross():
    module, bounds, ledger = fixture()
    result = module.evaluate_costs(bounds, ledger)
    assert result.prior_gross_usd == Decimal("5")
    assert result.total_gross_usd == Decimal("6.99501953125")
    with pytest.raises(ValueError):
        module.evaluate_costs(replace(bounds, prior_usage_usd=Decimal("2")), ledger)


def test_units_are_explicit():
    module, bounds, ledger = fixture()
    result = module.evaluate_costs(bounds, ledger)
    charges = dict(ledger.charges)
    charges["ram"] = replace(charges["ram"], quantity=Decimal("1"), unit="GiB")
    assert module.evaluate_costs(bounds, replace(ledger, charges=charges)) == result
    for name, unit in (("cpu", "vCPU"), ("ram", "GB"), ("gpu", "item")):
        charges = dict(ledger.charges)
        charges[name] = replace(charges[name], unit=unit)
        with pytest.raises(ValueError):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))
    charges = dict(ledger.charges)
    charges["gpu"] = replace(charges["gpu"], quantity=Decimal("2"))
    with pytest.raises(ValueError):
        module.evaluate_costs(bounds, replace(ledger, charges=charges))
    for name, field, value in (
        ("cpu", "rate_unit", "USD/vCPU-second"),
        ("ram", "rate_unit", "USD/GB-second"),
        ("build", "seconds", Decimal("1")),
        ("cpu", "seconds", None),
    ):
        charges = dict(ledger.charges)
        charges[name] = replace(charges[name], **{field: value})
        with pytest.raises(ValueError):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))


def test_exact_25_under_hostile_context():
    module, bounds, ledger = fixture()
    charges = {
        name: replace(charge, rate_usd=Decimal("0"))
        for name, charge in ledger.charges.items()
    }
    charges["build"] = replace(charges["build"], quantity=Decimal("1"), rate_usd=Decimal("20"))
    with localcontext() as context:
        context.prec = 1
        context.Emax = 1
        context.Emin = -1
        for signal in context.traps:
            context.traps[signal] = True
        result = module.evaluate_costs(bounds, replace(ledger, charges=charges))
        assert result.total_gross_usd == Decimal("25")
        assert result.remaining_usd == Decimal("20")
        assert context.prec == 1 and not any(context.flags.values())


def test_one_tiny_increment_over_25_blocks():
    module, bounds, ledger = fixture()
    charges = {
        name: replace(charge, rate_usd=Decimal("0"))
        for name, charge in ledger.charges.items()
    }
    charges["build"] = replace(charges["build"], quantity=Decimal("1"), rate_usd=Decimal("20"))
    charges["ancillary"] = replace(
        charges["ancillary"], quantity=Decimal("1"), rate_usd=Decimal("1e-30")
    )
    with localcontext() as context:
        context.prec = 1
        for signal in context.traps:
            context.traps[signal] = True
        with pytest.raises(ValueError):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))


def test_huge_exponents_are_refused():
    module, bounds, ledger = fixture()
    for value in (
        Decimal("1e1000000"), Decimal("1e-1000000"), Decimal("0e1000000"),
        Decimal("1" * 97),
    ):
        charges = dict(ledger.charges)
        charges["build"] = replace(charges["build"], rate_usd=value)
        with pytest.raises(ValueError, match="representation"):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))
        with pytest.raises(ValueError, match="representation"):
            module.evaluate_costs(replace(bounds, remaining_worst_case_usd=value), ledger)


def test_oversized_coefficient_is_refused_before_tuple(monkeypatch):
    module = api()
    oversized = Decimal("1" * 4096)
    boundary = Decimal("1" * 96)
    calls = []

    def record_tuple(frame, event, function):
        if event == "c_call" and getattr(function, "__name__", None) == "as_tuple":
            owner = getattr(function, "__self__", None)
            if owner is oversized or owner is boundary:
                calls.append(owner)

    previous = sys.getprofile()
    try:
        sys.setprofile(record_tuple)
        with pytest.raises(ValueError, match="representation"):
            module._number(oversized, "oversized")
        assert calls == []
        assert module._number(boundary, "boundary") == Fraction(int("1" * 96))
        assert len(calls) == 1 and calls[0] is boundary
    finally:
        sys.setprofile(previous)
    with pytest.raises(ValueError, match="representation"):
        module._number(Decimal("1" * 97), "over_boundary")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "implementation", types.SimpleNamespace(name="unsupported"))
        with pytest.raises(ValueError, match="representation"):
            module._number(Decimal("1"), "unsupported")


def test_invalid_numeric_bounds_block():
    module, bounds, ledger = fixture()
    for value in (Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-1"), 0.1, True):
        for field in ("quantity", "rate_usd", "seconds"):
            charges = dict(ledger.charges)
            charges["cpu"] = replace(charges["cpu"], **{field: value})
            with pytest.raises(ValueError):
                module.evaluate_costs(bounds, replace(ledger, charges=charges))
        with pytest.raises(ValueError):
            module.evaluate_costs(bounds, replace(ledger, prior_credits_usd=value))
    for field in ("lifetime_seconds", "retention_seconds", "artifact_bytes", "output_bytes_per_phase"):
        with pytest.raises(ValueError):
            module.evaluate_costs(replace(bounds, **{field: True}), ledger)
    with pytest.raises(ValueError):
        module.evaluate_costs(bounds, replace(ledger, teardown_seconds=None))


def test_compute_covers_both_tails():
    module, bounds, ledger = fixture()
    for name in ("cpu", "gpu", "ram"):
        charges = dict(ledger.charges)
        charges[name] = replace(charges[name], seconds=Decimal("14"))
        with pytest.raises(ValueError, match="duration"):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))
    assert module.evaluate_costs(bounds, ledger).charge_usd("gpu") == Decimal("1.5")


def test_storage_retention_and_export_floors():
    module, bounds, ledger = fixture()
    for name, field, value in (
        ("storage", "seconds", Decimal("14")),
        ("retention", "seconds", Decimal("19")),
        ("storage", "quantity", Decimal("0.99")),
        ("retention", "quantity", Decimal("0.99")),
        ("egress", "quantity", Decimal("1025")),
    ):
        charges = dict(ledger.charges)
        charges[name] = replace(charges[name], **{field: value})
        with pytest.raises(ValueError):
            module.evaluate_costs(bounds, replace(ledger, charges=charges))
    result = module.evaluate_costs(bounds, ledger)
    assert result.charge_usd("storage") == Decimal("0.015")
    assert result.charge_usd("retention") == Decimal("0.02")


def test_replay_and_ancillary_are_charged():
    module, bounds, ledger = fixture()
    charges = dict(ledger.charges)
    for name, cost in (("replay", "2"), ("ancillary", "3")):
        charges[name] = replace(charges[name], quantity=Decimal("1"), rate_usd=Decimal(cost))
    result = module.evaluate_costs(bounds, replace(ledger, charges=charges))
    assert result.remaining_usd == Decimal("6.99501953125")
    assert result.charge_usd("replay") == Decimal("2")
    assert result.charge_usd("ancillary") == Decimal("3")


def test_remaining_reservation_and_ceiling_are_independent():
    module, bounds, ledger = fixture()
    for invalid in (
        replace(bounds, remaining_worst_case_usd=Decimal("1")),
        replace(bounds, total_ceiling_usd=Decimal("24")),
        replace(bounds, prior_usage_usd=Decimal("4")),
        replace(bounds, total_ceiling_usd=Decimal("26")),
        replace(bounds, lifetime_seconds=1801),
    ):
        with pytest.raises(ValueError):
            module.evaluate_costs(invalid, ledger)


def test_conditional_h200_threshold():
    module = api()
    tie = module.compare_h200(Decimal("1"), Decimal("2"), Decimal("2"))
    assert tie.required_speedup == Fraction(2)
    assert tie.h200_compute_cheaper is False
    assert tie.scope == "conditional_compute_arithmetic_only"
    assert module.compare_h200(Decimal("1"), Decimal("2"), Decimal("2.01")).h200_compute_cheaper
    assert module.compare_h200(Decimal("3"), Decimal("2"), Decimal("1")).required_speedup == Fraction(2, 3)
    for value in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("1e1000000")):
        with pytest.raises(ValueError):
            module.compare_h200(value, Decimal("2"), Decimal("2"))


def test_result_grants_no_authority():
    module, bounds, ledger = fixture()
    result = module.evaluate_costs(bounds, ledger)
    assert result.scope == "conditional_all_charge_arithmetic_only"
    for name in ("approved", "candidate_approved", "launch_authorized", "controller", "run_once"):
        assert not hasattr(result, name)
    assert type(result.breakdown) is tuple and len(result.breakdown) == 12


def test_guarded_target_source_execution_has_no_effects(monkeypatch):
    # Dependencies are preloaded; this checks target source, not dependency-first imports.
    dependencies = {"dataclasses", "decimal", "fractions", "typing", "sys", "__future__"}
    for name in dependencies:
        importlib.import_module(name)
    name = "train.qualification_costs"
    path = Path(__file__).with_name("qualification_costs.py")
    source = path.read_text()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(alias.name in dependencies for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in dependencies
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            assert not any(isinstance(child, ast.Call) for child in ast.walk(node))
    calls = []
    original_import = builtins.__import__

    def denied(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("target source attempted application effect")

    def cached_import(module_name, globals=None, locals=None, fromlist=(), level=0):
        assert level == 0 and module_name in dependencies
        assert module_name in sys.modules
        return original_import(module_name, globals, locals, fromlist, level)

    # Harness source reads/compilation precede guards. No loader I/O is exercised.
    effects = (
        "open('forbidden', 'w')",
        "os.open('forbidden', 0)",
        "Path('forbidden').open()",
        "socket.socket()",
        "subprocess.Popen(['forbidden'])",
    )
    for effect in (None, *effects):
        code = compile(source + ("\n" + effect if effect else ""), str(path), "exec")
        fresh = types.ModuleType(name)
        fresh.__file__ = str(path)
        calls.clear()
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, name, fresh)
            for target, attribute in (
                (builtins, "open"), (os, "open"), (Path, "open"),
                (socket, "socket"), (subprocess, "Popen"),
            ):
                patch.setattr(target, attribute, denied)
            patch.setattr(builtins, "__import__", cached_import)
            if effect is None:
                exec(code, fresh.__dict__)
                assert sys.modules[name] is fresh
                assert fresh.Charge.__module__ == name
                assert calls == []
            else:
                # Injected calls use harness bindings, never broaden target imports.
                fresh.__dict__.update(
                    os=os, Path=Path, socket=socket, subprocess=subprocess
                )
                with pytest.raises(AssertionError, match="application effect"):
                    exec(code, fresh.__dict__)
                assert len(calls) == 1
