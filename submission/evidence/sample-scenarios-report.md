# Scenario replay

- Dataset: `D:\ALL Programming\0-WebDev\HOct-FlyteBase\assets\flytbase-dataset\sample-data`
- Database: `D:\ALL Programming\0-WebDev\HOct-FlyteBase\eval-runs\scenarios.sqlite3` (fresh ingest per run)
- Mode: **offline-deterministic**
- Generated: 2026-10-17T11:00:06.926757+00:00

| Scenario | Checks | Failing |
|---|---|---|
| Q1 | 12 | 0 |
| Q2 | 10 | 0 |
| Q3 | 6 | 0 |
| Q4 | 5 | 0 |
| Q5 | 3 | 0 |
| Q6 | 3 | 0 |
| Q7 | 3 | 0 |
| Q8 | 7 | 0 |
| Q9 | 17 | 0 |
| Q10 | 3 | 0 |
| Q11 | 4 | 0 |
| Q12 | 17 | 0 |
| Q13 | 13 | 0 |
| Q14 | 13 | 0 |
| Q15 | 9 | 0 |
| Q16 | 11 | 0 |
| Q17 | 15 | 0 |
| Q18 | 8 | 0 |

## Q1 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | card | card | yes |
| producing | False | False | yes |
| inspection id | INS-0001-0203 | INS-0001-0203 | yes |
| date | 2026-10-15 | 2026-10-15 | yes |
| inspector | Ryan Brooks | Ryan Brooks | yes |
| delta above air | 3.2 | 3.2 | yes |
| T200 limit | 15 | 15 | yes |
| reason names the planned rod string work | contains 'rod string' | Well shut in from 7 Oct for planned rod string replacement. Work order not yet in the maintenance system. Expected back online around 20 Oct. | yes |
| reason expects a return around 20 Oct | contains '20 Oct' | Well shut in from 7 Oct for planned rod string replacement. Work order not yet in the maintenance system. Expected back online around 20 Oct. | yes |
| recorded status | active | active | yes |
| recorded status is stale | True | True | yes |
| evidence cited | status card carries evidence | 6 | yes |

## Q2 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | table | table | yes |
| wells | ['WELL-0164', 'WELL-0170', 'WELL-0172', 'WELL-0175'] | ['WELL-0164', 'WELL-0170', 'WELL-0172', 'WELL-0175'] | yes |
| deltas | [4.1, 2.9, 5.7, 0.4] | [4.1, 2.9, 5.7, 0.4] | yes |
| all last inspected 15 Oct | ['2026-10-15', '2026-10-15', '2026-10-15', '2026-10-15'] | ['2026-10-15', '2026-10-15', '2026-10-15', '2026-10-15'] | yes |
| 0164 reason is absent | No recorded reason | No recorded reason | yes |
| 0164 keeps the inspector remark | contains 'Pump jack not moving' | Pump jack not moving. | yes |
| 0170 reason is the open pump jack repair | contains 'bearing wear' | Walking beam bearing wear | yes |
| 0170 recorded status | down | down | yes |
| 0172 reason is the open flowline leak | contains 'pinhole' | Flowline corrosion pinhole leak | yes |
| 0175 reason is absent | No recorded reason | No recorded reason | yes |

## Q3 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | line | line | yes |
| reading count | 13 | 13 | yes |
| first reading | 2026-07-23 | 2026-07-23 | yes |
| last reading | 2026-10-15 | 2026-10-15 | yes |
| non-producing dates | ['2026-10-08', '2026-10-15'] | ['2026-10-08', '2026-10-15'] | yes |
| every reading carries the production limit | threshold_c on all rows | [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15] | yes |

## Q4 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | table | table | yes |
| spill count | 6 | 6 | yes |
| total barrels | 15.1 | 15.1 | yes |
| spill dates | ['2023-03-16', '2023-04-27', '2023-09-28', '2023-10-19', '2026-06-11', '2026-10-01'] | ['2023-03-16', '2023-04-27', '2023-09-28', '2023-10-19', '2026-06-11', '2026-10-01'] | yes |
| rainwater detection INS-0001-0070 excluded | False | False | yes |

