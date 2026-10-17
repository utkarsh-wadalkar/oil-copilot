# Recorded answers

- Dataset: `assets/flytbase-dataset/sample-data`
- Questions: `assets\flytbase-dataset\03-evaluation-queries.md` (sha256 `c0a7ae962aa1f212`)
- Mode: **offline-deterministic**, user `U-201`
- Generated: 2026-10-17T10:31:47.270234+00:00

## Q1. Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.

<details><summary>Expected (from the question document)</summary>

- Expected (status card): **No, it is not producing oil.**
  - Latest inspection INS-0001-0203, on 15 Oct 2026, by drone, by Ryan Brooks.
  - The wellhead was only 3.2 °C warmer than the air, below the T200 limit.
  - Reason: note CTX-0001-003 by Jake Morales, a planned shut-in from 7 Oct for rod string replacement, expected back around 20 Oct. It is not yet in the maintenance system.
  - The recorded status still says `active`, which is out of date.

</details>

**Status:** complete

**Summary:** 1 status result(s).

**Visual:** `card`, 1 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0001 | INS-0001-0203 | 2026-10-15 | 2026-10-15T09:45:00+00:00 | T200 | 25.6 | 22.4 | 3.2 |

**Wells:** WELL-0001

**Evidence refs:** 6

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q2. Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.

<details><summary>Expected (from the question document)</summary>

- Expected (table): four T200 wells, all last inspected on 15 Oct 2026. Two have no recorded reason.

  | Well | Wellhead above air | Recorded status | Reason |
  |---|---|---|---|
  | WELL-0164 | 4.1 °C | active (out of date) | **No recorded reason.** The inspector noted "Pump jack not moving." |
  | WELL-0170 | 2.9 °C | down | Repair MNT-0170-031, pump jack walking beam bearing wear, started 19 Sep, still open |
  | WELL-0172 | 5.7 °C | active (out of date) | Repair MNT-0172-028, flowline pinhole leak, started 3 Oct, still open |
  | WELL-0175 | 0.4 °C | active (out of date) | **No recorded reason** |

  Where nothing explains the stop, the copilot says so and suggests a check. It must not invent a cause.

</details>

**Status:** complete

**Summary:** 4 status result(s).

**Visual:** `table`, 4 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0164 | INS-0164-0205 | 2026-10-15 | 2026-10-15T11:45:00+00:00 | T200 | 24.0 | 19.9 | 4.1 |
| WELL-0170 | INS-0170-0206 | 2026-10-15 | 2026-10-15T14:15:00+00:00 | T200 | 23.9 | 21.0 | 2.9 |
| WELL-0172 | INS-0172-0206 | 2026-10-15 | 2026-10-15T07:45:00+00:00 | T200 | 27.2 | 21.5 | 5.7 |
| WELL-0175 | INS-0175-0204 | 2026-10-15 | 2026-10-15T08:00:00+00:00 | T200 | 24.3 | 23.9 | 0.4 |

**Wells:** WELL-0164, WELL-0170, WELL-0172, WELL-0175

**Evidence refs:** 14

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q3. Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil.

<details><summary>Expected (from the question document)</summary>

- Expected (line chart): 13 readings (23 Jul to 15 Oct 2026). Not producing oil on 8 Oct and 15 Oct.

</details>

**Status:** complete

**Summary:** 13 temperatures result(s).

**Visual:** `line`, 13 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0001 | INS-0001-0191 | 2026-07-23 | 2026-07-23T11:30:00+00:00 | T200 | 61.2 | 33.1 | 28.1 |
| WELL-0001 | INS-0001-0192 | 2026-07-30 | 2026-07-30T10:30:00+00:00 | T200 | 58.2 | 32.0 | 26.2 |
| WELL-0001 | INS-0001-0193 | 2026-08-06 | 2026-08-06T15:30:00+00:00 | T200 | 65.0 | 35.1 | 29.9 |
| WELL-0001 | INS-0001-0194 | 2026-08-13 | 2026-08-13T09:30:00+00:00 | T200 | 60.6 | 34.0 | 26.6 |
| WELL-0001 | INS-0001-0195 | 2026-08-20 | 2026-08-20T14:15:00+00:00 | T200 | 59.3 | 36.3 | 23.0 |
| WELL-0001 | INS-0001-0196 | 2026-08-27 | 2026-08-27T13:45:00+00:00 | T200 | 61.2 | 34.4 | 26.8 |
| WELL-0001 | INS-0001-0197 | 2026-09-03 | 2026-09-03T13:00:00+00:00 | T200 | 65.2 | 34.5 | 30.7 |
| WELL-0001 | INS-0001-0198 | 2026-09-10 | 2026-09-10T07:30:00+00:00 | T200 | 52.8 | 27.2 | 25.6 |
| WELL-0001 | INS-0001-0199 | 2026-09-17 | 2026-09-17T15:30:00+00:00 | T200 | 53.6 | 31.2 | 22.4 |
| WELL-0001 | INS-0001-0200 | 2026-09-24 | 2026-09-24T15:00:00+00:00 | T200 | 45.7 | 23.6 | 22.1 |
| WELL-0001 | INS-0001-0201 | 2026-10-01 | 2026-10-01T09:45:00+00:00 | T200 | 50.4 | 23.0 | 27.4 |
| WELL-0001 | INS-0001-0202 | 2026-10-08 | 2026-10-08T10:45:00+00:00 | T200 | 23.4 | 20.2 | 3.2 |
| WELL-0001 | INS-0001-0203 | 2026-10-15 | 2026-10-15T09:45:00+00:00 | T200 | 25.6 | 22.4 | 3.2 |

