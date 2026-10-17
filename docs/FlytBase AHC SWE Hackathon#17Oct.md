# Asset Intelligence Copilot

***FlytBase local challenge · Hacktoberfest 2026 Hack Day***

## The problem

An oil company runs an oil field with many wells spread over a large area. Every week someone inspects each well (often with a drone), crews repair whatever breaks, and regulators step in when oil is spilled. All of this produces a lot of data, in many forms: records, sensor readings, long manuals, repair reports and notes people write.

Today an operator wants to know *"Which wells in my area were down the longest this summer, and why?"* has to dig through several systems and documents. **Build an Asset Intelligence Copilot: a chat assistant that answers operators' plain-English questions about their wells, correctly and with evidence, using all of this data.**

We are not asking you to train models or analyse images. We are asking you to engineer the **agentic AI layer in the middle**: how the data is stored and found again, which tools the assistant can use, how it combines numbers with documents, and how it remembers what people tell it.

## Why this matters

Today the information about a well is scattered: inspection results in one system, repair records in another, rules in long manuals, and important context in people's notes and heads. To answer even a simple question, someone has to get access to each of these, pull the data together by hand, read through reports and then work out what it means. That takes hours or days, so a well that has quietly stopped producing oil or started leaking can go unnoticed for weeks.

Every day it stays down is lost oil, and every day a leak goes unfixed means more damage, bigger clean-up costs and fines. A copilot that anyone can simply ask, and that answers in seconds with the evidence, lets the team spot these problems early and fix them before they get worse.

## The domain, in plain words

- An **oil well** is a hole drilled deep into the ground. Oil is pumped up by a **pump jack**, the machine that nods up and down. At the surface the well is capped by a **wellhead**, the set of valves where the oil comes out.  
- **Is the well producing oil?** Nobody writes this down. You can tell from temperature: oil comes up warm, so a wellhead that is producing oil is much warmer than the air around it. A stopped one cools to air temperature. The exact rule ("how much warmer") is in the manual for each well type. A well stopped on purpose is "shut in".  
- **Downtime** is how long a well was not producing oil. Each well is inspected once a week, so every inspection that finds the well not producing oil counts as one week (7 days) of downtime. Two such inspections in a row mean 14 days. A missed inspection adds no downtime.  
- **Is oil leaking?** Inspections check for oil spilled on the ground around the well. A spill of 5 barrels or more must be reported to the regulator within 24 hours, or the company is fined. These rules are in the safety procedures (SOPs). People sometimes correct an inspection later ("that was a puddle, not oil"), and the correction wins.  
- **Repairs** happen whenever something breaks, and on a schedule. Each repair has a cost and keeps the well stopped for a while. (Downtime still comes from the weekly inspections, not from how long each repair took.)

## The data you get

Data for **200 wells over 4 years** in the sample (the test dataset adds more) (one inspection per well per week, about 40,000 inspections in the sample). The separate **Dataset Guide** explains every file and field.

| Source | What it contains |
| :---- | :---- |
| Well details | type, area, team, location, equipment, recorded status (may be out of date) |
| Inspections | weekly wellhead and air temperature, spills found (area and volume), photo references |
| Repair history | issue, fix, technician, time stopped, cost, plus some free-text repair reports |
| Regulator events | spill reports, violation notices, fines, site visits |
| Human notes | operator feedback, corrections, planned shutdowns |
| Manuals and SOPs | rules per well type, spill and compliance procedures |

The data is realistic and messy. Records go stale, a "spill" may later be corrected as a mud puddle, and the rule you need may be deep inside a manual.

## What you build

1. **A copilot chat UI with generative UI.** A chat interface where the user asks a question and the copilot answers in the chat with the right visual, shown inline: a status card for one well, a table for a list, a line chart for change over time, a bar chart for comparisons, a map for locations, a heatmap for two dimensions such as area × month. If the user names a visual ("show it as a table"), use it; otherwise the copilot picks the one that fits the answer. The answer is generated for the question, not chosen from fixed screens. We will show a basic prototype at kickoff. We do not provide photos; if your copilot needs images for an answer, use or generate any. We judge how the copilot uses them, not what is in them.  
2. **Answers grounded in the data.** Questions range from single facts to analysis across the whole field that combines several sources. Every answer cites the records and documents it used.  
3. **Memory at two levels.**  
   - **Shared knowledge about a well:** if one user says *"WELL-0007 is down for planned maintenance"*, other users asking about that well later get that context.  
   - **Private memory per user:** *"the three wells we discussed yesterday"* refers to *that* user's conversation, never someone else's. Users are listed in the data; a simple user picker in your UI is enough to switch between them.  
   - **Learning from feedback:** users correct wrong raw data ("that reading was wrong, the real value is…") and wrong AI analysis ("the spill was 5.4 bbl, not 4.5"). The copilot keeps the original, records who corrected it and why, and uses the correction in every later answer, for every user. Feedback can apply to one well or to every well of a type, and must be applied at that scope only.  
4. **Honesty about conflicts.** If what a user says contradicts the data, or two users disagree, the copilot says so instead of silently picking one.  
5. **A system that holds up on new data.** It must handle data and questions it has not seen (see below). A system tuned to the sample questions will break.

The Example Questions document has 18 questions with expected answers, so you can check your progress.

## How the day runs

