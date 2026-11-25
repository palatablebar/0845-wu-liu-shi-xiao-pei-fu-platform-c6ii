from app.errors import DomainIssue
from app.evidence.manifest import stable_digest


SCHEMA = "workbench-evidence/v1"


def render(run):
    """证据只从已签发版本生成；签发快照冻结，重复下载得到同一份。"""
    if run is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if run["status"] != "APPROVED":
        raise DomainIssue("NOT_APPROVED", 409)
    source = run.get("source") or {}
    calculation = run.get("calculation") or {}
    artifact = {
        "schema": SCHEMA,
        "run_id": run["run_id"],
        "project": run["project"],
        "rule": run["rule"],
        "profile": run["profile"],
        "source": source,
        "source_digest": run.get("source_digest") or source.get("digest"),
        "calculation": calculation,
        "calc_version": run.get("calc_version") or calculation.get("version"),
        "counts": run["counts"],
        "ledger": run["ledger"],
        "summary": run["summary"],
        "review": {"status": run["status"], "revision": run["revision"], "comment": run["comment"]},
    }
    artifact["artifact_sha256"] = stable_digest(artifact)
    return artifact
