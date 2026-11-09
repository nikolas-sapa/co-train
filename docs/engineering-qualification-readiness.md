# Engineering qualification helpers

These helpers do not open the existing qualification or scientific admission gates.

- `train.engineering_budget` plans gross resource and ancillary estimates with exact arithmetic. The current engineering direction is $30 total, $25 planned expenditure and $5 headroom. This is not a provider-enforced spending cap. Credits count toward gross usage. A planned GPU attempt cannot exceed 1800 seconds.
- `train.qualification_remote_verification` invokes the original complete artifact verifier in a compatible remote environment. Its receipt binds declared request pins and checkpoint JSON digests. It does not revalidate source bytes, establish durable tensor-byte identity, grant cloud approval, or substitute for host verification.
- Source validation passed 23 budget tests and 21 remote-boundary tests. Six isolated guard-loss/restore pairs demonstrated the duration limit, original remote verifier, host validation, approval refusal, final verifier and non-None approval-label guard. Remote tests mock verifier/controller boundaries, not actual tensor or provider behavior.

- `train.qualification_file_rpc` is now integrated as a separate bounded stdlib wire/filesystem service. Its 73 tests passed; metadata and chunk bounds each have actual failing guard-loss and passing restored controls. Caller-owned quiescent trees and caller-supplied lower limits remain necessary. This does not grant command execution or cloud authority.
- The separate Core Qwen host candidate, with reviewed backend corrections, passed 90 offline tests. Genuine Modal 1.6.3 local Image/App constructors passed with zero client/network calls and five denial controls. A separate real server-reader constructor refused the ordinary loop and succeeded through the SDK synchronizer, also with zero client/network calls. Neither check exercises binary exec or provider lifecycle. The genuine GPT runner repair now passes four focused fixed-bootstrap cases, including unchanged phase argv and negative source-discovery controls. The remaining runner suite is unrun; cancellation-resistant cleanup remains blocked pending a new isolated owner boundary.
- `spec/spikes/reference/local-process-boundary` is a measured local-only reference, not production supervision. Three fresh trials and a restored guard case passed; worst observed worker kill/join was 0.003833 seconds. Removing the wrong-process-group guard failed as expected. The independent stand-in is not the actual Modal watchdog, and toy safety leases do not establish live lifecycle bounds.
- `spec/spikes/reference/local-capability` passed seven local protocol cases in 1.048738 seconds, with29 children reaped. Seven independent guard losses and four shared restored profiles behaved as required, with62 additional children reaped and no physical cleanup errors. This is a trusted local FD/one-use mechanism reference, not production authority.
- `spec/spikes/reference/local-stop-gate` now proves the direct-parent-owned same-PID exec topology locally: three baseline cases passed in0.260220167 seconds with9 children reaped; eight causal/fault profiles reaped33 additional children and produced their required witnesses. The repaired journal has one parent creator and append-only children. Faults include simulated reap-observation loss after actual OS reap, not an unreapable live child. Negative-control roots remain inert and retained. The isolated owner/worker contract still needs finalization, implementation and validation. No actual Modal cleanup or paid readiness follows from these probes.

- `spec/spikes/reference/local-sdk-ready` now passes three fresh genuine SDK-worker constructor trials. Worst READY was0.509975375s against2s; total1.51255975s, full process1.54s. All three actual child reaps and FD/root releases were observed. Constructor client/network deltas were zero, with live denial controls. This is local constructor/loop evidence, not an SDK provider lifecycle.
- `spec/spikes/reference/local-original-stop-parser` is a one-shot read-only reference, not a reusable execution authorization. The unchanged original stager/wrapper/adapter reached oversized-input refusal in one retained exec/reap chain: owned stdin observation1025→0, actual exit1, total0.515699125s, full process0.55s, root released. A separate two-child alarm/guard-loss test proved the kernel timer survives both exec transitions. All three narrowly authorized interpreter hash reads were used; permanent claim retained, no retry or further hash reads. Synthetic ID and invalid input prove neither App ownership nor real AppStop.
- Core bulk-FD source remains rejected and unrun. Genuine GPT delivered its replacement; the parent-corrected, reviewed version is accepted at `spec/spikes/reference/local-bulk-fd`. Seven baseline children and fourteen causal/fault children were actually reaped. Baseline total was0.728043958s, worst valid manifest0.182102208s; all ten causal oracles passed. The tested prototype maximum is6510001bytes/10000members, not the superseded5840001/5870001 estimates. Close-failure injection retained two actual manifest owner FDs before harness exit; its inert root remains, without a claim of live FD custody after process exit. This proves neither member-content verification nor the broader production schema.
- The separate shutdown-reserve arithmetic model passed seven named fixtures in8.724292ms (full process0.03s), including guard losses/restores; it does not prove actual binding or async cancellation integration. Its reference is `spec/spikes/reference/local-shutdown-schedule`. Shared isolated-owner interfaces are now frozen after269purechecks and two guard-loss RED oracles in0.19s fullwall. Production-shape bound is5026024bytes; largest permitted closed control frame is497bytes. Gate birth follows actual App retention/original command staging and precedes CREATE. Actual production integration/cancellation/cleanup acceptance remains outstanding.