- **Build** with the sample dataset and example questions.  
- **Final 2 hours:** we release a **test dataset** in the same format. Load it into your system. We then release the **final questions**. Run them through your copilot and record the answers.  
- **Submit** before the deadline.

## What to submit

We are evaluating **you, not the AI's output**. Use any tools, agents and models you like: open-source, open-weight or proprietary. What matters is how you designed the system and how well you understand it. Submit through **OrganizerHQ** (the event portal):

| Item | What it contains |
| :---- | :---- |
| Write-up: page 1, system design | Your architecture: how the data is stored, indexed and retrieved; the tools the copilot uses; how it combines numbers, documents and notes; how both memory levels work; how it handles conflicts and new data; models used and cost; what you would do next. |
| Write-up: page 2, results | Your copilot's answers to the final questions, with what worked, what didn't and why. |
| Video, 5 minutes at most | In your own voice: how you built the system, then one real use case, showing a question running end to end in your copilot UI. |
| Repository link | A public GitHub repository with an open-source license, needed for event approval. |

Keep to 2 pages max; writing them clearly is part of the challenge. The work must be your own.

## How we judge

1. **Shortlisting :** we check the answers on your results page against our expected answers and use the submitted video to understand the system that produced them.  
2. **Demos:** shortlisted individuals from the results will show demos in final showdown

# Dataset Guide

## Overview

The sample dataset describes a fictional oil field with **200 wells in 4 geographic areas** (blocks of land, 50 wells each), observed from **20 Oct 2022 to 16 Oct 2026**. 

| What | Count |
| :---- | :---- |
| Wells | 200 (50 per area) |
| Weekly inspections | about 39,600 (up to 209 per well) |
| Repair records | about 5,700 |
| Free-text repair reports | about 1,500 (one for every corrective repair) |
| Regulator events | 90 |
| Human notes | about 140 |

A few things make the data behave like a real field:

- Some wells were drilled during these 4 years, so their history starts later.  
- About 2% of weekly inspections were missed.  
- Older wells, and equipment that already failed, break more often.

In the final 2 hours of the event we release a **test dataset** in exactly the same format (more wells and more history). Your system has to load it alongside this one.

**WELL-0001** is the reference well. It has every kind of record and appears in many of the example questions.

All data is synthetic and created for this challenge. Manuals and SOPs are simplified, fictional documents, not real operating or legal guidance.

## Folder layout

All paths are inside the `sample-data/` folder.

**Fleet-wide files (`fleet/`)**

| Path | What it contains |
| :---- | :---- |
| `fleet/areas.json` | Geographic areas (blocks of land), their teams, and which wells belong where |
| `fleet/users.json` | People who use the copilot, with their roles |
| `fleet/well-types/T200.md` | Operating manual for T200 wells |
| `fleet/well-types/T350.md` | Operating manual for T350 wells |
| `fleet/sops/spill-response-sop.md` | Spill classes and protocols SR-01 to SR-04 |
| `fleet/sops/regulatory-compliance-sop.md` | Compliance protocols RC-01 to RC-05 |
| `fleet/sops/field-work-sop.md` | Crew safety and maintenance protocols WS-01 to WS-07 |

**One folder per well (`assets/WELL-0001/` … `assets/WELL-0200/`)**

| File | What it contains |
| :---- | :---- |
| `metadata.json` | Well details and equipment |
| `inspections.jsonl` | One line per weekly inspection |
| `maintenance.jsonl` | One line per maintenance job |
| `maintenance-reports/*.md` | A free-text report for every corrective repair: what happened, root cause, safety steps, work done, tests, clean-up, parts and cost, and a compliance check |
| `regulatory-events.jsonl` | Agency reports, notices and fines |
| `context.jsonl` | Human notes, feedback and corrections |

`.jsonl` files hold one JSON object per line.

Every record in `assets/` also carries the `asset_id` of its well.

## Areas (fleet/areas.json)

A **geographic area** is a block of land in the oil field, for example SW-23 (Southwest Block 23). Each area belongs to one production team and lists the wells in it.

{

  "areas": \[

    {

      "area\_id": "SW-23",

      "name": "Southwest Block 23",

      "team\_id": "TEAM-SW",

      "center": { "lat": 31.842, "lon": \-102.512 },

      "asset\_ids": \["WELL-0001", "..."\]

    }

  \],

  "teams": \[

    {

      "team\_id": "TEAM-SW",

      "name": "Southwest Production",

      "lead\_user\_id": "U-101"

    }

  \]

}

## Users (fleet/users.json)

| Field | Meaning |
| :---- | :---- |
| `user_id` | Unique ID, for example `U-201` |
| `name` | Full name |
| `role` | `production_supervisor`, `field_operator`, `field_inspector`, `maintenance_lead`, `maintenance_technician` or `hse_officer` |
| `team_id` | Team the person belongs to |

## Well details (assets/WELL-XXXX/metadata.json)

| Field | Meaning |
| :---- | :---- |
| `asset_id`, `name` | Unique ID and display name |
| `asset_category` | Always `oil_well` |
| `well_type` | `T200` or `T350`; selects the manual and its rules |
| `area_id`, `team_id`, `in_charge_user_id` | Ownership |
| `location` | `lat`, `lon` |
| `installed_on` | Installation date |
| `equipment[]` | `equipment_id`, `kind` (`wellhead`, `pump_jack`, `rod_string`, `downhole_pump`, `flowline`, `separator`), `model` |
| `last_inspection` | ID, time and inspector of the latest inspection |
| `recorded_status` | `active` or `down` in the system of record, refreshed at the end of each month. **Can be out of date**; the inspections are the truth. |