## Q5 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| downtime days | 21 | 21 | yes |
| latest non-producing reading | 2025-10-23 | 2025-10-23 | yes |
| evidence cited | evidence for the three readings | 5 | yes |

## Q6 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | bar | bar | yes |
| ranked wells | [('WELL-0121', 49), ('WELL-0138', 42), ('WELL-0107', 42)] | [('WELL-0121', 49), ('WELL-0138', 42), ('WELL-0107', 42)] | yes |
| window | {'start': '2026-06-16', 'end': '2026-10-16'} | {'start': '2026-06-16', 'end': '2026-10-16'} | yes |

## Q7 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | map | map | yes |
| pin count | 4 | 4 | yes |
| pins | {'WELL-0151': (32.12246, -102.18445, '2026-09-24', 4.5), 'WELL-0165': (32.15665, -102.14522, '2026-07-30', 1.2), 'WELL-0175': (32.1802, -102.1479, '2026-07-30', 3.9), 'WELL-0186': (32.17552, -102.17775, '2026-07-23', 0.6)} | {'WELL-0151': (32.12246, -102.18445, '2026-09-24', 4.5), 'WELL-0165': (32.15665, -102.14522, '2026-07-30', 1.2), 'WELL-0175': (32.1802, -102.1479, '2026-07-30', 3.9), 'WELL-0186': (32.17552, -102.17775, '2026-07-23', 0.6)} | yes |

## Q8 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | heatmap | heatmap | yes |
| cells (4 areas x Jan-Oct) | 40 | 40 | yes |
| months | ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10'] | ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10'] | yes |
| Southwest Block 23 row | [4, 3, 3, 6, 3, 4, 4, 3, 3, 2] | [4, 3, 3, 6, 3, 4, 4, 3, 3, 2] | yes |
| Southwest Block 24 row | [7, 4, 5, 6, 5, 5, 3, 1, 5, 2] | [7, 4, 5, 6, 5, 5, 3, 1, 5, 2] | yes |
| Northeast Block 7 row | [5, 3, 2, 4, 6, 6, 2, 4, 4, 1] | [5, 3, 2, 4, 6, 6, 2, 4, 4, 1] | yes |
| Northeast Block 8 row | [4, 4, 4, 3, 2, 4, 4, 0, 1, 0] | [4, 4, 4, 3, 2, 4, 4, 0, 1, 0] | yes |

## Q9 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| SR-01 present and adverse | True | True | yes |
| SR-02 present and adverse | True | True | yes |
| SR-03 present and adverse | True | True | yes |
| RC-04 present and adverse | True | True | yes |
| breaches come from the June spill | INS-0001-0185 | INS-0001-0185 | yes |
| hours to report | 41.0 | 41.0 | yes |
| containment took about 7 hours | 7.0 | 7.0 | yes |
| containment limit | 4 | 4.0 | yes |
| SR-03 verification due | 2026-08-10 | 2026-08-10 | yes |
| SR-03 still open | open | open | yes |
| RC-04 response due | 2026-07-30 | 2026-07-30 | yes |
| RC-04 no response recorded | open | open | yes |
| fine total | 5000 | 5000.0 | yes |
| RC-02 annual flowline test met | met | met | yes |
| pending RCA on the flowline | contains 'flowline' | flowline | yes |
| planned shut-in missing from maintenance system | contains 'maintenance system' | Well shut in from 7 Oct for planned rod string replacement. Work order not yet in the maintenance system. Expected back online around 20 Oct. | yes |
| breach count | 4 | 4 | yes |

## Q10 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| visual | table | table | yes |
| late spills | [('WELL-0082', 7.1), ('WELL-0100', 8.1)] | [('WELL-0082', 7.1), ('WELL-0100', 8.1)] | yes |
| SOP containment limit | 4 | 4.0 | yes |