**Wells:** WELL-0001

**Evidence refs:** 18

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q4. How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.

<details><summary>Expected (from the question document)</summary>

- Expected (table): **6 spills, 15.1 barrels.**
  - There were 7 detections. INS-0001-0070 (7 Mar 2024) was corrected as rainwater (CTX-0001-001) and does not count.
  - Spills: 16 Mar 2023 (0.5 bbl), 27 Apr 2023 (2.6), 28 Sep 2023 (3.3), 19 Oct 2023 (0.3), 11 Jun 2026 (6.8), 1 Oct 2026 (1.6).

</details>

**Status:** complete

**Summary:** 6 spills result(s).

**Visual:** `table`, 6 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0001 | INS-0001-0021 | 2023-03-16 | 2023-03-16T14:00:00+00:00 | T200 | 42.7 | 15.7 | 27.0 |
| WELL-0001 | INS-0001-0027 | 2023-04-27 | 2023-04-27T15:30:00+00:00 | T200 | 47.1 | 22.1 | 25.0 |
| WELL-0001 | INS-0001-0048 | 2023-09-28 | 2023-09-28T14:15:00+00:00 | T200 | 45.3 | 24.8 | 20.5 |
| WELL-0001 | INS-0001-0051 | 2023-10-19 | 2023-10-19T08:00:00+00:00 | T200 | 38.0 | 18.5 | 19.5 |
| WELL-0001 | INS-0001-0185 | 2026-06-11 | 2026-06-11T14:30:00+00:00 | T200 | 61.1 | 37.1 | 24.0 |
| WELL-0001 | INS-0001-0201 | 2026-10-01 | 2026-10-01T09:45:00+00:00 | T200 | 50.4 | 23.0 | 27.4 |

**Wells:** WELL-0001

**Evidence refs:** 14

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q5. How many days was WELL-0001 down in 2025?

<details><summary>Expected (from the question document)</summary>

- Expected (a short answer with its evidence; no visual needed): **21 days**, from three weekly inspections where it was not producing oil.
  - **24 Jul 2025:** the wellhead read 51.6 °C, which looks hot, but the air was 43.1 °C. That is only 8.5 °C warmer, so the well was not producing oil. Cause: the prime mover tripped (MNT-0001-021).
  - **16 and 23 Oct 2025:** stuffing box packing leak (MNT-0001-023).

</details>

**Status:** complete

**Summary:** 1 downtime result(s).

**Visual:** `text`, 1 row(s)

| well_id | downtime_days | latest_nonproducing |
|---|---|---|
| WELL-0001 | 21 | 2025-10-23T11:45:00 |

**Wells:** WELL-0001

**Evidence refs:** 5

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q6. Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.

<details><summary>Expected (from the question document)</summary>

- Expected (bar chart): **WELL-0121: 49 days** (T200), **WELL-0138: 42 days** (T350), **WELL-0107: 42 days** (T350). Next is WELL-0119 at 28.

</details>

**Status:** complete

**Summary:** 3 downtime result(s).

**Visual:** `bar`, 3 row(s)

| well_id | downtime_days | latest_nonproducing |
|---|---|---|
| WELL-0121 | 49 | 2026-10-15T07:45:00 |
| WELL-0138 | 42 | 2026-10-08T11:00:00 |
| WELL-0107 | 42 | 2026-08-06T12:45:00 |

**Wells:** WELL-0121, WELL-0138, WELL-0107

**Evidence refs:** 62

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q7. Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.

<details><summary>Expected (from the question document)</summary>