## Inspections (assets/WELL-XXXX/inspections.jsonl)

| Field | Unit / values | Meaning |
| :---- | :---- | :---- |
| `inspection_id` | `INS-<well>-<n>` | Unique ID |
| `inspected_at` | ISO 8601 UTC | Time of the inspection (also the spill *discovery* time) |
| `inspector_user_id`, `method` | `drone` / `manual` | Who and how |
| `ambient_temp_c` | °C | Air temperature |
| `wellhead_temp_c` | °C | Thermal reading of the wellhead |
| `spill_detected` | bool | A spill was detected on the pad |
| `spill_area_pct` | % of pad area | Null when no spill |
| `spill_est_volume_bbl` | barrels | Crude volume estimated by the AI analysis of the inspection images; null when no spill |
| `evidence_images[]` | paths | Image references (files not supplied) |
| `notes` | text | Inspector's remark |

**Producing oil or not** is never stored. Derive it from the well-type manual: a well is producing oil when `wellhead_temp_c - ambient_temp_c` is at least the threshold for its type. **Downtime** is how long a well was not producing oil. Each well is inspected once a week, so every inspection in a period that finds the well not producing oil counts as **7 days** of downtime. A missed inspection adds no downtime. Do not use `maintenance.downtime_hours` for this; that field is how long one repair job took.

## Repairs (assets/WELL-XXXX/maintenance.jsonl)

| Field | Meaning |
| :---- | :---- |
| `maintenance_id` | `MNT-<well>-<n>`, in date order |
| `started_at`, `completed_at` | ISO 8601 UTC. For repairs still in progress, `completed_at` is the planned end and can be after today. |
| `maintenance_type` | `scheduled` or `corrective` |
| `equipment_kind` | Equipment worked on |
| `issue`, `action_taken` | What was wrong and what was done |
| `technician_user_id`, `contractor` | Who did it |
| `downtime_hours` | Hours the well was stopped for this job |
| `cost_usd` | `labor`, `parts`, `total` |
| `triggered_by_inspection_id` | Inspection that led to the job, if any |
| `report_file` | Path of a free-text report, if any. File names vary, so always follow this field. |

## Regulator events (assets/WELL-XXXX/regulatory-events.jsonl)

| Field | Meaning |
| :---- | :---- |
| `event_id`, `date` | ID and date |
| `agency` | `State Oil & Gas Commission` or `Regional Environmental Protection Office` |
| `event_type` | `spill_report_filed`, `notice_of_violation`, `site_inspection`, `nov_response_filed` |
| `protocol_id` | SOP protocol involved (e.g. `SR-01`) |
| `related_inspection_id` | Inspection that discovered the spill |
| `hours_to_report` | Hours from discovery to the report being filed |
| `detail` | Short description of the event |
| `fine_usd`, `status` | Fine amount; `open` or `closed` |

## Human notes (assets/WELL-XXXX/context.jsonl)

| Field | Meaning |
| :---- | :---- |
| `note_id`, `created_at`, `author_user_id` | Who wrote it and when |
| `note_type` | `operator_feedback`, `operator_note`, `correction` |
| `inspection_id` | Only on `correction` notes: the inspection being corrected |
| `text` | The note itself |
| `valid_from`, `valid_to` | Period the note applies to (`valid_to` may be null) |

A `correction` overrides the detection of the inspection named in its `inspection_id`, for example a "spill" that was really rainwater. Notes exist on many wells, not only WELL-0001. Feedback your copilot collects at run time belongs to the same kind of knowledge.

## Things to watch for

- On a hot day an idle wellhead can read over 50 °C. Only the difference from ambient matters.  
- The latest record can disagree with `recorded_status` or with a recent human note.  
- Some facts appear only in free-text reports, such as when containment actually happened.  
- Thresholds and deadlines live in the manuals and SOPs, not in the data files.  
- People can disagree in their notes about the same inspection; neither note is a formal correction.

# **Example Scenarios**

These are 18 example questions with the answers your copilot should give on the sample dataset (200 wells). "Today" is **17 Oct 2026**, and "right now" means each well's latest inspection. Periods such as "last 4 months" end today and are compared by date. A repair belongs to a period by its start date. The final questions, released with the test dataset in the last 2 hours, follow the same style.

Run each scenario on the original sample data, unless it says it follows another one.

## Before you start: how the data fits together

The data is more than the record files. The **well-type manuals** and the **SOPs** in `fleet/` are part of it: they hold the rules that decide most answers, such as when a well counts as producing oil and which deadlines apply to a spill. How downtime is counted is in the Dataset Guide. Your system has to find and apply those rules; we do not repeat them here.

Everything starts from a well. Its type decides which manual applies, and its weekly inspections are the main record of what happened. When an inspection finds a problem, the follow-up records point back to that inspection's ID: the repair, its free-text report, and, for larger spills, the regulator events. Some facts live only in the reports. To judge whether something was handled correctly, compare these records with the SOPs. Human notes explain why the data looks the way it does, and the recorded status can be out of date.

