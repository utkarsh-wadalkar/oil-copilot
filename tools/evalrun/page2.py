"""Turn a recorded run into the page-2 results table.

Reads ``answers.jsonl`` + ``manifest.json`` from an ``eval-runs`` folder and writes a Markdown
table of *what the copilot actually returned* — the question, the headline facts, the visual and
a verdict column the author ticks by hand after comparing with the expected answer. It never
invents a verdict and never copies an expected value into the answer column.

Usage::

    python tools/evalrun/page2.py --out eval-runs/final --write submission/page2-table.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def headline(answer: dict, question: str) -> str:
    """The most informative sentence the copilot itself produced, plus the key figures.

    A merged answer can carry calculations for a second tool call the user did not ask about
    (an incidental repair-cost total on a status question). Those are left out of the headline:
    the page-2 cell should say what the question asked, not everything the turn computed.
    """
    asked = (question or "").lower()
    parts: list[str] = []
    summary = (answer.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    for calculation in answer.get("calculations") or []:
        if calculation.get("kind") == "tool_trace":
            continue
        if calculation.get("spill_count") is not None and "spill" in asked:
            parts.append(f"{calculation['spill_count']} spills / {calculation.get('volume_bbl')} bbl")
        if calculation.get("downtime_days") is not None and ("down" in asked or "downtime" in asked):
            parts.append(f"{calculation['well_id']} {calculation['downtime_days']} d")
        if calculation.get("cost_usd") is not None and ("cost" in asked or "spend" in asked or "price" in asked):
            parts.append(f"{calculation['well_id']} USD {calculation['cost_usd']:,.0f}")
        if calculation.get("kind") == "proposed_spill":
            parts.append(f"{calculation.get('protocol')} due {str(calculation.get('due_at'))[:10]} {calculation.get('status')}")
        if calculation.get("kind") == "corrected_exclusion":
            parts.append(f"{calculation['well_id']} corrected {calculation.get('original_value')}->{calculation.get('corrected_value')}")
        if (calculation.get("threshold_c") is not None and calculation.get("delta_c") is not None
                and ("produc" in asked or "temperature" in asked or "warm" in asked or "status" in asked)):
            parts.append(f"{calculation.get('well_id')} {calculation.get('delta_c')} vs {calculation.get('threshold_c')} C")
    return " · ".join(dict.fromkeys(parts))[:400]


def cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def build(out: Path, limit: int = 0) -> str:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (out / "answers.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        records = records[:limit]
    warnings = sum(1 for r in records if ((r.get("response") or {}).get("answer") or {}).get("warnings"))
    errors = sum(1 for r in records if (r.get("response") or {}).get("error"))
    refusals = sum(
        1
        for r in records
        if "no earlier conversation" in (((r.get("response") or {}).get("answer") or {}).get("summary") or "")
        or "could not map" in (((r.get("response") or {}).get("answer") or {}).get("summary") or "")
    )
    lines = [
        f"Run: {manifest.get('generated_at')} · mode **{manifest.get('mode')}** · "
        f"user `{manifest.get('default_user') or manifest.get('user')}` · {len(records)} questions",
        f"{len(records) - warnings - errors - refusals} answered cleanly · {warnings} with a warning · "
        f"{refusals} refusal(s) · {errors} transport error(s)",
        "",
        "| # | Question (short) | Copilot answer (facts it returned) | Visual | Verdict |",
        "|---|---|---|---|---|",
    ]
    for record in records:
        payload = record.get("response") or {}
        if payload.get("error"):
            lines.append(f"| {record.get('id')} | {cell(record.get('question', '')[:70])} | ERROR {cell(str(payload.get('error')))} | — | |")
            continue
        answer = payload.get("answer") or {}
        visual = answer.get("visual") or {}
        kind = visual.get("kind") or "—"
        rows = len(visual.get("data") or [])
        user = record.get("user")
        prefix = f"[{user}] " if user else ""
        lines.append(
            f"| {record.get('id')} | {prefix}{cell((record.get('question') or '')[:70])} | "
            f"{cell(headline(answer, record.get('question') or ''))} | {kind} ({rows}) | |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="eval-runs/final")
    parser.add_argument("--write", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    text = build(Path(args.out), args.limit)
    if args.write:
        Path(args.write).write_text(text, encoding="utf-8")
        print(f"wrote {args.write}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