- Expected (map with 4 pins):

  | Well | Date | Barrels | Location (lat, lon) |
  |---|---|---|---|
  | WELL-0151 | 24 Sep 2026 | 4.5 | 32.12246, −102.18445 |
  | WELL-0165 | 30 Jul 2026 | 1.2 | 32.15665, −102.14522 |
  | WELL-0175 | 30 Jul 2026 | 3.9 | 32.18020, −102.14790 |
  | WELL-0186 | 23 Jul 2026 | 0.6 | 32.17552, −102.17775 |

</details>

**Status:** complete

**Summary:** 4 spills result(s).

**Visual:** `map`, 4 row(s)

| well_id | inspection_id | date | inspected_at | well_type | wellhead_temp_c | ambient_temp_c | delta_c |
|---|---|---|---|---|---|---|---|
| WELL-0151 | INS-0151-0201 | 2026-09-24 | 2026-09-24T15:30:00+00:00 | T350 | 62.6 | 26.4 | 36.2 |
| WELL-0165 | INS-0165-0194 | 2026-07-30 | 2026-07-30T11:45:00+00:00 | T200 | 70.5 | 39.4 | 31.1 |
| WELL-0175 | INS-0175-0193 | 2026-07-30 | 2026-07-30T11:45:00+00:00 | T200 | 51.8 | 32.3 | 19.5 |
| WELL-0186 | INS-0186-0097 | 2026-07-23 | 2026-07-23T14:15:00+00:00 | T200 | 61.2 | 33.6 | 27.6 |

**Wells:** WELL-0151, WELL-0165, WELL-0175, WELL-0186

**Evidence refs:** 18

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q8. Show a heatmap of 2026 spills by geographic area and month.

<details><summary>Expected (from the question document)</summary>

- Expected (heatmap of areas × Jan–Oct, with corrected detections removed):

  | Area | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Total |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | Southwest Block 23 | 4 | 3 | 3 | 6 | 3 | 4 | 4 | 3 | 3 | 2 | 35 |
  | Southwest Block 24 | 7 | 4 | 5 | 6 | 5 | 5 | 3 | 1 | 5 | 2 | **43** |
  | Northeast Block 7 | 5 | 3 | 2 | 4 | 6 | 6 | 2 | 4 | 4 | 1 | 37 |
  | Northeast Block 8 | 4 | 4 | 4 | 3 | 2 | 4 | 4 | 0 | 1 | 0 | 26 |

</details>

**Status:** complete

**Summary:** Combined 1 source-backed analyses; see the findings and evidence.

**Visual:** `heatmap`, 48 row(s)

(48 rows recorded in `answers.jsonl`)

**Evidence refs:** 288

**Conflict:** Attributed notes disagree; informal claims do not replace detection.
**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q9. Which rules has WELL-0001 broken in the last 12 months, and what is still open?

<details><summary>Expected (from the question document)</summary>

- Expected (table or list): four breaches, all from the 11 Jun 2026 spill of 6.8 bbl. USD 5,000 in fines, still open.
  - **SR-01:** reported after 41 hours (REG-0001-001), against a 24-hour limit. This led to notice of violation REG-0001-002 with a USD 5,000 fine, still open.
  - **SR-02:** contained after about 7 hours, against a 4-hour limit. This is found only in the June repair report.
  - **SR-03:** cleanup verification was due by 10 Aug 2026 and is still open (REG-0001-003).
  - **RC-04:** the notice needed a response by 30 Jul 2026, and none is recorded.

  Also still pending (open actions, not counted as breaches because the deadlines have not passed or the work is still under way):
  - A root-cause analysis is due on the flowline: 3 corrective repairs in the last 12 months (MNT-0001-028, -029, -032). The report for the October repair (MNT-0001-032) marks it as "Action required".
  - The planned shut-in from 7 Oct is not yet recorded in the maintenance system, which the T200 manual requires before work starts (note CTX-0001-003).

  The yearly flowline test (RC-02) was done on 7 Mar 2026, so that rule was met.

</details>

**Status:** complete

**Summary:** 7 compliance result(s).

**Visual:** `table`, 7 row(s)

| well_id | inspection_id | protocol | status | due_at | hours_to_report | detail |
|---|---|---|---|---|---|---|
| WELL-0001 | INS-0001-0185 | SR-01 | breach | 2026-06-12T14:30:00+00:00 | 41.0 | Late written notice |
| WELL-0001 | INS-0001-0185 | SR-03 | breach | 2026-08-10T14:30:00+00:00 |  | Agency verification remains open |
| WELL-0001 | INS-0001-0185 | RC-04 | possible breach | 2026-07-30 |  | No notice response recorded |
| WELL-0001 | INS-0001-0185 | SR-02 | breach |  |  | Containment exceeded extracted SOP deadline |
| WELL-0001 |  | RCA | pending |  |  | RCA required before next repair closes |
| WELL-0001 |  | RC-02 | met |  |  | Yearly flowline integrity test completed |
| WELL-0001 |  | manual records | pending |  |  | Well shut in from 7 Oct for planned rod string replacement.  |