## Choosing the visual

When a question names a visual (a card, table, chart, map or heatmap), the copilot shows that visual. When it doesn't, the copilot picks the one that fits the answer:

| The answer is about… | Show |
| :---- | :---- |
| A list of wells, events or repairs | A table |
| A value changing over time | A line chart |
| Comparing a few wells or areas | A bar chart |
| Where things are | A map |
| Two dimensions at once, such as area × month | A heatmap |

## How we check answers

- **Facts:** numbers, names, IDs and dates must match.  
- **Evidence:** the answer cites the records and documents it used.  
- **Visual:** the visual the question asks for, or a fitting one if it doesn't ask.

Wells are referred to by their ID (for example **WELL-0001**). Geographic areas, teams and people are referred to by name (for example **Northeast Block 7**).

---

# Part A: One user

**What these questions test:**

- **A1:** the copilot answers any kind of question about the data (one well, a well over time, an area, many wells, and records combined with documents) correctly, with evidence and the right visual.  
- **A2:** the copilot remembers the user's past conversations, and it learns from the user's feedback: corrections to raw data, corrections to the AI's analysis, and rules for a whole well type. It applies each one at the right scope.

## A1. Asking about the data

**Q1. Is WELL-0001 producing oil right now? When was it last inspected, and by whom?**

- Expected: **No, it is not producing oil.**  
  - Latest inspection INS-0001-0203, on 15 Oct 2026, by drone, by Ryan Brooks.  
  - The wellhead was only 3.2 °C warmer than the air, below the T200 limit.  
  - Reason: note CTX-0001-003 by Jake Morales, a planned shut-in from 7 Oct for rod string replacement, expected back around 20 Oct. It is not yet in the maintenance system.  
  - The recorded status still says `active`, which is out of date.

**Q2. Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.**

- Expected (table): four T200 wells, all last inspected on 15 Oct 2026\. Two have no recorded reason.


| Well | Wellhead above air | Recorded status | Reason |
| :---- | :---- | :---- | :---- |
| WELL-0164 | 4.1 °C | active (out of date) | **No recorded reason.** The inspector noted "Pump jack not moving." |
| WELL-0170 | 2.9 °C | down | Repair MNT-0170-031, pump jack walking beam bearing wear, started 19 Sep, still open |
| WELL-0172 | 5.7 °C | active (out of date) | Repair MNT-0172-028, flowline pinhole leak, started 3 Oct, still open |
| WELL-0175 | 0.4 °C | active (out of date) | **No recorded reason** |


  Where nothing explains the stop, the copilot says so and suggests a check. It must not invent a cause.

**Q3. Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil.**

- Expected (line chart): 13 readings (23 Jul to 15 Oct 2026). Not producing oil on 8 Oct and 15 Oct.

**Q4. How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table.**

- Expected (table): **6 spills, 15.1 barrels.**  
  - There were 7 detections. INS-0001-0070 (7 Mar 2024\) was corrected as rainwater (CTX-0001-001) and does not count.  
  - Spills: 16 Mar 2023 (0.5 bbl), 27 Apr 2023 (2.6), 28 Sep 2023 (3.3), 19 Oct 2023 (0.3), 11 Jun 2026 (6.8), 1 Oct 2026 (1.6).

**Q5. How many days was WELL-0001 down in 2025?**

- Expected (a short answer with its evidence; no visual needed): **21 days**, from three weekly inspections where it was not producing oil.  
  - **24 Jul 2025:** the wellhead read 51.6 °C, which looks hot, but the air was 43.1 °C. That is only 8.5 °C warmer, so the well was not producing oil. Cause: the prime mover tripped (MNT-0001-021).  
  - **16 and 23 Oct 2025:** stuffing box packing leak (MNT-0001-023).

**Q6. Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.**

- Window: 16 Jun to 16 Oct 2026\.  
- Expected (bar chart): **WELL-0121: 49 days** (T200), **WELL-0138: 42 days** (T350), **WELL-0107: 42 days** (T350). Next is WELL-0119 at 28\.

**Q7. Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.**

- Expected (map with 4 pins):


| Well | Date | Barrels | Location (lat, lon) |
| :---- | :---- | :---- | :---- |
| WELL-0151 | 24 Sep 2026 | 4.5 | 32.12246, −102.18445 |
| WELL-0165 | 30 Jul 2026 | 1.2 | 32.15665, −102.14522 |
| WELL-0175 | 30 Jul 2026 | 3.9 | 32.18020, −102.14790 |
| WELL-0186 | 23 Jul 2026 | 0.6 | 32.17552, −102.17775 |

**Q8. Show a heatmap of 2026 spills by geographic area and month.**

- Expected (heatmap of areas × Jan–Oct, with corrected detections removed):


| Area | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Total |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| Southwest Block 23 | 4 | 3 | 3 | 6 | 3 | 4 | 4 | 3 | 3 | 2 | 35 |
| Southwest Block 24 | 7 | 4 | 5 | 6 | 5 | 5 | 3 | 1 | 5 | 2 | **43** |
| Northeast Block 7 | 5 | 3 | 2 | 4 | 6 | 6 | 2 | 4 | 4 | 1 | 37 |
| Northeast Block 8 | 4 | 4 | 4 | 3 | 2 | 4 | 4 | 0 | 1 | 0 | 26 |

