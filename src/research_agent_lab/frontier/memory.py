"""Durable ideation/experiment memory and *human-feedback* bandit adaptation.

Not gradient-based reinforcement learning: an auditable UCB strategy selector.
Private/sensitive source records must never be placed in this SQLite store.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STRATEGIES = ("balanced", "novelty", "feasibility")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, path: str = "outputs/frontier-memory.sqlite"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('ideation','experiment','failure','review')),
                strategy TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS exp_line_kind
                ON experiences(line_id,kind,created_at);
            CREATE TABLE IF NOT EXISTS human_feedback (
                run_id TEXT NOT NULL,
                reviewer_tag TEXT NOT NULL,
                line_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('accept','revise','reject')),
                novelty INTEGER NOT NULL CHECK(novelty BETWEEN 0 AND 100),
                feasibility INTEGER NOT NULL CHECK(feasibility BETWEEN 0 AND 100),
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(run_id,reviewer_tag)
            );
            CREATE TABLE IF NOT EXISTS run_index (
                run_id TEXT PRIMARY KEY,
                line_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def recall(self, line_id: str, limit: int = 6) -> list[dict]:
        rows = self.db.execute(
            "SELECT kind,strategy,summary FROM experiences "
            "WHERE line_id=? ORDER BY id DESC LIMIT ?",
            (line_id, max(0, min(limit, 16))),
        ).fetchall()
        return [{"kind": kind, "strategy": strategy, "summary": summary}
                for kind, strategy, summary in rows]

    def select_strategy(self, line_id: str) -> str:
        """UCB1 on explicitly supplied human ratings, not LLM self-scores."""
        rows = self.db.execute(
            "SELECT strategy,COUNT(*),AVG((novelty+feasibility)/200.0),"
            "AVG(CASE decision WHEN 'accept' THEN 1.0 "
            "WHEN 'revise' THEN 0.35 ELSE 0.0 END) "
            "FROM human_feedback WHERE line_id=? GROUP BY strategy", (line_id,)
        ).fetchall()
        stats = {name: (n, (score + decision) / 2)
                 for name, n, score, decision in rows}
        for strategy in STRATEGIES:
            if strategy not in stats:
                return strategy
        total = sum(n for n, _ in stats.values())
        return max(STRATEGIES, key=lambda key: (
            stats[key][1] + math.sqrt(2 * math.log(max(2, total)) / stats[key][0]),
            -STRATEGIES.index(key)
        ))

    def record_run(self, run_id: str, line_id: str, strategy: str,
                   *, best_title: str, lessons: list[str], status: str,
                   experiment_summary: str = "") -> None:
        if strategy not in STRATEGIES:
            raise ValueError("Unknown strategy")
        # Explicitly short summaries. No full paper abstract/records or credentials.
        with self.db:
            self.db.execute(
                "INSERT INTO run_index VALUES (?,?,?,?)",
                (run_id, line_id, strategy, utcnow())
            )
            self.db.execute(
                "INSERT INTO experiences(line_id,run_id,kind,strategy,summary,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (line_id, run_id,
                 "ideation" if status == "eligible" else "failure", strategy,
                 json.dumps({"best_title": best_title[:200],
                             "lessons": [str(x)[:300] for x in lessons[:6]],
                             "status": status}, ensure_ascii=False)[:1800],
                 utcnow())
            )
            if experiment_summary:
                self.db.execute(
                    "INSERT INTO experiences(line_id,run_id,kind,strategy,summary,created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (line_id, run_id, "experiment", strategy,
                     experiment_summary[:900], utcnow())
                )

    def add_feedback(self, run_id: str, reviewer_tag: str, decision: str,
                     novelty: int, feasibility: int, comment: str = "") -> None:
        if decision not in ("accept", "revise", "reject"):
            raise ValueError("Unexpected decision")
        if not isinstance(novelty, int) or not isinstance(feasibility, int) or not (
            0 <= novelty <= 100 and 0 <= feasibility <= 100
        ):
            raise ValueError("Scores must be 0..100")
        row = self.db.execute(
            "SELECT line_id,strategy FROM run_index WHERE run_id=?", (run_id,)
        ).fetchone()
        if not row:
            raise ValueError("Cannot record feedback for unknown run")
        with self.db:
            self.db.execute(
                "INSERT INTO human_feedback VALUES(?,?,?,?,?,?,?,?,?)",
                (run_id, reviewer_tag[:100], row[0], row[1], decision,
                 novelty, feasibility, comment[:900], utcnow())
            )
            self.db.execute(
                "INSERT INTO experiences(line_id,run_id,kind,strategy,summary,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (row[0], run_id, "review", row[1],
                 json.dumps({"decision": decision, "novelty": novelty,
                             "feasibility": feasibility,
                             "comment": comment[:450]}, ensure_ascii=False),
                 utcnow())
            )