**Wells:** WELL-0001

**Evidence refs:** 15

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q10. In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?

<details><summary>Expected (from the question document)</summary>

- Expected (table): 2 spills. The limit is 4 hours, and the containment time exists only inside the repair reports.
  - WELL-0082: contained after about 7.1 hours (report MNT-0082-028, inspection INS-0082-0198).
  - WELL-0100: contained after about 8.1 hours (report MNT-0100-034, inspection INS-0100-0196).

</details>

**Status:** complete

**Summary:** 69 guidance result(s).

**Visual:** `table`, 69 row(s)

(69 rows recorded in `answers.jsonl`)

**Wells:** WELL-0073, WELL-0077, WELL-0080, WELL-0082, WELL-0085, WELL-0091, WELL-0097, WELL-0098, WELL-0100

**Evidence refs:** 56

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q11. Remembering past conversations

<details><summary>Expected (from the question document)</summary>

- Expected: WELL-0121: USD 25,794 · WELL-0138: USD 46,942 · WELL-0107: USD 5,176.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q12. Correcting wrong raw data

<details><summary>Expected (from the question document)</summary>

- Expected:
  - The copilot records the correction against inspection INS-0164-0205. It keeps the original value (24.0 °C) and notes who corrected it and why.
  - With 41.0 °C against 19.9 °C air (21.1 °C warmer, above the T200 limit), WELL-0164 **is producing oil**.
  - The copilot also points out that the same inspection has the note "Pump jack not moving." (Tyler Hughes), which disagrees with the correction, and asks Michael Turner to confirm.
- Then Michael Turner asks Q2 again.
  - Expected: **three wells** (WELL-0170, WELL-0172, WELL-0175). WELL-0164 is no longer listed, and the answer says why.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q13. Correcting the AI's analysis

<details><summary>Expected (from the question document)</summary>

- Expected:
  - The copilot records the corrected volume against inspection INS-0151-0201, keeping the AI's estimate for reference.
  - At 5.4 bbl the spill is **reportable** under the Spill Response SOP. A written notice was due within 24 hours of the 24 Sep 15:30 inspection, and **none is recorded**. The copilot flags this as a possible SR-01 breach.
  - Repair report MNT-0151-025 classed the spill as "moderate" and listed no reporting duty. That was based on the old estimate and no longer holds. (The same report already shows containment took about 6.4 hours, an SR-02 breach.)
  - Because it is now a reportable spill, agency verification of the clean-up (SR-03) is also due within 60 days, by 23 Nov 2026.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q14. A rule for a whole well type

<details><summary>Expected (from the question document)</summary>

- Expected: **WELL-0108, WELL-0121 and WELL-0138**, with 3 corrective pump jack repairs each in the last 12 months (T200 manual section 10; the T350 manual refers to it).
- Michael Turner: *"Note for all T350 wells: our team now wants a pump jack root-cause analysis after 2 repairs, not 3."* Then, in a new chat, he asks the same question again.
  - Expected: **WELL-0108, WELL-0120, WELL-0121 and WELL-0138.**
    - WELL-0120 is a T350 well with 2 repairs, so it is now added.
    - WELL-0102 also has 2 repairs, but it is a T200 well, so it must **not** be added.
    - The answer says this follows Michael Turner's rule, not the manual.

---

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q16. Shared knowledge, private memory

<details><summary>Expected (from the question document)</summary>

- Expected: yes, from 17 Oct for about 10 days, according to Jake Morales.
- Then Jessica Reed: *"For the three wells we discussed yesterday, what have repairs cost this year?"* (This follows Q11.)
  - Expected: the copilot says it has no such earlier conversation with Jessica Reed. It must **not** use Michael Turner's history from Q11.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q17. People disagree with the data

<details><summary>Expected (from the question document)</summary>

- Expected: the copilot tells Tyler Hughes that the 15 Oct inspection (by Jessica Reed) shows the wellhead only 0.4 °C above the air, so the well is not producing oil. That matches Michael Turner's note, not Tyler Hughes's claim. The copilot keeps both statements on record, marks Tyler Hughes's as unconfirmed, and asks for confirmation.
- Then Jake Morales: *"WELL-0001 is back online since 14 Oct."*
  - Expected: the copilot points out that the 15 Oct inspection shows WELL-0001 not producing oil, and that note CTX-0001-003 expects a return around 20 Oct. It records the claim as unconfirmed.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---

