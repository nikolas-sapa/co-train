# Sanitized public reference, UNRUN derivative. No execution authority.
"""SOURCE ONLY: twenty new pure provenance cases, no filesystem fixture reads.

Parent stages the actual RED/GREEN module at
train/_qualification_timeout_recovery_fixture.py before each frozen test run.
Literal fixtures transcribe only approved first-party metadata. Python JSON
parsing preserves the exact nanosecond integers; no JS numeric conversion.
"""
from copy import deepcopy
import json

import pytest

from train import _qualification_timeout_recovery_fixture as recovery


MANIFEST = r'''{"bulk_identity":[101,1001,16832,503,20],"files":[{"identity":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700062943913929955,4210688],"key":"checkpoint-1/native-observation.json","name":"blob-1.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000001","size":2147483648},{"identity":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700062943914710999,4194304],"key":"checkpoint-1/trainer_state.json","name":"blob-2.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000002","size":2147483648},{"identity":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700062943915516376,4194304],"key":"checkpoint-2/native-observation.json","name":"blob-3.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000003","size":2147483648},{"identity":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700062943916397545,4194304],"key":"checkpoint-2/trainer_state.json","name":"blob-4.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000004","size":2147483648}],"op":"v290-owned-volume","preparation":{"buffer_bytes":8388608,"cache":"reused-generated-after-previous-full-read-not-evicted","elapsed_ns":40528727250,"final_free_bytes":15917719552,"initial_free_bytes":24537923584,"written_bytes":8589934592},"root_identity":[101,1006,16832,503,20],"v":1}'''
RECEIPT = r'''{"cache":"reused-generated-after-previous-full-read-not-evicted","consumed_failure":{"elapsed_ns":6514416,"error":"exact prior validated source generation","error_type":"ValueError","moved":[{"after":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700061926992514711,4210688],"before":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700060354453968409,4210688],"key":"checkpoint-1/native-observation.json"},{"after":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700061926993769673,4194304],"before":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700060354454211451,4194304],"key":"checkpoint-1/trainer_state.json"}],"status":"FAIL","v":1},"destination":"/qualification-reference/scratch/pc309-80pg7a82","destination_root_identity":[101,1006,16832,503,20],"elapsed_ns":9159917,"hashes_are_expectations_only":true,"moved":[{"after":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700062943913929955,4210688],"before":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700061926992514711,4210688],"closed":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700062943913929955,4210688],"expected":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700061926992514711,4210688],"key":"checkpoint-1/native-observation.json","preflight":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700061926992514711,4210688],"source_name":"blob-1.bin","source_root":"/qualification-reference/scratch/pc305-nklrdyr7","state":"COMPLETE"},{"after":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700062943914710999,4194304],"before":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700061926993769673,4194304],"closed":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700062943914710999,4194304],"expected":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700061926993769673,4194304],"key":"checkpoint-1/trainer_state.json","preflight":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700061926993769673,4194304],"source_name":"blob-2.bin","source_root":"/qualification-reference/scratch/pc305-nklrdyr7","state":"COMPLETE"},{"after":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700062943915516376,4194304],"before":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700060354454443618,4194304],"closed":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700062943915516376,4194304],"expected":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700060354454443618,4210688],"key":"checkpoint-2/native-observation.json","preflight":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700060354454443618,4194304],"source_name":"native-observation.json","source_root":"/qualification-reference/scratch/pc297-4yntz90o","state":"COMPLETE"},{"after":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700062943916397545,4194304],"before":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700060354454657827,4194304],"closed":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700062943916397545,4194304],"expected":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700060354454657827,4210688],"key":"checkpoint-2/trainer_state.json","preflight":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700060354454657827,4194304],"source_name":"trainer_state.json","source_root":"/qualification-reference/scratch/pc297-4yntz90o","state":"COMPLETE"}],"moved_bytes":8589934592,"new_bulk_written_bytes":0,"op":"v307-owned-volume-recovery","original_preparation":{"buffer_bytes":8388608,"cache":"fresh-generated-not-evicted","elapsed_ns":40528727250,"final_free_bytes":15917719552,"initial_free_bytes":24537923584,"written_bytes":8589934592},"partial":"/qualification-reference/scratch/pc305-nklrdyr7","partial_failure_evidence":["bulk-input/staging-failure.json",633,"0000000000000000000000000000000000000000000000000000000000000005"],"partial_root_identity":[101,1007,16832,503,20],"source":"/qualification-reference/scratch/pc297-4yntz90o","source_evidence":[["execution.json",497,"0000000000000000000000000000000000000000000000000000000000000006"],["diagnostics/v290-volume.json",3788,"0000000000000000000000000000000000000000000000000000000000000007"],["bulk-input/manifest.json",1393,"0000000000000000000000000000000000000000000000000000000000000008"]],"source_root_identity":[101,1008,16832,503,20],"v":1}'''
TIMEOUT = r'''{"status":"NONPASS_EXTERNAL_TIMEOUT","spec":"parent-v310-optimized-ac-volume-spec.json","spec_sha256":"0000000000000000000000000000000000000000000000000000000000000009","root":"/qualification-reference/scratch/pc309-80pg7a82","actual_execute_exit":null,"signal":"TIMEOUT","external_limit_seconds":30,"internal_limit_seconds":29,"execution_report_absent":true,"metrics_absent":true,"buffered_logs_empty":true,"observed_state":"All four files moved into volume-case/export/run/checkpoint-{1,2}; diagnostics directory exists but has no completed metric. No inference on C read progress, publication, joins or release.","previous_success":"V29828.580670667internal/28.70wall predates two-line optimization and reused-cache run. Different cache conditions; no causal performance regression attribution.","recovery":{"actual_exit":0,"internal_seconds":0.009627292,"wall_seconds":0.08,"bytes":8589934592,"new_bulk_bytes":0,"manifest_sha256":"000000000000000000000000000000000000000000000000000000000000000a","receipt_sha256":"000000000000000000000000000000000000000000000000000000000000000b","metadata_identity_validation":"PASS_before_test","full_content_hash":"NOT_CONFIRMED_THIS_RUN"},"one_recovery_consumed":true,"no_unchanged_retry":true,"source_only_diagnosis_task":"public-review-01","gpu_native_science":"0/7"}'''
GENERATION = r'''{"bulk_bytes_read":0,"evidence":[{"base":"/qualification-reference/scratch/pc309-80pg7a82","name":"bulk-input/manifest.json","sha256":"000000000000000000000000000000000000000000000000000000000000000a","size":1419},{"base":"/qualification-reference/scratch/pc309-80pg7a82","name":"bulk-input/staging-receipt.json","sha256":"000000000000000000000000000000000000000000000000000000000000000b","size":4617},{"base":"/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06","name":"parent-v310-volume-nonpass.json","sha256":"000000000000000000000000000000000000000000000000000000000000000c","size":1461},{"base":"/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06","name":"parent-v314-diagnostic-run-authorization.json","sha256":"000000000000000000000000000000000000000000000000000000000000000d","size":866}],"files":[{"identity":[101,1002,33152,503,20,1,2147483648,1700060281922665152,1700063061211314784,4210688],"key":"checkpoint-1/native-observation.json","name":"blob-1.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000001","size":2147483648},{"identity":[101,1003,33152,503,20,1,2147483648,1700060293388071224,1700063061211576993,4194304],"key":"checkpoint-1/trainer_state.json","name":"blob-2.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000002","size":2147483648},{"identity":[101,1004,33152,503,20,1,2147483648,1700060303027173964,1700063061211807535,4194304],"key":"checkpoint-2/native-observation.json","name":"blob-3.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000003","size":2147483648},{"identity":[101,1005,33152,503,20,1,2147483648,1700060312459346547,1700063061212040119,4194304],"key":"checkpoint-2/trainer_state.json","name":"blob-4.bin","sha256":"0000000000000000000000000000000000000000000000000000000000000004","size":2147483648}],"hashes_are_expectations_only":true,"new_bulk_written_bytes":0,"op":"v316-timeout-source-generation","prior_status":"NONPASS_EXTERNAL_TIMEOUT","source":"/qualification-reference/scratch/pc309-80pg7a82","source_directories":{".":[101,1006,16832,503,20],"bulk-input":[101,1001,16832,503,20],"volume-case":[101,1009,16832,503,20],"volume-case/export":[101,1010,16832,503,20],"volume-case/export/run":[101,1011,16832,503,20],"volume-case/export/run/checkpoint-1":[101,1012,16832,503,20],"volume-case/export/run/checkpoint-2":[101,1013,16832,503,20]},"v":1}'''


