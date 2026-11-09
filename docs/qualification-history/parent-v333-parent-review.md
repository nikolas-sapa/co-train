# Parent review of revised SWE CPU output

SOURCE ONLY UNRUN. Genuine SWE worker returned text; parent extracted/froze these files and repaired tests. Production unchanged.

Rejected worker test defects: `_with_mode` again used stat_result index2 (device) rather than index0 (mode), which would not exercise intended faults. Reconstructing stat_result also loses nanosecond attributes. Parent replaced it with a test-only mode view forwarding all other genuine metadata, with explicit field assertions. Parent registered original API functions with monkeypatch BEFORE arm swaps so failed timing/trace paths cannot contaminate later cases. These repairs are parent-authored, not SWE-authored. Candidate changes only two function bodies; no cross-await caching/classes installed. Eight new cases remain unexecuted pending review. Full source copies are experiment-only.