## Q18. People disagree about the AI's analysis

<details><summary>Expected (from the question document)</summary>

- Expected:
  - The AI flagged a 1.0 bbl spill at inspection INS-0101-0197 ("Oil sheen around cellar").
  - Two notes disagree: Ryan Brooks thought it was produced water (CTX-0101-002), but Chris Dalton (HSE) sampled the stain and confirmed crude (CTX-0101-003).
  - Neither note is a formal correction, and a spill repair (MNT-0101-029) was done, so the detection stands.
  - The copilot answers **yes** but shows the disagreement and both sources.

</details>

**Status:** complete

**Summary:** 200 status result(s).

**Visual:** `table`, 200 row(s)

(200 rows recorded in `answers.jsonl`)

**Wells:** WELL-0001, WELL-0002, WELL-0003, WELL-0004, WELL-0005, WELL-0006, WELL-0007, WELL-0008, WELL-0009, WELL-0010, WELL-0011, WELL-0012, WELL-0013, WELL-0014, WELL-0015, WELL-0016, WELL-0017, WELL-0018, WELL-0019, WELL-0020, WELL-0021, WELL-0022, WELL-0023, WELL-0024, WELL-0025, WELL-0026, WELL-0027, WELL-0028, WELL-0029, WELL-0030, WELL-0031, WELL-0032, WELL-0033, WELL-0034, WELL-0035, WELL-0036, WELL-0037, WELL-0038, WELL-0039, WELL-0040, WELL-0041, WELL-0042, WELL-0043, WELL-0044, WELL-0045, WELL-0046, WELL-0047, WELL-0048, WELL-0049, WELL-0050, WELL-0051, WELL-0052, WELL-0053, WELL-0054, WELL-0055, WELL-0056, WELL-0057, WELL-0058, WELL-0059, WELL-0060, WELL-0061, WELL-0062, WELL-0063, WELL-0064, WELL-0065, WELL-0066, WELL-0067, WELL-0068, WELL-0069, WELL-0070, WELL-0071, WELL-0072, WELL-0073, WELL-0074, WELL-0075, WELL-0076, WELL-0077, WELL-0078, WELL-0079, WELL-0080, WELL-0081, WELL-0082, WELL-0083, WELL-0084, WELL-0085, WELL-0086, WELL-0087, WELL-0088, WELL-0089, WELL-0090, WELL-0091, WELL-0092, WELL-0093, WELL-0094, WELL-0095, WELL-0096, WELL-0097, WELL-0098, WELL-0099, WELL-0100, WELL-0101, WELL-0102, WELL-0103, WELL-0104, WELL-0105, WELL-0106, WELL-0107, WELL-0108, WELL-0109, WELL-0110, WELL-0111, WELL-0112, WELL-0113, WELL-0114, WELL-0115, WELL-0116, WELL-0117, WELL-0118, WELL-0119, WELL-0120, WELL-0121, WELL-0122, WELL-0123, WELL-0124, WELL-0125, WELL-0126, WELL-0127, WELL-0128, WELL-0129, WELL-0130, WELL-0131, WELL-0132, WELL-0133, WELL-0134, WELL-0135, WELL-0136, WELL-0137, WELL-0138, WELL-0139, WELL-0140, WELL-0141, WELL-0142, WELL-0143, WELL-0144, WELL-0145, WELL-0146, WELL-0147, WELL-0148, WELL-0149, WELL-0150, WELL-0151, WELL-0152, WELL-0153, WELL-0154, WELL-0155, WELL-0156, WELL-0157, WELL-0158, WELL-0159, WELL-0160, WELL-0161, WELL-0162, WELL-0163, WELL-0164, WELL-0165, WELL-0166, WELL-0167, WELL-0168, WELL-0169, WELL-0170, WELL-0171, WELL-0172, WELL-0173, WELL-0174, WELL-0175, WELL-0176, WELL-0177, WELL-0178, WELL-0179, WELL-0180, WELL-0181, WELL-0182, WELL-0183, WELL-0184, WELL-0185, WELL-0186, WELL-0187, WELL-0188, WELL-0189, WELL-0190, WELL-0191, WELL-0192, WELL-0193, WELL-0194, WELL-0195, WELL-0196, WELL-0197, WELL-0198, WELL-0199, WELL-0200

**Evidence refs:** 414

**Warning:** No model credentials configured; using the deterministic offline planner.

---