- The genuine GPT isolated-run candidate's amended C suite passed all104 cases in10.47s full process, with32 stable source pins and all9module origins verified. A safe FIFO-substitution regression first failed on exactly the missing snapshot O_NONBLOCK flag, with103 other cases passing (6.66s full process); restoring only that flag made all104 pass. Earlier51-case acceptance and V230/V232 failures remain historical. These tests use explicit lifecycle/SDK/native/lease mocks and newly owned filesystem fixtures, not actual child reaps or provider execution. The public preadmission integration refusal remains; real A/C integration is outstanding.
- Genuine GPT A V251, with three reviewed parent repairs, previously passed124 fixture cases in7.96s full process (7.873939750s internal), with38 stable source pins and16 verified module origins. The same frozen tests first produced exactly eight planned failures against original V251 production, with116 passing and zero errors/skips, in8.30s. Repairs explicitly wrap inherited Unix sockets, retain owner/latch/anchors after opaque identity-append failures, and reject positive reaps first observed past fixed join cutoffs. The original helper still hid secondary close failures at that historical checkpoint; conservative poisoning alone did not fix that gap.
- After explicit scope authorization, the original reservation helper now owns actual generation/anchor custody receipts across traversal, policy, claim, append and final close. Existing public signatures and healthy one-FD claim remain unchanged. Receipts preserve original primary and secondary errors, distinguish confirmed failed opens from interrupted/unknown acquisitions, and never retry or inspect retired FD numbers. A immediately retains successful/failed-claim receipts and requires observed receipt-wide closure before latch release; known-clean errors permit failure-only cleanup, while unknown custody keeps required anchors/latch. Backend authored the helper source; parent integrated A and tests. Both Python/security reviews cleared the exact source before execution.
- Actual updated acceptance:111legacy/custody cases passed in0.90s full process (0.818071708s internal), and129A cases passed separately in7.87s (7.791702333s internal), zero failures/errors/skips. Both invocations verified42stablepins and17/16module origins respectively, with unchanged H19130/29-second and80pins/200cases/4paths caps and no forbidden process/signal/connection operations. Frozen21focused cases first failed against pre-repair helper in0.91s; their source stayed identical in the positive run. Two legacy tests were explicitly corrected before execution: required parent retention after an ambiguous child close, and exact frozen V226 read-only binding surface. The other88legacy bodies remained unchanged. Local helper-receipt gate is closed only for this stdlib/owned-fixture boundary. Tests include actual A private lease/C reader logic, three repeated cancellations with substituted process observations, primary/secondary faults, registration-before-validation, at most2traversal FDs, interrupted opens, and recycled-number controls. Valid-output lifecycle C validation, processes, signals, SDK/native outcomes and exec remain substituted; malformed-output refusal uses the actual full C validator. Real A/C valid-output integration, genuine SDK/three-child lifecycle, worst-case export FD capacity, 8GiB throughput and paid readiness remain blocked. Public C refusal remains; no implementation code is promoted here.
- V280 closes the previously missing fixture-backed valid-output A/C validation gap:6new genuine GPT cases passed, zero failures/errors/skips,1.43s full process (1.264972917s internal),43stablepins/17verifiedorigins, unchanged H191. Actual A lease feeds unchanged C validation/original receipt/full hashes, two exact10entry inventories and eight-reader post-close identity sweep, then actual sealing, C final wrapper, one-use publication and release. Five negatives exercise same-size byte corruption, OUTCOME digest corruption, late identity drift, inner receipt mismatch with valid outer hashes, and unchanged public refusal. Prior129successful cases were not rerun. Processes/channels/stager/SDK remain synthetic, and four bulk fixture JSONs total8bytes; no native/tensor verification or throughput proof follows. Actual OS/SDK lifecycle, worst-case capacity/hash timing and renewed interpreter/stager authority still gate GPU readiness. No A/C production source changed or implementation promoted. Exact acceptance: `parent-v281-ac-valid-output-acceptance.json` in the parent workspace.
- V298 measures maximum bulk volume through the actual A lease and unchanged full C validator: one new case passed with four dense2GiB files (8,589,934,592 bulk bytes), validator27.847598167s, internal harness28.580670667s/full process28.70s, peak RSS56,852,480bytes. All eight readers closed, final identities swept, original receipt checked, one-use publication and actual custody release completed;46pins/17origins verified. Preparation separately completed in40.62s against internal50/external60. Two preparer/test custody defects were repaired and ten new tiny regressions first failed against originals, then passed in0.70s; old129/six-case suites were not rerun. Only0.419329333s remained under H191's29s internal cap, so this is an observed fixture PASS, not ample-headroom/capacity or GPU clearance. Fresh-generated files were not cache-evicted; process/stager/SDK observations remain synthetic. OS-wide FD peak, combined high-fanout/deep/input-root capacity, genuine OS/SDK lifecycle and native/science remain unproved. No production source changed. Exact evidence: `parent-v299-volume-observation.json`;8GiB owned fixture data retained. The approved OS probe remains blocked on independent birth-time containment and has not run.
- Proposed validation scheduling passed295 pure checks and one guard-loss RED oracle in0.05s full process. It books full parent hashing after clean worker reap and before normal shutdown, without extending the existing attempt or shutdown limits. The separate V237 owner-held validation amendment is now frozen and its pure helper is byte-identical A/C/I; the original DTO module is unchanged. Arithmetic proves neither runtime lease custody nor throughput.
- Core V226 and V240 deliveries remain source-blocked and unrun. V240 fixes some earlier defects but imports lease types absent from the immutable DTO module and omits the required owner validation methods. Its152 unique test definitions are not executed evidence. Both source deliveries and the original GPT V251 delivery are preserved. GPT completion and parent repairs were validated separately as described above; immutable DTO/helper, accepted RPC and staged C sources stayed unchanged. V256's113pass/2fail baseline and V260's116pass/8fail negative remain failures, never relabeled as unit passes. No known-uncollectible Core diagnostic run was attempted.

