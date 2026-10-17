# Recorded answers

- Dataset: `assets/flytbase-dataset/sample-data`
- Questions: `assets\flytbase-dataset\03-evaluation-queries.md` (sha256 `c0a7ae962aa1f212`)
- Mode: **configured-model**, user `U-201`
- Generated: 2026-10-17T10:15:11.273498+00:00

## Q1. Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.

<details><summary>Expected (from the question document)</summary>

- Expected (status card): **No, it is not producing oil.**
  - Latest inspection INS-0001-0203, on 15 Oct 2026, by drone, by Ryan Brooks.
  - The wellhead was only 3.2 °C warmer than the air, below the T200 limit.
  - Reason: note CTX-0001-003 by Jake Morales, a planned shut-in from 7 Oct for rod string replacement, expected back around 20 Oct. It is not yet in the maintenance system.
  - The recorded status still says `active`, which is out of date.

</details>

**Status:** complete

**Summary:** Combined 2 source-backed analyses; see the findings and evidence.

**Visual:** `card`, 1 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0001 | INS-0001-0203 | 2026-10-15 | 2026-10-15T09:45:00+00:00 | T200 | 25.6 | 22.4 | 3.2 |

**Wells:** WELL-0001

**Evidence refs:** 38


---