## Q11 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| day 1 resolved three wells | ['WELL-0121', 'WELL-0138', 'WELL-0107'] | ['WELL-0121', 'WELL-0138', 'WELL-0107'] | yes |
| recalled the earlier wells | ['WELL-0107', 'WELL-0121', 'WELL-0138'] | ['WELL-0107', 'WELL-0121', 'WELL-0138'] | yes |
| 2026 repair cost per well | {'WELL-0121': 25794, 'WELL-0138': 46942, 'WELL-0107': 5176} | {'WELL-0107': 5176, 'WELL-0121': 25794, 'WELL-0138': 46942} | yes |
| cost rows are evidenced | True | True | yes |

## Q12 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| turn asks for confirmation | pending_confirmation | pending_confirmation | yes |
| correction targets the 15 Oct inspection | INS-0164-0205 | INS-0164-0205 | yes |
| original reading preserved | 24.0 | 24.0 | yes |
| corrected reading | 41.0 | 41.0 | yes |
| author | U-201 | U-201 | yes |
| reason recorded | contains 'faulty' | The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that inspection was faulty; the field crew re-measured the wellhead at 41.0 °C. | yes |
| still provisional | pending | pending | yes |
| confirm succeeds | 200 | 200 | yes |
| correction keeps the original | 24.0 | 24.0 | yes |
| correction stores the new value | 41.0 | 41 | yes |
| history keeps before/after/author | (24.0, 41.0, 'U-201') | (24, 41, 'U-201') | yes |
| copilot flags the disagreeing inspector note | contains 'pump jack not moving' | [{"target_id": "INS-0164-0205", "message": "The inspector's remark 'Pump jack not moving.' disagrees with the corrected reading. Please confirm.", "remark": "Pump jack not moving.", "evidence_ids": []}] Prepared a correction change for INS- | yes |
| copilot asks to confirm | contains 'confirm' | Prepared a correction change for INS-0164-0205 (24.0 -> 41.0). Confirm to publish it; nothing has changed yet. If confirmed, WELL-0164 would be producing (21.1 °C above ambient, against the 15 °C T200 limit). The same inspection notes 'Pump | yes |
| with 41.0 C the well produces | True | True | yes |
| delta is 21.1 C above air | 21.1 | 21.1 | yes |
| Q2 afterwards lists three wells | ['WELL-0170', 'WELL-0172', 'WELL-0175'] | ['WELL-0170', 'WELL-0172', 'WELL-0175'] | yes |
| answer says why 0164 is gone | contains '0164' | 3 status result(s). WELL-0164 is not listed: its reading of 24.0 was corrected to 41 by Michael Turner, which makes it producing. [{"kind": "corrected_exclusion", "well_id": "WELL-0164", "inspection_id": "INS-0164-0205", "original_value": 2 | yes |

## Q13 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| turn asks for confirmation | pending_confirmation | pending_confirmation | yes |
| correction targets the 24 Sep inspection | INS-0151-0201 | INS-0151-0201 | yes |
| AI estimate preserved | 4.5 | 4.5 | yes |
| measured volume | 5.4 | 5.4 | yes |
| field | spill_est_volume_bbl | spill_est_volume_bbl | yes |
| confirm succeeds | 200 | 200 | yes |
| now reportable at 5.4 bbl | contains 'reportable' | Prepared a correction change for INS-0151-0201 (4.5 -> 5.4). Confirm to publish it; nothing has changed yet. At 5.4 bbl the spill is reportable: a written notice was due by 2026-09-25 15:30 (24 h) and none is recorded, a possible SR-01 brea | yes |
| SR-01 possible breach due 25 Sep | contains '2026-09-25' | [{"kind": "proposed_spill", "well_id": "WELL-0151", "inspection_id": "INS-0151-0201", "volume_bbl": 5.4, "reportable": true}, {"kind": "proposed_spill", "well_id": "WELL-0151", "inspection_id": "INS-0151-0201", "protocol": "SR-01", "reporta | yes |
| SR-03 verification due 23 Nov 2026 | contains '2026-11-23' | [{"kind": "proposed_spill", "well_id": "WELL-0151", "inspection_id": "INS-0151-0201", "volume_bbl": 5.4, "reportable": true}, {"kind": "proposed_spill", "well_id": "WELL-0151", "inspection_id": "INS-0151-0201", "protocol": "SR-01", "reporta | yes |
| the old moderate class no longer holds | contains 'no longer holds' | Prepared a correction change for INS-0151-0201 (4.5 -> 5.4). Confirm to publish it; nothing has changed yet. At 5.4 bbl the spill is reportable: a written notice was due by 2026-09-25 15:30 (24 h) and none is recorded, a possible SR-01 brea | yes |
| the report shows 6.4 h containment | contains '6.4' | Prepared a correction change for INS-0151-0201 (4.5 -> 5.4). Confirm to publish it; nothing has changed yet. At 5.4 bbl the spill is reportable: a written notice was due by 2026-09-25 15:30 (24 h) and none is recorded, a possible SR-01 brea | yes |
| SR-01 flagged for no written notice | possible breach | possible breach | yes |
| SR-03 due 23 Nov 2026 | 2026-11-23 | 2026-11-23 | yes |

## Q14 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| manual threshold finds three wells | ['WELL-0108', 'WELL-0121', 'WELL-0138'] | ['WELL-0108', 'WELL-0121', 'WELL-0138'] | yes |
| each has three corrective pump jack repairs | [3, 3, 3] | [3, 3, 3] | yes |
| authority is the manual | {'official manual'} | {'official manual'} | yes |
| rule change is prepared | pending_confirmation | pending_confirmation | yes |
| rule scope | T350 | T350 | yes |
| rule threshold | 2 | 2 | yes |
| rule equipment | pump_jack | pump_jack | yes |
| rule confirm succeeds | 200 | 200 | yes |
| rule adds WELL-0120 and keeps the three | ['WELL-0108', 'WELL-0120', 'WELL-0121', 'WELL-0138'] | ['WELL-0108', 'WELL-0120', 'WELL-0121', 'WELL-0138'] | yes |
| T200 WELL-0102 is not added | False | False | yes |
| the added well is T350 with two repairs | ('T350', 2) | ('T350', 2) | yes |
| answer attributes the rule to Michael Turner | ('team override', 'Michael Turner') | ('team override', 'Michael Turner') | yes |
| summary distinguishes the rule from the manual | contains 'michael turner' | 4 rca result(s). This threshold follows Michael Turner's team rule for T350, not the official manual. | yes |

## Q15 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| another user sees the correction | True | True | yes |
| the corrected value is 41.0 C | 41.0 | 41.0 | yes |
| the delta is 21.1 C above air | 21.1 | 21.1 | yes |
| answer says who corrected it | contains 'michael turner' | [{"correction_id": "d2706b75-780d-4f9b-84b2-ab4230c07605", "target_id": "INS-0164-0205", "field": "wellhead_temp_c", "value": 41, "original_value": 24, "author": "Michael Turner", "evidence_ids": ["8242e077-5a7f-4fd6-a396-89f5b0901edb:1:13" | yes |
| answer mentions the disagreeing inspector note | contains 'pump jack not moving' | [{"target_id": "INS-0164-0205", "message": "Corrected thermal reading disagrees with inspector remark. Please confirm.", "remark": "Pump jack not moving.", "evidence_ids": ["c953d955-387f-4d68-b7be-5232a4614b0f:205:205", "fb7885a3-fea4-4d3b | yes |
| only the corrected WELL-0151 spill is reportable | [('WELL-0151', 5.4)] | [('WELL-0151', 5.4)] | yes |
| the corrected spill is reportable | True | True | yes |
| no written notice is on record, so it is overdue | overdue | overdue | yes |
| the 24-hour notice deadline | 2026-09-25 | 2026-09-25 | yes |

## Q16 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| FYI is prepared for the shared store | pending_confirmation | pending_confirmation | yes |
| FYI is scoped to WELL-0007 | WELL-0007 | WELL-0007 | yes |
| FYI confirm succeeds | 200 | 200 | yes |
| answers about WELL-0007 | ['WELL-0007'] | ['WELL-0007'] | yes |
| does not answer with historical downtime days | False | False | yes |
| the attributed plan is surfaced | [('Jake Morales', True)] | [('Jake Morales', True)] | yes |
| plan starts 17 Oct | contains '17 Oct' | FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover. | yes |
| plan lasts about 10 days | contains '10-day' | FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover. | yes |
| does not reuse Michael Turner history | [] | [] | yes |
| no fleet-wide rows | [] | [] | yes |
| says there is no such earlier conversation | contains 'no earlier conversation' | I have no earlier conversation of yours that names those wells. Name the wells, an area, or a date range and I will answer from the records. | yes |

## Q17 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| shared plan claim is prepared | pending_confirmation | pending_confirmation | yes |
| claim is scoped to WELL-0175 | WELL-0175 | WELL-0175 | yes |
| claim confirm succeeds | 200 | 200 | yes |
| inspection contradicts the claim | False | False | yes |
| delta is 0.4 C above air | 0.4 | 0.4 | yes |
| inspection was by Jessica Reed | Jessica Reed | Jessica Reed | yes |
| both statements on record | {'Tyler Hughes', 'Michael Turner'} | {'Tyler Hughes', 'Michael Turner'} | yes |
| Tyler's claim is unconfirmed | {'Tyler Hughes': 'unconfirmed'} | {'Tyler Hughes': 'unconfirmed'} | yes |
| asks for confirmation | contains 'confirm' | Prepared a claim change for WELL-0175 (none -> WELL-0175 is running fine.). Confirm to publish it; nothing has changed yet. Unconfirmed shared claim disagrees with inspected production. Please confirm. | yes |
| Tyler draft confirmed as an unconfirmed claim | 200 | 200 | yes |
| inspection contradicts the claim | False | False | yes |
| latest inspection is 15 Oct | 2026-10-15 | 2026-10-15 | yes |
| note expects a return around 20 Oct | contains '20 Oct' | Well shut in from 7 Oct for planned rod string replacement. Work order not yet in the maintenance system. Expected back online around 20 Oct. | yes |
| claim recorded as unconfirmed | unconfirmed | unconfirmed | yes |
| conflict shown | contains 'confirm' | [{"target_id": "WELL-0001", "message": "Unconfirmed shared claim disagrees with inspected production. Please confirm.", "claim": "WELL-0001 is back online since 14 Oct.", "author": "Jake Morales", "evidence_ids": ["6e275215-5353-4503-9ae3-3 | yes |

## Q18 — PASS

| Check | Expected | Actual | OK |
|---|---|---|---|
| one detection | 1 | 1 | yes |
| the AI flagged INS-0101-0197 | INS-0101-0197 | INS-0101-0197 | yes |
| estimated volume | 1.0 | 1.0 | yes |
| shows Ryan Brooks produced-water note | contains 'produced water' | [{"target_id": "INS-0101-0197", "message": "Attributed notes disagree; informal claims do not replace detection.", "notes": [{"text": "Inspection INS-0101-0197: I think this was only produced water, not crude.", "author": "Ryan Brooks"}, {" | yes |
| shows Chris Dalton confirmed crude | contains 'crude' | [{"target_id": "INS-0101-0197", "message": "Attributed notes disagree; informal claims do not replace detection.", "notes": [{"text": "Inspection INS-0101-0197: I think this was only produced water, not crude.", "author": "Ryan Brooks"}, {" | yes |
| both notes retained | {'Ryan Brooks', 'Chris Dalton'} | {'Ryan Brooks', 'Chris Dalton'} | yes |
| detection stands | True | True | yes |
| answer says yes | contains 'yes' | Yes. The detection stands; the attributed notes disagree and both are shown. 1 spills result(s). | yes |
