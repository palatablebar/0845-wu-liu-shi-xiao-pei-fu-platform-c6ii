import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


BASE_COLUMNS = {
    "id": "TEXT PRIMARY KEY",
    "request_key": "TEXT UNIQUE NOT NULL",
    "created_at": "TEXT NOT NULL",
    "profile": "TEXT NOT NULL",
    "status": "TEXT NOT NULL",
    "revision": "INTEGER NOT NULL",
    "payload": "TEXT NOT NULL",
    "comment": "TEXT NOT NULL DEFAULT ''",
}

# 追加列用于批次版本化：凭据、来源摘要、计算版本、签发快照。
EXTRA_COLUMNS = {
    "generation": "INTEGER NOT NULL DEFAULT 1",
    "source_digest": "TEXT NOT NULL DEFAULT ''",
    "calc_version": "TEXT NOT NULL DEFAULT ''",
    "credentials": "TEXT NOT NULL DEFAULT '[]'",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
    "signed_payload": "TEXT",
    "signed_at": "TEXT",
    "signed_revision": "INTEGER",
    "signed_generation": "INTEGER",
    "signed_source_digest": "TEXT",
}


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=8)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self):
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY,
              request_key TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              profile TEXT NOT NULL,
              status TEXT NOT NULL,
              revision INTEGER NOT NULL,
              payload TEXT NOT NULL,
              comment TEXT NOT NULL DEFAULT ''
            );
            ''')
            present = {row["name"] for row in db.execute("PRAGMA table_info(runs)")}
            for name, ddl in EXTRA_COLUMNS.items():
                if name not in present:
                    db.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")

    def find_by_request(self, request_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE request_key=?", (request_key,)).fetchone()
        return dict(row) if row else None

    def create(self, request_key, profile, payload, generation=1, source_digest="",
               calc_version="", credentials=None):
        existing = self.find_by_request(request_key)
        if existing:
            return existing
        run_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,request_key,created_at,profile,status,revision,payload,comment,"
                "generation,source_digest,calc_version,credentials,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, request_key, now, profile, "DRAFT", 0,
                 json.dumps(payload, ensure_ascii=False), "", generation, source_digest,
                 calc_version, json.dumps(list(credentials or []), ensure_ascii=False), now))
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def update_draft(self, run_id, payload, generation, source_digest, calc_version,
                     credentials, expected_revision=None):
        """仅在批次尚未签发时原地重算；已签发版本拒绝改写。"""
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                db.rollback()
                return None, "missing"
            if row["status"] == "APPROVED":
                db.rollback()
                return dict(row), "signed"
            if expected_revision is not None and row["revision"] != expected_revision:
                db.rollback()
                return dict(row), "stale"
            db.execute(
                "UPDATE runs SET payload=?, generation=?, source_digest=?, calc_version=?, "
                "credentials=?, updated_at=?, revision=revision+1 WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), generation, source_digest,
                 calc_version, json.dumps(list(credentials or []), ensure_ascii=False), now, run_id))
        return self.get(run_id), None

    def review(self, run_id, decision, comment, expected_revision):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                db.rollback()
                return None, "missing"
            if row["revision"] != expected_revision:
                db.rollback()
                return None, "stale"
            if row["status"] == "APPROVED":
                db.rollback()
                return dict(row), "signed"
            if decision == "APPROVED":
                # 签发即冻结：保留当时的金额、来源摘要与计算版本，后续凭据不再改写。
                db.execute(
                    "UPDATE runs SET status=?, revision=revision+1, comment=?, "
                    "signed_payload=payload, signed_at=?, signed_revision=revision+1, "
                    "signed_generation=generation, signed_source_digest=source_digest, updated_at=? "
                    "WHERE id=?",
                    (decision, comment, now, now, run_id))
            else:
                db.execute(
                    "UPDATE runs SET status=?, revision=revision+1, comment=?, updated_at=? WHERE id=?",
                    (decision, comment, now, run_id))
        return self.get(run_id), None