**Q9. Which rules has WELL-0001 broken in the last 12 months, and what is still open?**

- Expected (table or list): four breaches, all from the 11 Jun 2026 spill of 6.8 bbl. USD 5,000 in fines, still open.  
    
  - **SR-01:** reported after 41 hours (REG-0001-001), against a 24-hour limit. This led to notice of violation REG-0001-002 with a USD 5,000 fine, still open.  
  - **SR-02:** contained after about 7 hours, against a 4-hour limit. This is found only in the June repair report.  
  - **SR-03:** cleanup verification was due by 10 Aug 2026 and is still open (REG-0001-003).  
  - **RC-04:** the notice needed a response by 30 Jul 2026, and none is recorded.


  Also still pending (open actions, not counted as breaches because the deadlines have not passed or the work is still under way):


  - A root-cause analysis is due on the flowline: 3 corrective repairs in the last 12 months (MNT-0001-028, \-029, \-032). The report for the October repair (MNT-0001-032) marks it as "Action required".  
  - The planned shut-in from 7 Oct is not yet recorded in the maintenance system, which the T200 manual requires before work starts (note CTX-0001-003).


  The yearly flowline test (RC-02) was done on 7 Mar 2026, so that rule was met.

**Q10. In Southwest Block 24, which spills in the last 90 days were not contained within the SOP time limit?**

- Expected (table): 2 spills. The limit is 4 hours, and the containment time exists only inside the repair reports.  
  - WELL-0082: contained after about 7.1 hours (report MNT-0082-028, inspection INS-0082-0198).  
  - WELL-0100: contained after about 8.1 hours (report MNT-0100-034, inspection INS-0100-0196).

## A2. Memory and feedback from one user

**Q11. Remembering past conversations**

- Day 1, Michael Turner asks Q6.  
- Day 2, Michael Turner, in a new chat: *"For the three wells we discussed yesterday, what have repairs cost this year?"*  
- Expected: WELL-0121: USD 25,794 · WELL-0138: USD 46,942 · WELL-0107: USD 5,176.

**Q12. Correcting wrong raw data**

- Michael Turner: *"The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that inspection was faulty; the field crew re-measured the wellhead at 41.0 °C."*  
- Expected:  
  - The copilot records the correction against inspection INS-0164-0205. It keeps the original value (24.0 °C) and notes who corrected it and why.  
  - With 41.0 °C against 19.9 °C air (21.1 °C warmer, above the T200 limit), WELL-0164 **is producing oil**.  
  - The copilot also points out that the same inspection has the note "Pump jack not moving." (Tyler Hughes), which disagrees with the correction, and asks Michael Turner to confirm.  
- Then Michael Turner asks Q2 again.  
  - Expected: **three wells** (WELL-0170, WELL-0172, WELL-0175). WELL-0164 is no longer listed, and the answer says why.

**Q13. Correcting the AI's analysis**

- Michael Turner: *"The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. The field crew measured 5.4 bbl."*  
- Expected:  
  - The copilot records the corrected volume against inspection INS-0151-0201, keeping the AI's estimate for reference.  
  - At 5.4 bbl the spill is **reportable** under the Spill Response SOP. A written notice was due within 24 hours of the 24 Sep 15:30 inspection, and **none is recorded**. The copilot flags this as a possible SR-01 breach.  
  - Repair report MNT-0151-025 classed the spill as "moderate" and listed no reporting duty. That was based on the old estimate and no longer holds. (The same report already shows containment took about 6.4 hours, an SR-02 breach.)  
  - Because it is now a reportable spill, agency verification of the clean-up (SR-03) is also due within 60 days, by 23 Nov 2026\.

**Q14. A rule for a whole well type**

- Michael Turner first asks: *"Which wells in Northeast Block 7 need a root-cause analysis on their pump jack?"*  
  - Expected: **WELL-0108, WELL-0121 and WELL-0138**, with 3 corrective pump jack repairs each in the last 12 months (T200 manual section 10; the T350 manual refers to it).  
- Michael Turner: *"Note for all T350 wells: our team now wants a pump jack root-cause analysis after 2 repairs, not 3."* Then, in a new chat, he asks the same question again.  
  - Expected: **WELL-0108, WELL-0120, WELL-0121 and WELL-0138.**  
    - WELL-0120 is a T350 well with 2 repairs, so it is now added.  
    - WELL-0102 also has 2 repairs, but it is a T200 well, so it must **not** be added.  
    - The answer says this follows Michael Turner's rule, not the manual.

---

# Part B: Several users

Part B adds more people:

| Person | Role | Team |
| :---- | :---- | :---- |
| Michael Turner | Production supervisor | Northeast Production |
| Tyler Hughes | Field operator | Northeast Production |
| Jessica Reed | Field inspector | Northeast Production |
| Jake Morales | Field operator | Southwest Production |
| Laura Simmons | HSE officer | Health, Safety & Environment |

**What these questions test:** facts and corrections that one user gives reach everyone else; each user's private conversations stay private; and when people disagree with each other or with the data, the copilot shows the conflict instead of quietly picking a side.

**Q15. A correction reaches other users** (follows Q12 and Q13)

- Jessica Reed, in her own chat: *"Is WELL-0164 producing oil right now?"*  
  - Expected: **yes**, based on the corrected reading of 41.0 °C. The answer says the 15 Oct value was corrected by Michael Turner, and mentions the inspector's "Pump jack not moving." note that disagrees with it.  
