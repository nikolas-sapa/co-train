# Licence requests — #1 FILED, #2 deliberately not

Two repositories this project wants to reuse ship with **no licence file**, which
makes them all-rights-reserved by default: public to read, not legal to vendor,
fork-and-modify, or redistribute. Verified 2026-09-25 (`08` §4a, §4b): GitHub API
`license: null`, and `LICENSE` / `LICENSE.txt` / `LICENCE` / `COPYING` / `NOTICE`
all return 404 on both.

**Status 2026-10-03.** #1 is **filed**:
[Qihoo360/harness-bench#14](https://github.com/Qihoo360/harness-bench/issues/14), as
`nikolas-sapa`, open, awaiting reply. Both repos were re-checked the same day and still
report `license: null`, eight days after this file was drafted.

**#2 is deliberately NOT filed.** It is wanted only for the recording proxy, and §4b of
`research/08-gap-closure.md` already found that pattern shipped in three other places with
real licences (`verifiers`' interception layer, Polar, ClawGym II, plus prime-agent's
`proxy.ts`). There is nothing to gain that is not already obtainable, so it does not justify
spending a public comment under a personal identity.

Filing puts a public, permanent, attributable comment under the repo owner's GitHub
identity. To file #2 if that ever changes: open the URL, paste the body, submit.

---

## 1. Qihoo360/harness-bench

**URL:** https://github.com/Qihoo360/harness-bench/issues/new
**Why it matters:** 106 manually reviewed, oracle-checkable agent tasks with 812
fixtures and 12 harness adapters. Reusing them would save this project weeks of
task authoring. Without a licence we can read the design but not build on it.

**Title:** `Licence for the code and task suite?`

**Body:**

> Thanks for releasing Harness-Bench — the model-harness configuration framing and
> the oracle/rubric split in the task manifests have both been directly useful to
> read.
>
> I could not find a licence for the repository: there is no `LICENSE` file and the
> GitHub API reports `license: null`. The paper is CC BY 4.0, but as I understand it
> that covers the text rather than the code and task data.
>
> Could you confirm the intended licence for the repository contents — in particular
> the `tasks/` suite and the harness adapters? Without one they default to
> all-rights-reserved, which means researchers can read them but cannot reuse or
> redistribute them, and I suspect that is not what you intended given the paper's
> framing.
>
> Apache-2.0 or MIT would both be unambiguous here. Happy to open a PR adding the
> file if you tell me which you prefer.

---

## 2. MSR-Orchard/OpenForge-RL

**URL:** https://github.com/MSR-Orchard/OpenForge-RL/issues/new
**Why it matters:** the recording proxy (`openforgerl/proxy/vllm_proxy.py`, 58 KB)
is a working implementation of the pattern this project needs. Note the repo's
default branch is `master`, not `main`.

**Title:** `Licence for the repository?`

**Body:**

> Thanks for open-sourcing OpenForge-RL. The proxy that serves the harness's model
> calls while recording the io-pairs is exactly the mechanism described in the paper,
> and it is useful to have a reference implementation.
>
> The paper's abstract describes this as "an open-source framework", but I could not
> find a licence in the repository — there is no root `LICENSE` and the GitHub API
> reports `license: null`. The only licence files present are vendored third-party
> ones (`molmoweb/LICENSE`, `LICENSE.Online-Mind2Web`).
>
> Could you confirm the intended licence? As it stands the contents default to
> all-rights-reserved, which would prevent the reuse the paper seems to invite. MIT
> would match the orchestrator repo referenced alongside it.
>
> Also, a small note in case it helps others: the paper's link resolves via
> `aka.ms/OpenForge-RL`, and the default branch is `master`, so tooling that assumes
> a `github.com/...` URL or a `main` branch misses the repo entirely. That is why at
> least one prior search for it came up empty.

---

## If the answer is no, or there is no answer

Neither is on the critical path. `08` §4a already recommends reading Harness-Bench
rather than vendoring it, and §4b notes the proxy pattern is independently shipped in
three other places (`verifiers`' interception layer, Polar, ClawGym II) plus
prime-agent's `proxy.ts` — all of which carry real licences. Treat a non-response as
the expected case and build against the licensed implementations.
