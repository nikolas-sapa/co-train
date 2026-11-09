# File RPC correction, source-only

## Test plan BEFORE implementation

The corrected suite defines 73 finite ordinary unittest methods through
`serve_file_rpc(stdin, stdout, *, roots=None)`. Parent runs them, not this worker.
Maximum 100 methods. No processes, sockets, SDK, plugins or parametrization.

Numeric acceptance criteria:
- Valid whitespace-padded JSON metadata of exactly 1,048,576 bytes succeeds.
  A 1,048,577 prefix fails after exactly four input bytes, before body reads.
- A 65,536-byte body frame succeeds; 65,537 fails before its payload read.
  Input/output payload I/O requests never exceed 65,536 bytes.
- Each successful put/get/manifest emits one exact success metadata schema,
  correctly hashed/sized body frames, one zero terminator and EOF.
- Missing/truncated prefixes, payloads, terminators, trailing bytes, wrong
  size/hash, duplicate fields, nonfinite JSON, extra/missing fields, bool-as-int,
  bad roots and bad paths produce zero successful complete responses.
- Exclusive put never replaces existing bytes. Failed put retains its partial
  inode with explicit failure instead of a racy check-then-unlink.
- Get rejects symlink leaf/intermediate/root/root-ancestor, hardlink, directory,
  FIFO (open must include O_NONBLOCK), and missing file.
- Real filesystem rename/replacement and same-inode content mutation injected
  during I/O must prevent successful terminators, preserve unknown replacement
  files, and leave zero tracked open descriptors after success/failure.
- Short input/output/file writes still produce byte-exact roundtrips.
- Manifest byte/member/depth limits are inclusive: equality succeeds; one above
  fails, including empty directories beyond depth. Directory work is capped at
  20,000 entries; invalid/unreadable members are errors, never silently omitted.
- Per-file ceiling is 2,147,483,648 bytes, representing the 1,192,135,096-byte
  model file. A header declaring that model size must reach body framing (not a
  size-cap rejection), with no gigabyte allocation. Cap+1 fails in metadata.

Named behavioral tests will cover all boundaries above, real filesystem FD
closure, stream short writes, directory-entry work limits, changed file/path
identity, non-quiescent directory failure and manifest canonical bytes.
Guard-removal witnesses are named in the report. They remain unexecuted.

## Implementation plan

1. Replace broken tests with public wire-path tests and deterministic mutation
   injection around real stdlib I/O. Write no private-attribute-only assertions.
2. Strict bounded JSON/frame parser and exact typed request validation.
3. Pin every absolute root ancestor and relative directory using Python 3.12
   `os.open(..., dir_fd=...)`, O_DIRECTORY and O_NOFOLLOW. Retain parent handles,
   compare opened inode/device/type to nofollow path stats before/after use,
   close every descriptor using context managers.
4. Open file leaves O_NOFOLLOW|O_NONBLOCK; require regular single-link inode.
   Exclusive put streams and rehashes actual opened-handle bytes. Failed puts
   are retained, explicitly reported, never automatically deleted.
5. Get prehashes then streams a second pass from the same handle. Verify hash,
   size, inode/link/time stamps and pinned paths before success terminator.
6. Manifest bounded DFS, no silent skips, actual opened-handle sizes/hashes,
   inclusive byte/member/depth ceilings, sorted canonical bounded JSON body.
7. CLI only `--serve`, fixed production roots, one request, no generic command
   execution. Errors raise from public API; CLI emits no invented error schema
   and exits nonzero. Incomplete output must never be accepted as success.

## Frozen interface and limits

Contract B wire and seven production roots unchanged. Metadata 1 MiB, chunks
64 KiB, file 2 GiB, manifest aggregate 8 GiB, members 10,000, depth 32,
directory entries 20,000, serialized manifest 8 MiB, key 4,096 UTF-8 bytes,
64 key components, component 255 bytes. Root directory depth is zero.
Manifest max_members counts files; the separate entry ceiling counts files
and directories. Put requires pre-existing directories, never creates parents.

## Non-goals and limits

No SDK/cloud/training/authority/receipts, execution, Git, dependency installation,
credentials, immutable helper edits or other worktrees. No claim of test PASS,
snapshot isolation or adversarial concurrent-writer immunity. Root hierarchy
must already exist without symlinks; production must provide owned/quiescent
directories. Source checks detect observed mutations, not a kernel transaction.
Parent owns execution, review, integration, commits and external verification.
