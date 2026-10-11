# Trace provenance

Every published number in this repository is derived from these files. They are not
in version control: ~1.2 MB compressed, and they are evidence rather than source.
An agent auditing this project in 2026-10 concluded "no run traces survive on disk"
and was wrong, which is the reason this file exists.

**Archive:** `~/Developer/misc/co-train-artifacts/co-train-traces-2026-10-11.tar.gz`  
**sha256:** `11a51f1f8fba4b4d5d98478ceaa348f1b5d795e21b8d059a28264e85ccf47cbd`  
**Taken:** 2026-10-11

Verify a single file against this table before trusting a number derived from it:

```sh
shasum -a 256 ~/scratch/co-train-run3d/ledger-ptc-tool/traces.jsonl
```

| run dir | traces.jsonl | bytes | sha256 (first 16) |
|---|---|---:|---|
| `ptc-real` | `traces/ledger-bash-tool/traces.jsonl` | 336,799 | `82a54c17763fd0cf` |
| `ptc-real` | `traces/ledger-ptc-tool/traces.jsonl` | 195,648 | `ed94592a045e37a9` |
| `ptc-real` | `traces-run3-conc1/ledger-bash-tool/traces.jsonl` | 366,009 | `4104398bcb424333` |
| `ptc-real` | `traces-run3-conc1/ledger-ptc-tool/traces.jsonl` | 227,636 | `1107b5f764a60f1b` |
| `ptc-real-run2` | `traces/ledger-bash-tool/traces.jsonl` | 318,010 | `398f525e13e675e3` |
| `ptc-real-run2` | `traces/ledger-ptc-tool/traces.jsonl` | 154,038 | `00a5c65869a1f053` |
| `ptc-real-run2` | `traces-attempt-conc4/ledger-bash-tool/traces.jsonl` | 94,625 | `5187a61c2e48ba2a` |
| `ptc-real-run2` | `traces-attempt-conc4/ledger-ptc-tool/traces.jsonl` | 60,099 | `ddb41e9ff2abb252` |
| `ptc-real-run2c` | `traces/ledger-bash-tool/traces.jsonl` | 90,901 | `c4887fefaee3a71e` |
| `ptc-real-run2c` | `traces/ledger-ptc-tool/traces.jsonl` | 376,749 | `d9b322335c936c02` |
| `ptc-real-run2d` | `traces/ledger-bash-tool/traces.jsonl` | 333,112 | `46b50fee6c62fc73` |
| `ptc-real-run2d` | `traces/ledger-ptc-tool/traces.jsonl` | 444,344 | `0e2029616111b752` |
| `ptc-real-run2e` | `traces/ledger-bash-tool/traces.jsonl` | 307,454 | `958c3dfb2a211505` |
| `ptc-real-run2e` | `traces/ledger-ptc-tool/traces.jsonl` | 471,884 | `7bf51bb799d2e6a7` |
| `ptc-real-run2f` | `traces/ledger-bash-tool/traces.jsonl` | 333,216 | `92c6615e491f82ac` |
| `ptc-real-run2f` | `traces/ledger-ptc-tool/traces.jsonl` | 419,598 | `9d5f4c7339fe90a8` |
| `ptc-real-run2g` | `ledger-bash-tool/traces.jsonl` | 353,618 | `3590f79f46c4ec37` |
| `ptc-real-run2g` | `ledger-ptc-tool/traces.jsonl` | 158,469 | `4b9c08859d58353e` |
| `ptc-real-run2h` | `ledger-bash-tool/traces.jsonl` | 348,585 | `22a6a2f7aa1d307b` |
| `ptc-real-run2h` | `ledger-ptc-tool/traces.jsonl` | 166,338 | `c6191af045b99d18` |
| `co-train-run3a` | `ledger-bash-tool/traces.jsonl` | 812,730 | `1f781c80ae96071f` |
| `co-train-run3a` | `ledger-ptc-tool/traces.jsonl` | 191,607 | `ff997fe5734bedb6` |
| `co-train-run3b` | `ledger-bash-tool/traces.jsonl` | 701,258 | `8e5a9e45203a64be` |
| `co-train-run3b` | `ledger-ptc-tool/traces.jsonl` | 392,038 | `10d680ed84690c91` |
| `co-train-run3c` | `ledger-bash-tool/traces.jsonl` | 1,011,024 | `89ec2433d0302309` |
| `co-train-run3c` | `ledger-ptc-tool/traces.jsonl` | 398,635 | `d1048ec04ef4bd77` |
| `co-train-run3d` | `ledger-bash-tool/traces.jsonl` | 1,037,690 | `0e6e826f0114ac80` |
| `co-train-run3d` | `ledger-ptc-tool/traces.jsonl` | 395,719 | `c4d161600252276e` |
