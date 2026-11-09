> Sanitized public reference. Historical acceptance applies to the private original, not these derivative bytes.

# File RPC correction report, UNRUN

## Status and exact written paths

Source correction only. No commands, Python imports/execution, tests, SDK/cloud
calls or Git performed by this worker. No PASS or compliance claim.
The previous report's nonexistent APIs, vacuous tests and checkmarks are
withdrawn. The rejected sibling copy was not read or edited.

Only these four assigned paths were written:
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-nemotron-file-rpc/train/qualification_file_rpc.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-nemotron-file-rpc/train/test_qualification_file_rpc.py`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-nemotron-file-rpc/docs/core-v159-rpc-plan.md`
- `/qualification-reference/scratch/cotrain-devin-continuation-2026-11-06/core-v159-nemotron-file-rpc/docs/core-v159-rpc-report.md`

Plan written first, replacement public-path tests next, implementation next,
then static source review and additional fault-injection tests.

## Source changes

Public API is `serve_file_rpc(stdin, stdout, *, roots=None)`. It reads metadata
itself and writes real framed put/get/manifest responses, not returned Python
lists. Requests and success responses use contract B exact schemas. JSON rejects
duplicates, nonfinite/float values and bool-as-int. Hashes accept 64 hex digits,
normalized lowercase for comparison/responses.

Metadata length 1..1,048,576, data frames 1..65,536, four-byte big-endian lengths,
zero terminator and EOF are enforced. Get/manifest requests require an empty
terminated body. File payloads stream; metadata and bounded manifest JSON alone
are buffered. Short reads/writes loop; zero write progress fails.

Directory traversal uses actual Python 3.12 `os.open(..., dir_fd=...)` and
`os.stat(..., dir_fd=..., follow_symlinks=False)`, not nonexistent openat/fstatat
Python names. Every root ancestor and relative component is separately pinned
with O_DIRECTORY|O_NOFOLLOW; retained parent descriptors enable identity checks.
Leaves use O_NOFOLLOW|O_NONBLOCK before opened-handle regular/single-link checks.
Before/after file stats include inode/device/type/link-count/size/mtime/ctime.

Put is exclusive, mode 0600, streams into its opened inode, validates received
hash/size, then rehashes actual stored bytes. It checks file/path identity again
after acknowledgement metadata, before the zero terminator. It never unlinks
on failure: errors explicitly report retained/uncertain partials. This avoids
a check-then-unlink race deleting an unknown replacement. A failed key cannot
be retried without separate owner-controlled cleanup.

Get prehashes and then rehashes while exporting from the same handle. Mutations
or identity drift prevent the success terminator. Manifest hashes actual opened
regular files with size/hash-bracketing stats, validates each entry, uses bounded
DFS and emits sorted canonical JSON. Invalid/unreadable members fail, not skip.
Directory timestamp changes during enumeration also fail.

Declared ceilings, inclusive:
- File: 2,147,483,648 bytes (2 GiB), larger than model 1,192,135,096 bytes.
- Manifest file aggregate: 8,589,934,592 bytes (8 GiB).
- Manifest files: 10,000; directory depth: 32 (root zero).
- Directory entries visited: 20,000, including directories.
- Serialized manifest: 8,388,608 bytes (8 MiB).
- Key: 4,096 UTF-8 bytes, 64 components, each at most 255 bytes.

Request limits above declared ceilings reject instead of silently clamping.
Directory depth zero allows root files but no child directory, even empty.
Put parents must already exist.

Seven production roots remain source/model/data/wheels under
`/opt/qualification/`, output/evidence under `/var/tmp/qualification/`, and
request at `/var/tmp/qualification/request-input`. CLI exposes only `--serve`,
one operation, no root override or training/command execution. Public errors
raise RPCError. CLI exits 1 with generic stderr, no unfrozen error metadata or
error frame appended after a partial response. Consumers require valid complete
framing AND actual exit 0, not a metadata `ok` boolean.

## Test source and proposed mutational witnesses

73 ordinary finite unittest methods, all reaching the real public wire path.
No parametrization, plugins, processes or sockets. Filesystem calls remain real;
selected wrappers shorten I/O or inject deterministic mutations/errors.
These are candidate witnesses, not executed mutation-test results:

| Proposed guard mutation | Specific test witness / observable assertion |
| --- | --- |
| Reject valid maximum metadata / raise metadata cap | `test_metadata_exact_1048576_whitespace` / `test_metadata_1048577_before_payload_read`: valid padded JSON succeeds; oversized header reads exactly 4 bytes |
| Remove 64 KiB chunk guard | `test_chunk_65537_before_payload_read`: expects chunk-length error before payload; `test_chunk_65536` checks inclusive success |
| Drop terminator or EOF enforcement | `test_missing_terminator`, `test_trailing_body`, `test_get_requires_eof`, `test_manifest_requires_eof` |
| Drop declared hash/size checks | `test_put_wrong_hash_retains_explicit_partial`, `test_put_short_size`, `test_put_oversize`, `test_get_wrong_hash_before_response`, `test_get_wrong_size` |
| Trust received bytes rather than actual written inode | `test_put_rehashes_written_inode`: real write corrupts stored byte to `!`, expected stored-hash failure |
| Remove duplicate/nonfinite/exact type/schema guards | `test_duplicate_json`, `test_nonfinite_json`, `test_bool_size`, `test_bool_version`, `test_exact_schema_extra`, `test_exact_schema_missing` |
| Permit symbolic-link traversal (remove nofollow and identity protections) | `test_leaf_symlink`, `test_intermediate_symlink`, `test_root_symlink`, `test_root_ancestor_symlink` |
| Remove single-link constraint | `test_hardlink_get`, `test_manifest_hardlink_not_omitted` |
| Remove exclusive creation | `test_overwrite_preserves_original`: old bytes must remain `old` |
| Remove O_NONBLOCK | `test_fifo_nonblocking_get`: asserts flag before real FIFO syscall, so mutation fails rather than hangs |
| Remove short-write loop / no-progress guard | `test_short_input_file_and_output_writes`, `test_zero_progress_file_write_fails`, `test_zero_progress_output_write_fails` |
| Remove opened-file path identity checks | `test_put_replacement_retains_unknown_inode`, `test_get_replacement_before_response`: real rename/replacement; unknown bytes preserved |
| Omit final put identity check | `test_put_replacement_during_ack_has_no_terminator`: replacement during real response writes, no successful terminator |
| Omit stable handle stamp/hash check during export | `test_get_same_inode_mutation_during_send_no_terminator`: last byte changes from `b` to `c` after first 64 KiB response chunk |
| Stop checking pinned root identity | `test_root_directory_replacement_during_put`: real directory rename/replacement, unknown file preserved |
| Skip invalid/unreadable manifest entries | `test_manifest_symlink_not_omitted`, `test_manifest_unreadable_member_is_not_omitted`: hard failure, no manifest response |
| Remove manifest actual-data stability checks | `test_manifest_file_mutation_is_not_a_valid_manifest`, `test_manifest_directory_mutation_fails` |
| Change inclusive aggregate ceilings or omit failure | `test_manifest_inclusive_limits`, `test_manifest_bytes_one_over`, `test_manifest_members_one_over`, `test_manifest_depth_one_over_empty_directory`, `test_empty_manifest_zero_limits` |
| Remove directory-work / encoded-manifest cap | `test_manifest_directory_work_bound`, `test_manifest_json_byte_ceiling`: reduced runtime ceilings exercise exact equality then one-over failure without huge fixtures |
| Restore 1 GiB file cap / unbound cap | `test_model_size_reaches_body_without_gigabyte_allocation`, `test_file_cap_exact_reaches_body`, `test_file_cap_plus_one_metadata_rejection`: header-only tests create at most empty retained files |
| Leak explicit directory/file descriptors | `test_all_open_fds_closed_success_and_failure`: real open/close wrappers track zero live FDs after successful manifest, aggregate error, bad put and missing intermediate directory |

## Remaining gaps and required parent work

- All 73 tests, compilation, guard-removal controls and platform compatibility
  remain UNRUN. Parent must review and execute, including real Linux Python 3.12.
- CLI process exit behavior and real consumer integration are not exercised by
  these no-process tests. Parent must verify nonzero exit and incomplete output
  refusal using its authorized execution lane.
- No large model/data/wheel bytes were read. Header-only model/cap witnesses do
  not prove real 1.19 GB throughput, memory peak, durability or transport behavior.
- Filesystem checks are not an atomic snapshot or protection against a hostile
  writer changing/restoring state between checks. Production needs privately
  owned, quiescent trees. Manifest describes observed file reads, not independent
  attestation; files changed after their completed scan may require a new manifest.
- Root ancestors must contain no symlinks. On Darwin `/var` is often a symlink;
  unit tests resolve their temporary root to its physical path. Production fixed
  Linux paths must meet the no-symlink requirement, not silently resolve links.
- Partials remain on put failure; automatic cleanup/retry is intentionally absent.
  Parent/orchestrator must preserve failure and handle owned cleanup separately.
- Root creation, private native request materialization, SDK host authorization,
  receipt generation, transport deadlines/exit verification and training remain
  outside this generic RPC. No bool or receipt grants host authority.

VERIFY_REAL: Four assigned source/document paths written and read with file tools;
tests and runtime checks UNRUN. No execution-based success claim.

## Parent validation after source delivery

Parent executed 73 tests, all passed in 0.768378s. Both metadata and chunk bounds have actual guard-loss/restored controls. Parent independently decoded JUnit, checked source pins and exact one-if copied mutations in `parent-v180-rpc-acceptance.json` in the continuation workspace. V168 chunk-loss expected-message metadata NONPASS remains preserved; corrected V173 loss passed without production changes. These are offline wire/filesystem tests, not GPU, provider or scientific qualification. Backend authored this correction after the rejected original Nemotron implementation.