- Laura Simmons: *"Which spills in Northeast Block 8 in the last 90 days needed a report to the regulator?"*  
  - Expected: **WELL-0151**, because its volume was corrected to 5.4 bbl. No written notice is on record, so it is flagged as overdue. No other spill in that period reached 5 bbl.

**Q16. Shared knowledge, private memory**

- Jake Morales: *"FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover."*  
- Later, Michael Turner, in a new chat: *"Is any downtime planned for WELL-0007?"*  
  - Expected: yes, from 17 Oct for about 10 days, according to Jake Morales.  
- Then Jessica Reed: *"For the three wells we discussed yesterday, what have repairs cost this year?"* (This follows Q11.)  
  - Expected: the copilot says it has no such earlier conversation with Jessica Reed. It must **not** use Michael Turner's history from Q11.

**Q17. People disagree with the data**

- Michael Turner: *"WELL-0175 has been shut in for planned work since 14 Oct."*  
- Later, Tyler Hughes: *"WELL-0175 is running fine."*  
  - Expected: the copilot tells Tyler Hughes that the 15 Oct inspection (by Jessica Reed) shows the wellhead only 0.4 °C above the air, so the well is not producing oil. That matches Michael Turner's note, not Tyler Hughes's claim. The copilot keeps both statements on record, marks Tyler Hughes's as unconfirmed, and asks for confirmation.  
- Then Jake Morales: *"WELL-0001 is back online since 14 Oct."*  
  - Expected: the copilot points out that the 15 Oct inspection shows WELL-0001 not producing oil, and that note CTX-0001-003 expects a return around 20 Oct. It records the claim as unconfirmed.

**Q18. People disagree about the AI's analysis**

- Any user: *"Was the 20 Aug spill at WELL-0101 real oil?"*  
- Expected:  
  - The AI flagged a 1.0 bbl spill at inspection INS-0101-0197 ("Oil sheen around cellar").  
  - Two notes disagree: Ryan Brooks thought it produced water (CTX-0101-002), but Chris Dalton (HSE) sampled the stain and confirmed crude (CTX-0101-003).  
  - Neither note is a formal correction, and a spill repair (MNT-0101-029) was done, so the detection stands.  
  - The copilot answers **yes** but shows the disagreement and both sources.

# Hackathon Prerequisites & Resources Guide

To work through the hackathon challenge, you'll need three things ready beforehand:

- **The sample dataset:** a fictional oil field with 200 wells and 4 years of history, in the challenge repository. You build your copilot on it.  
- **A coding setup:** for example Claude Code, OpenCode, Codex, Cursor, or any other coding agent you're comfortable using.  
- **Model access:** through hosted APIs, free model providers, a local model, or any other setup that works for you. You need it twice: for your coding agent, and for the copilot you build, which calls a model to answer questions.

Please have all three set up and tested before the hackathon so you can start building right away.

# Sample Dataset

Repository: [`https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset`](https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset)

The repository holds the challenge documents and the sample dataset you build on. There is no starter app: you choose your own language, framework, storage and models, and build the copilot from scratch.

## Requirements

- Git, and access to the repository above  
- About 30 MB of free disk space  
- Any language or stack you like

## 1\. Get it

Clone the repository and go into its folder:

`git clone https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset`

`cd flytbase-ahc-swe-asset-intelligence-dataset`

List the folder. You should see the challenge documents and a `sample-data` folder with `fleet` and `assets` inside it.

## 2\. What's inside

| Path | What it is |
| :---- | :---- |
| `01-problem-statement.md` | The challenge, what to build and how we judge |
| `02-dataset-guide.md` | Every file and field in the dataset |
| `03-evaluation-queries.md` | Example questions with expected answers, to check your progress |
| `04-prerequisites.md` | This guide |
| `sample-data/fleet/` | Areas, teams and people, well-type manuals, and operating procedures (SOPs) |
| `sample-data/assets/` | One folder per well, WELL-0001 to WELL-0200: details, weekly inspections, maintenance jobs, free-text repair reports, regulator events and human notes |

Read `02-dataset-guide.md` before you start.

# Coding Setup Guide

If you already use Claude Code, OpenCode, Codex, Cursor or another coding agent with your own model access or subscription, keep using that setup.

If you don't have one yet, there are many workable combinations: a coding agent paired with a free model provider or gateway such as OpenRouter, another provider with a free tier, or a local model. Pick whatever works best for you.

Below are two things to help: Gemma 4, a free model you can use in several ways, and an example setup with Claude Code and OpenRouter. You don't need either. Any coding agent and any model work, as long as you have tested them beforehand.

# Free Model Option: Gemma 4

Gemma 4 is Google's open model. It is free and supports tool calling. You can use it in three ways:

| Where you get it | In the copilot you build | With Claude Code |
| :---- | :---- | :---- |
| Google AI Studio | Yes | No |
| OpenRouter | Yes | Yes |
| Your own laptop, with Ollama | Yes | Yes |

## 1\. Google AI Studio

Gemma 4 is free of charge on Google's Gemini API.

1. Create an API key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).  
2. Install the SDK: `pip install google-genai`  
3. Make a test call:

from google import genai

client \= genai.Client(api\_key="YOUR-KEY-HERE")