def _inputs():
    return [json.loads(value) for value in (MANIFEST, RECEIPT, TIMEOUT, GENERATION)]


@pytest.mark.parametrize("allocation_drift", [False, True],
                         ids=["exact-provenance-four-ordered", "dense-allocation-drift"])
def test_timeout_recovery_accepts_exact_provenance(allocation_drift):
    args = _inputs()
    if allocation_drift:
        args[3]["files"][0]["identity"][9] = 4194304
        args[3]["files"][1]["identity"][9] = 4210688
    before = deepcopy(args)
    result = recovery._validated_sources(*args)
    assert type(result) is tuple and len(result) == 4
    assert result == tuple(before[3]["files"])
    assert tuple(row["key"] for row in result) == (
        "checkpoint-1/native-observation.json", "checkpoint-1/trainer_state.json",
        "checkpoint-2/native-observation.json", "checkpoint-2/trainer_state.json")
    assert args == before


NEGATIVE_CASES = (
    "missing-file", "extra-file", "file-key-order", "name", "size", "hash",
    "inode", "mtime", "sparse-current", "alias", "timeout-status", "receipt-root",
    "source-root", "cache", "preparation-byte-count", "incomplete-receipt-moves",
    "missing-directory-binding", "wrong-generation-operation",
)


@pytest.mark.parametrize("mutation", NEGATIVE_CASES)
def test_timeout_recovery_refuses_provenance_mutation(mutation):
    manifest, receipt, timeout, generation = args = _inputs()
    first = generation["files"][0]
    if mutation == "missing-file":
        generation["files"].pop()
    elif mutation == "extra-file":
        generation["files"].append(deepcopy(first))
    elif mutation == "file-key-order":
        generation["files"][0], generation["files"][1] = (
            generation["files"][1], generation["files"][0])
    elif mutation == "name":
        first["name"] = "other.bin"
    elif mutation == "size":
        first["size"] -= 1
    elif mutation == "hash":
        first["sha256"] = "0" * 64
    elif mutation == "inode":
        first["identity"][1] += 1
    elif mutation == "mtime":
        first["identity"][7] += 1
    elif mutation == "sparse-current":
        first["identity"][9] = 4194303
    elif mutation == "alias":
        generation["files"][1]["identity"] = deepcopy(first["identity"])
    elif mutation == "timeout-status":
        timeout["status"] = "PASS"
    elif mutation == "receipt-root":
        receipt["destination_root_identity"][1] += 1
    elif mutation == "source-root":
        generation["source"] = "/qualification-reference/scratch/not-the-owned-root"
    elif mutation == "cache":
        manifest["preparation"]["cache"] = "fresh-generated-not-evicted"
    elif mutation == "preparation-byte-count":
        manifest["preparation"]["written_bytes"] -= 1
    elif mutation == "incomplete-receipt-moves":
        receipt["moved"].pop()
    elif mutation == "missing-directory-binding":
        del generation["source_directories"]["volume-case/export/run/checkpoint-2"]
    elif mutation == "wrong-generation-operation":
        generation["op"] = "not-v316-timeout-source-generation"
    else:
        raise AssertionError("unknown test mutation")
    before = deepcopy(args)
    with pytest.raises(ValueError):
        recovery._validated_sources(*args)
    assert args == before
