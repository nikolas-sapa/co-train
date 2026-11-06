"""Offline regression for `sampling_reward` over single-pass completions.

The wrapped reward must accept lazy completions (generators, single-pass
Iterables) exactly as it accepts finite ones: score them once, record the same
completions aligned with the scores, and leave nothing to a second iteration
that cannot happen. Pure callables only -- no trainer, no framework, no model.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # noqa: E402

from train import dead_group_probe as probe  # noqa: E402


def _call(wrapped, completions, style):
    if style == "keyword":
        return wrapped(completions=completions, answer=["ada", "ada"])
    return wrapped(completions, ["ada", "ada"])


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_reward_preserves_single_pass_completions(style):
    completions = (c for c in ["<answer>ada</answer>", "<answer>ada</answer>"])
    calls, returned = [], []

    def reward(completions, answer, **_):
        calls.append(completions)
        returned.append(probe.exact_match_reward(completions, answer))
        return returned[-1]

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    out = _call(wrapped, completions, style)

    assert len(calls) == 1
    assert out is returned[0]  # the reward's own result object, untouched
    assert len(returned[0]) == 2
    assert wrapped.__name__ == reward.__name__
    samples = sampler.drain()
    assert len(samples) == 2
    assert [s["reward"] for s in samples] == returned[0]
    assert [s["extracted"] for s in samples] == ["ada", "ada"]


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_iterable_accumulates_to_existing_cap(style):
    assert probe.CompletionSampler().per_step == probe.SAMPLES_PER_STEP == 4
    calls, returned = [], []

    def reward(completions, answer, **_):
        calls.append(completions)
        returned.append(probe.exact_match_reward(completions, answer))
        return returned[-1]

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    for call in range(3):
        completions = (f"<answer>c{call}-{i}</answer>" for i in range(2))
        answers = [f"c{call}-{i}" for i in range(2)]
        if style == "keyword":
            out = wrapped(completions=completions, answer=answers)
        else:
            out = wrapped(completions, answers)
        assert out is returned[-1]

    assert len(calls) == 3  # every completion scored, none dropped from reward
    assert sum(len(r) for r in returned) == 6
    samples = sampler.drain()
    assert len(samples) == probe.SAMPLES_PER_STEP  # cap retains the first 4
    assert [s["extracted"] for s in samples] == [
        f"c0-{i}" for i in range(2)] + [f"c1-{i}" for i in range(2)]
    assert sampler.drain() == []


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_finite_sequence_contract(style):
    completions = ["<answer>ada</answer>", "no tags", "<answer></answer>"]
    seen = []

    def reward(completions, answer, **_):
        seen.append(completions)
        return probe.exact_match_reward(completions, answer)

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    if style == "keyword":
        out = wrapped(completions=completions, answer=["ada", "ada", "ada"])
    else:
        out = wrapped(completions, ["ada", "ada", "ada"])

    assert seen[0] is completions  # the original object reaches reward
    assert out == [1.0, 0.0, 0.0]
    samples = sampler.drain()
    assert len(samples) == 3
    assert [s["extracted"] for s in samples] == ["ada", None, ""]
    assert [s["chars"] for s in samples] == [len(c) for c in completions]

    # chat-style completion extraction, on the same finite path
    chat = [[{"role": "assistant", "content": "<answer>ada</answer>"}]]
    sampler.record(chat, probe.exact_match_reward(chat, ["ada"]))
    sample, = sampler.drain()
    assert sample["extracted"] == "ada"
    assert sample["chars"] == len("<answer>ada</answer>")

    # configured truncation keeps the original length beside the cut text
    long = "<answer>" + "x" * (probe.SAMPLE_CHARS * 2) + "</answer>"
    sampler.record([long], [0.0])
    sample, = sampler.drain()
    assert len(sample["completion"]) < len(long)
    assert sample["chars"] == len(long)


class _SharedIteratorIterable:
    """An Iterable that is not an Iterator: every __iter__ hands back the same
    single-pass iterator, so it can be consumed exactly once total."""

    def __init__(self, items):
        self._it = iter(items)

    def __iter__(self):
        return self._it


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_preserves_reward_exception_identity(style):
    pulled = []

    def watched():
        for c in ["<answer>ada</answer>", "<answer>ada</answer>"]:
            pulled.append(c)
            yield c

    sentinel = RuntimeError("original reward failure")

    def reward(completions, answer, **_):
        assert pulled == []  # no preconsumption before reward runs
        raise sentinel

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    with pytest.raises(RuntimeError) as caught:
        _call(wrapped, watched(), style)
    assert caught.value is sentinel
    assert sampler.drain() == []


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_preserves_single_pass_iterable(style):
    completions = _SharedIteratorIterable(
        ["<answer>ada</answer>", "<answer>ada</answer>"])
    calls = []

    def reward(completions, answer, **_):
        calls.append(completions)
        return probe.exact_match_reward(completions, answer)

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    out = _call(wrapped, completions, style)

    assert len(calls) == 1
    assert out == [1.0, 1.0]
    samples = sampler.drain()
    assert len(samples) == 2
    assert [s["reward"] for s in samples] == out
    assert [s["extracted"] for s in samples] == ["ada", "ada"]


@pytest.mark.parametrize("style", ["positional", "keyword"])
@pytest.mark.parametrize("kind", ["generator", "shared_iterator", "list"])
def test_sampling_distinct_completions_keep_order_and_reward_identity(style, kind):
    originals = [
        "<answer>ada</answer>",
        "<answer>grace</answer>",
        "<answer>linus</answer>",
    ]
    answers = ["ada", "wrong", "linus"]
    if kind == "generator":
        completions = (c for c in originals)
    elif kind == "shared_iterator":
        completions = _SharedIteratorIterable(originals)
    else:
        completions = originals
    calls, seen, returned = [], [], []

    def reward(completions, answer, **_):
        calls.append(completions)
        batch = list(completions)
        seen.extend(batch)
        returned.append(probe.exact_match_reward(batch, answer))
        return returned[-1]

    sampler = probe.CompletionSampler()
    wrapped = probe.sampling_reward(reward, sampler)
    if style == "keyword":
        out = wrapped(completions=completions, answer=answers)
    else:
        out = wrapped(completions, answers)

    assert len(calls) == len(returned) == 1
    assert len(seen) == 3
    assert all(actual is original for actual, original in zip(
        seen, originals, strict=True))
    if kind == "list":
        assert calls[0] is originals
    assert out is returned[0]
    assert out == [1.0, 0.0, 1.0]
    assert wrapped.__name__ == reward.__name__
    assert sampler.drain() == [
        {"chars": len(originals[0]), "completion": originals[0],
         "extracted": "ada", "reward": 1.0},
        {"chars": len(originals[1]), "completion": originals[1],
         "extracted": "grace", "reward": 0.0},
        {"chars": len(originals[2]), "completion": originals[2],
         "extracted": "linus", "reward": 1.0},
    ]
    assert sampler.drain() == []


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_sampling_configured_extractor_cap_and_truncation(style):
    originals = ["abcdefgh", "ijklmnop", "qrstuvwx", "yzabcdef"]
    seen, returned, extracted = [], [], []

    def reward(completions, answer, **_):
        batch = list(completions)
        seen.append(batch)
        returned.append(probe.exact_match_reward(batch, answer))
        return returned[-1]

    def extract(text):
        extracted.append(text)
        return "parsed:" + text

    sampler = probe.CompletionSampler(extract=extract, per_step=2, chars=5)
    wrapped = probe.sampling_reward(reward, sampler)
    for start in (0, 2):
        completions = (c for c in originals[start:start + 2])
        out = _call(wrapped, completions, style)
        assert out is returned[-1]

    assert len(seen) == len(returned) == 2
    assert seen == [originals[:2], originals[2:]]
    assert sum(len(values) for values in returned) == 4
    assert returned == [[0.0, 0.0], [0.0, 0.0]]
    assert wrapped.__name__ == reward.__name__
    assert sampler.extract is extract
    assert sampler.per_step == 2
    assert sampler.chars == 5
    assert extracted == originals[:2]
    assert sampler.drain() == [
        {"chars": 8, "completion": "abcde...[+3 chars]",
         "extracted": "parse...[+10 chars]", "reward": 0.0},
        {"chars": 8, "completion": "ijklm...[+3 chars]",
         "extracted": "parse...[+10 chars]", "reward": 0.0},
    ]
    assert sampler.drain() == []
