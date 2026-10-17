"""Replay the released final question set through a running copilot and record the answers.

The sample-set harness (``run.py ask``) opens one conversation per question. Final questions
follow the same style as the sample set, which includes multi-turn scenarios: a correction is
prepared, confirmed, then asked about again by another user. This runner keeps a named
conversation per thread and can confirm a pending draft between turns, so those flows are
reproduced faithfully instead of being judged from a one-shot answer.

Input (JSON) — a list of turns::

    [
      {"id": "F1", "user": "U-201", "question": "Is WELL-0001 producing oil right now?"},
      {"id": "F2", "user": "U-201", "thread": "t1", "question": "Which wells ...", "note": "setup"},
      {"id": "F3", "user": "U-201", "thread": "t1", "confirm": true},
      {"id": "F4", "user": "U-202", "thread": "t2", "question": "Is WELL-0164 producing oil right now?"}
    ]

``thread`` defaults to the question id, so omit it for one-shot questions. ``confirm`` sends the
pending draft from the previous turn in the same thread for confirmation. ``user`` switches the
dataset user; a new user always gets a new thread even if the key repeats.

A markdown question document in the dataset's ``**Q1. ...**`` format is also accepted; each
question becomes its own thread.

Usage::

    python tools/evalrun/final.py --base-url http://127.0.0.1:8000 \
        --turns final-questions.json --out eval-runs/final

Writes manifest.json, answers.jsonl and answers.md. It never edits a question or an expected
answer; it only records what the copilot actually returned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import _git_head, parse_questions, render_answers  # noqa: E402


def load_turns(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("turns") or data.get("questions") or []
        return [dict(item) for item in data]
    questions = parse_questions(path)
    return [{"id": q.id, "question": q.text, "expected": q.expected} for q in questions]


class Runner:
    def __init__(self, base_url: str, default_user: str):
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=300)
        self.default_user = default_user
        self.threads: dict[tuple[str, str], str] = {}
        self.last_draft: dict[tuple[str, str], str] = {}

    def _conversation(self, user: str, key: str, title: str) -> str:
        slot = (user, key)
        if slot not in self.threads:
            response = self.client.post("/conversations", json={"title": title[:60]},
                                        headers={"X-User-ID": user})
            response.raise_for_status()
            self.threads[slot] = response.json()["id"]
        return self.threads[slot]

    def ask(self, user: str, key: str, question: str) -> dict:
        conversation = self._conversation(user, key, question)
        body = {"content": question,
                "client_message_id": f"fin-{hashlib.sha256(question.encode()).hexdigest()[:16]}"}
        response = self.client.post(f"/conversations/{conversation}/messages", json=body,
                                    headers={"X-User-ID": user})
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "detail": response.text[:800]}
        payload = response.json()
        draft = payload.get("draft") or {}
        if draft.get("id") and draft.get("status") == "pending":
            self.last_draft[(user, key)] = draft["id"]
        return payload

    def confirm(self, user: str, key: str) -> dict:
        draft_id = self.last_draft.get((user, key))
        if not draft_id:
            return {"error": "no pending draft in this thread",
                    "detail": "nothing was prepared by the previous turn"}
        response = self.client.post(f"/feedback/{draft_id}/confirm", json={},
                                    headers={"X-User-ID": user})
        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}", "detail": response.text[:800]}
        return {"status": "confirmed", "draft_id": draft_id, "confirmation": response.json()}

    def close(self):
        self.client.close()


def run(args) -> int:
    turns = load_turns(Path(args.turns))
    if args.limit:
        turns = turns[: args.limit]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner(args.base_url, args.user)
    records = []
    started = datetime.now(timezone.utc)
    try:
        for turn in turns:
            user = turn.get("user") or args.user
            key = str(turn.get("thread") or turn.get("id") or len(records))
            if turn.get("confirm"):
                payload = runner.confirm(user, key)
                records.append({"id": turn.get("id"), "question": "(confirm the prepared change)",
                                "expected": turn.get("expected"), "response": payload,
                                "user": user, "thread": key})
                continue
            question = turn.get("question") or ""
            payload = runner.ask(user, key, question)
            records.append({"id": turn.get("id"), "question": question,
                            "expected": turn.get("expected"), "response": payload,
                            "user": user, "thread": key, "note": turn.get("note")})
    finally:
        runner.close()

    manifest = {
        "generated_at": started.isoformat(),
        "turns_file": args.turns,
        "turns_sha256": hashlib.sha256(Path(args.turns).read_bytes()).hexdigest(),
        "mode": "live-http",
        "base_url": args.base_url,
        "default_user": args.user,
        "count": len(records),
        "seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "git_head": _git_head(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "answers.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records) + "\n", encoding="utf-8")
    (out / "answers.md").write_text(render_answers(records, manifest), encoding="utf-8")
    failures = sum(1 for r in records if (r["response"] or {}).get("error"))
    print(f"wrote {len(records)} turns to {out}; {failures} transport/HTTP error(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--turns", required=True)
    parser.add_argument("--out", default="eval-runs/final")
    parser.add_argument("--user", default="U-201")
    parser.add_argument("--limit", type=int, default=0)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