The Modal host/runner candidates are not promoted here. Exact approved inputs, resource/rate/preparation accounting, one-attempt ownership, deadlines, full streamed export and cleanup still gate any paid attempt. Local Torch is unavailable; the original strict host verification path remains unchanged. No successful GPU qualification, model improvement or scientific benchmark result is established by these checks. No provider/GPU launch follows from local acceptance.

## Latest maximum-volume checkpoint, V323

V310 and V323 both timed out at the unchanged30-second external limit. Both
remain NONPASS. V323's bounded journal proves actual C entry, original receipt
return and at least7.75GiB read, last recorded after28.549480084s wall and
20.298816s CPU. That read record precedes C's hash update. Full hash completion,
validation close, publication, joins and release remain unknown. All8GiB is
retained; neither failure authorizes a retry. The earlier V298 PASS is historical,
not current headroom. GPU/native/science remains0/7; conditionalNov9 unscheduled.

Separately, journal33, recovery-provenance20 and private-metadata-routing5 new
cases passed after their intended RED controls. One separately authorized
recovery renamed8GiB with0new bulk bytes in0.12s wall, then V323 consumed the
single full-run authority. No existing workspace permissions or production C
checks were relaxed. Exact evidence: parent-v315-journal-unit-acceptance.json,
parent-v317-provenance-unit-acceptance.json,
parent-v321-private-metadata-unit-acceptance.json,
parent-v322-recovery-acceptance.json and parent-v323-full-volume-nonpass.json.
The V327 directory-projection spike was rejected after measurement. Its RED run
produced exactly one missing-gid failure and five passes; unchanged GREEN passed
all six cases. Across six alternating pairs (all12 samples retained), candidate
CPU ratio was1.027284 median and1.068010 worst, missing the preset0.90/1.05 gates.
Production owner remains unchanged. Exact evidence:
parent-v329-directory-projection-decision.json and
parent-v329-directory-projection-measurement.json. No throughput or ETA claim.

Independent security review cleared the timer arithmetic only under its stated
premises. Public source supplements now expose CPython's signed-tick cast, which
requires explicit INT64_MAX headroom admission. Running Darwin27 applicability,
installed runtime equivalence, guard/exec behavior and OS execution remain
blocked. The finite models are neither exhaustive nor native proof.

## Latest bounded experiments, V335/V337

Two genuine Devin SWE-2 High workers completed source-only work; exports verify
model `swe-2-high` and zero tool calls. Parent rejected unsafe broad CPU changes
and repaired defective draft tests before independent Python review. Production
owner, C, deadline and public admission remain unchanged.

V334/335 corrected pure timer arithmetic passed22 new cases in0.57s wall after
the retained-H negative control produced exactly1failure/21passes. Checks cover
exact observed-tick inversion, bounded future-window headroom, unreduced CPython
conversion operands, BOTH retained H and actual requested deadline, and exact
absolute-expiry domination. The three source/import pins were verified. Evidence:
parent-v335-timer-pure-acceptance.json. This is a pure model, not proof of runtime
window coverage, running-kernel applicability, signal delivery or containment.
The short-lived unrearmed birth-probe guard is not full GPU-attempt lifetime
qualification.

V333/336/337 narrow stat-mode candidate passed8 new cases in1.94s wall after
exactly2intended RED failures/6passes. Exhaustive policy checks covered all65,536
modes with both private flags for each function. Actual tiny A/C validation,
publication, second-publication refusal and release passed with identical fresh
stat/policy/monitor traces. Nonetheless median paired CPU ratio0.996722766 and
worst1.078799250 missed the unchanged0.90/1.05 screening gates: REJECTED.
All12 samples remain; no retry, tuning or production promotion. Repeated-EOF
reads are not positive64KiB or full8GiB throughput evidence. Exact evidence:
parent-v337-mode-bit-decision.json and parent-v337-mode-bit-measurement.json.

No new full-volume/recovery/OS/GPU authority follows from these results.
GPU/native/science remains0/7, no defensible same-day ETA.