response \= client.models.generate\_content(model="gemma-4-26b-a4b-it", contents="Say hello.")

print(response.text)

Model IDs: `gemma-4-26b-a4b-it` (faster) and `gemma-4-31b-it` (stronger).

Good to know:

- Your exact rate limits are shown in AI Studio. There is no paid tier for Gemma, so you can't buy higher limits.  
- Google may use free-tier prompts to improve its products.  
- Use it in your copilot, or with coding agents that support Gemini directly. It does not work with Claude Code; for that, use OpenRouter or Ollama.

## 2\. OpenRouter

Model IDs: `google/gemma-4-31b-it:free` and `google/gemma-4-26b-a4b-it:free`.

Use them in your copilot through OpenRouter's API, or as the model behind Claude Code. The example setup below shows Claude Code with Gemma 4 on OpenRouter, and explains the free limits. Both models are served by a single provider, so if they stop responding, switch to Ollama or another free model.

## 3\. Your own laptop, with Ollama

No account, no key and no rate limits, but it needs a capable machine and runs slower than the hosted options.

**Step 1\. Install Ollama** from [ollama.com/download](https://ollama.com/download).

**Step 2\. Pick the size that fits your machine.**

| Model | Download | Rough guide |
| :---- | :---- | :---- |
| `gemma4:e2b` | about 5–8 GB | Laptops with 8 GB of memory |
| `gemma4:e4b` | about 7–10 GB | Most laptops with 16 GB of memory |
| `gemma4:12b` | about 8 GB | Laptops with 16 GB or more |
| `gemma4:26b` | about 16–19 GB | Machines with 32 GB or more. Usually much faster than 31b |
| `gemma4:31b` | about 20 GB | Machines with 48 GB or more for comfortable use |

These sizes are for a short context. A 64K context (step 3\) needs several GB more, so if memory is tight, use the next size down.

**Step 3\. Raise the context length.** Ollama starts with only 4K of context on most laptops (any machine with less than 24 GB of graphics memory). That is too small for a coding agent or for your copilot's prompts, and longer text is silently cut off. Move the context length slider in the Ollama app's settings to 64K, or start the server with:

OLLAMA\_CONTEXT\_LENGTH=64000 ollama serve

Your copilot needs this too: the API below can't change it per request.

**Step 4\. Download and test the model:**

ollama pull gemma4:e4b

ollama run gemma4:e4b "Say hello."

Run `ollama ps` to check the model fits in memory.

**Use it in your copilot** through Ollama's OpenAI-compatible API at `http://localhost:11434/v1/`. Ollama ignores the API key, but the client needs some value:

from openai import OpenAI

client \= OpenAI(base\_url="http\://localhost:11434/v1/", api\_key="ollama")

response \= client.chat.completions.create(model="gemma4:e4b", messages=\[{"role": "user", "content": "Say hello."}\])

print(response.choices\[0\].message.content)

**Use it with Claude Code:** run `ollama launch claude` and pick the Gemma 4 model, or follow [Ollama's Claude Code guide](https://docs.ollama.com/integrations/claude-code). Raise the context length first (step 3). Small local models are much weaker at multi-step coding than hosted ones, so try a real task before the event.

# Example: Claude Code \+ OpenRouter \+ Gemma 4

Claude Code is the coding agent here, and OpenRouter provides the model it uses. The same idea applies to other compatible coding agents and model providers.

For this example, have these ready:

- Claude Code installed on your machine ([install guide](https://code.claude.com/docs/en/setup))  
- An OpenRouter account  
- A terminal you're comfortable using

## 1\. Create an OpenRouter account and API key

Go to [openrouter.ai](https://openrouter.ai/) and create an account. Free models don't need credits, but have tight daily limits (see step 2).

Once you're logged in:

1. Open the [API Keys page](https://openrouter.ai/settings/keys).  
2. Create a new API key.  
3. Copy the generated key. It should look like `sk-or-v1-...`

Keep it private: treat the API key like a password. Don't share it or commit it to your codebase.

## 2\. Choose a free model

For this example, we'll use Gemma 4: `google/gemma-4-31b-it:free`

You can browse the currently available free text models here: [OpenRouter \- Free Models](https://openrouter.ai/models?max_price=0&output_modalities=text).

Free-model availability changes. Pick a model that supports tool use and copy its model ID. You can switch later if one is rate-limited or doesn't work well with your coding agent. Backups that worked when we wrote this: `google/gemma-4-26b-a4b-it:free` (Gemma 4, faster), `nvidia/nemotron-3-super-120b-a12b:free` and `poolside/laguna-s-2.1:free`.

**Know the free limits.** Free models allow about 20 requests per minute and **50 requests per day** on an account that has never bought credits. A coding agent makes many requests for one task, so 50 can run out within the first hour. If your copilot also uses OpenRouter free models, it shares the same daily limit. Buying at least \$10 of credits once raises the free limit to 1,000 requests per day. Plan for this before the event.

## 3\. Point Claude Code to OpenRouter

Run these in the same terminal session where you'll use Claude Code.

macOS / Linux / WSL:

export ANTHROPIC\_BASE\_URL="https\://openrouter.ai/api"

export ANTHROPIC\_AUTH\_TOKEN="\<your-api-key\>"

export ANTHROPIC\_API\_KEY=""

export ANTHROPIC\_MODEL="google/gemma-4-31b-it:free"

export ANTHROPIC\_DEFAULT\_OPUS\_MODEL="google/gemma-4-31b-it:free"

export ANTHROPIC\_DEFAULT\_SONNET\_MODEL="google/gemma-4-31b-it:free"

export ANTHROPIC\_DEFAULT\_HAIKU\_MODEL="google/gemma-4-31b-it:free"

export CLAUDE\_CODE\_SUBAGENT\_MODEL="google/gemma-4-31b-it:free"

Windows PowerShell:

\$env:ANTHROPIC\_BASE\_URL="https\://openrouter.ai/api"

\$env:ANTHROPIC\_AUTH\_TOKEN="\<your-api-key\>"

\$env:ANTHROPIC\_API\_KEY=""

\$env:ANTHROPIC\_MODEL="google/gemma-4-31b-it:free"

\$env:ANTHROPIC\_DEFAULT\_OPUS\_MODEL="google/gemma-4-31b-it:free"

\$env:ANTHROPIC\_DEFAULT\_SONNET\_MODEL="google/gemma-4-31b-it:free"

\$env:ANTHROPIC\_DEFAULT\_HAIKU\_MODEL="google/gemma-4-31b-it:free"

\$env:CLAUDE\_CODE\_SUBAGENT\_MODEL="google/gemma-4-31b-it:free"

Replace `<your-api-key>` with your OpenRouter key. `ANTHROPIC_API_KEY` must be set to an empty value, so Claude Code uses your OpenRouter key instead.

Put the same model ID in all five model lines. Claude Code uses different models for background work and helper agents, and any line you leave out sends those requests to paid Claude models, which fail on a free account. If you picked another model, change all five lines.

Note: these environment variables only apply to the current terminal session. If you open a new terminal, set them again, or add them to your shell profile so they stick.

## 4\. Verify that the setup works

Run a tiny one-off request:

claude \-p "Reply with exactly: OK"

If the setup works, you'll get `OK` back.

## 5\. Confirm the selected model

Start Claude Code with `claude`, then run `/model` to confirm the model you intended is selected. Run `/status` too: it should show `ANTHROPIC_AUTH_TOKEN` as the auth token and `https://openrouter.ai/api` as the base URL. If it shows a Claude account login or `ANTHROPIC_API_KEY` instead, run `/logout`, set the variables again and restart Claude Code. An earlier Claude account login can override them.

# Test Your Setup Before the Hackathon

Don't stop at the OK test. Try a few small coding tasks and make sure the setup is usable for you. A good test: ask your coding agent to read `dataset-guide` and ask few questions

Free models can be rate-limited, temporarily unavailable, slower under load, or less compatible with a particular coding agent. Claude Code is built for Anthropic models and may not work fully with others. If one isn't working reliably:

- Open the free-model catalogue.  
- Pick another free model.  
- Update your selected model.  
- Run the verification again.  
- Try a small coding task.

If you see `No endpoints found matching your data policy`, check your [OpenRouter privacy settings](https://openrouter.ai/settings/privacy): some free models need you to allow free endpoints there.

Recommendation: have one or two backup model IDs or an alternative setup ready before the event.

Different tools have different configuration steps. If you choose another combination, follow that tool's documentation and test the complete flow beforehand. OpenRouter also documents integrations for [Claude Code](https://openrouter.ai/docs/cookbook/coding-agents/claude-code-integration) and [Codex CLI](https://openrouter.ai/docs/cookbook/coding-agents/codex-cli).

## Sources \- 

1. PPT \- [https\://docs.google.com/presentation/d/1afk3M1hwKaaAjXcDGNe5Y9cBOv-oXjhxqsVhNpMeiRs/edit?usp=sharing](https://docs.google.com/presentation/d/1afk3M1hwKaaAjXcDGNe5Y9cBOv-oXjhxqsVhNpMeiRs/edit?usp=sharing)  
2. DataSet \- [https\://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset](https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset)  
3. Gen UI \-   
   1. [https\://www\.openui.com/blog/oui-1](https://www.openui.com/blog/oui-1)  
   2. [https\://arxiv.org/pdf/2610.11123](https://arxiv.org/pdf/2610.11123)  
   3. [https\://www\.youtube.com/watch?v=hCMrEfPG2Yg\&t=1s](https://www.youtube.com/watch?v=hCMrEfPG2Yg&t=1s)  
   4. https\://youtu.be/UsMDkEsR-ok?si=3oeeUq9jh8R08fSU  
4. Context Engineering \-   
   1. [https\://arxiv.org/pdf/2606.18829](https://arxiv.org/pdf/2606.18829)  
   2. https\://www\.youtube.com/watch?v=esY99nYXxR4  
5. Physical AI \-   
   1. [https\://bostondynamics.com/case-studies/meet-chevrons-new-energy-watchdog/](https://bostondynamics.com/case-studies/meet-chevrons-new-energy-watchdog/)  
   2. [https\://energiminas.com/2025/06/17/pisco-pluspetrol-culmina-con-exito-prueba-de-robot-autonomo-para-monitoreo-y-seguridad-en-sus-operaciones/](https://energiminas.com/2025/06/17/pisco-pluspetrol-culmina-con-exito-prueba-de-robot-autonomo-para-monitoreo-y-seguridad-en-sus-operaciones/)

