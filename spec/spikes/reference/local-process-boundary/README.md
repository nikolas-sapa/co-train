# Local process-boundary reference, not production

PROVES: three fresh worker/stand-in pairs passed on this macOS host. Each worker ignored three asyncio cancellations and SIGTERM and retained an active thread. Parent killed and reaped only its new worker group; the separate stand-in answered a fresh challenge and produced exactly one stop marker. Snapshot release followed worker join.

Worst baseline kill/join: 0.001561s; worst single restored guard case: 0.003833s, both below the 1s gate. Worst accepted trial including restored case: 0.167386s, below 3s. Removing the exact wrong-group guard produced the expected ordinary assertion failure; restoring byte-exact source passed. Fresh process and tiny local fixtures only.

SHORTCUT: both fixed toy children have independent 8s safety leases so a probe-parent failure cannot leave indefinite live test processes. Lease exits never count as success. The stand-in is not the actual Modal watchdog. The source is a reference, not a production supervisor foundation.

MISSING: sealed authority/live capability protocol, actual watchdog delegation, SDK exec/cancellation coupling, remote termination, billing, assets, native/tensor/GPU/science proof. Do not use this reference to authorize a paid attempt. Continuation receipts: parent-v190-local-isolation-execution.json and parent-v192-local-isolation-control-execution.json.
