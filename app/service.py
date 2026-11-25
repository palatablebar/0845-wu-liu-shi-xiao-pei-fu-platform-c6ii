import hashlib
from decimal import Decimal
from pathlib import Path

from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.pauses import merge as merge_pauses, normalize_pauses
from app.domain.prepare import prepare_rows
from app.evidence.manifest import stable_digest
from app.intake.service import load
from app.reconcile.ledger import build_ledger

# 计算口径的稳定标识；口径变更时必须同时升版本，旧证据才能被识别。
ALGORITHM = "0845-workday-deferral-v1"


def jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def _stage(name):
    return SPEC["stages"].index(name) + 1


def source_digest(file_sha, pauses):
    """来源摘要 = 来源字节 + 规则 + 有效暂停凭据。

    只认内容，不认样例名或文件名这类展示标签，否则同一份数据换个名字
    就会得到新摘要并被误当作新来源。
    """
    return stable_digest({
        "sha256": file_sha,
        "rule": SPEC["rule"],
        "pauses": pauses["signature"],
    })


def calculation_digest(rows):
    return stable_digest([
        {
            "key": str(item.get(SPEC["key"], "")),
            "deadline": str(item.get("deadline_rolled", "")),
            "delay_hours": str(item.get("delay_hours", "")),
            "compensation_cents": item.get("compensation_cents"),
            "verdict": item.get("verdict"),
            "reason": item.get("reason"),
        }
        for item in rows
    ])


def run_key(file_sha):
    """批次身份：只认来源字节与规则，不认凭据或展示用的样例名。

    同一来源（相同字节）无论重跑多少次、以何名称提交，都映射到同一批次，
    因此绝不会因为重跑而多出一笔赔付。
    """
    return hashlib.sha256(
        (SPEC["code"] + file_sha + SPEC["rule"]).encode("utf-8")).hexdigest()[:24]


def pipeline(profile="dirty", path=None, upto="证据交付", pauses=None, generation=1):
    intake = load(profile, path)
    pause_state = normalize_pauses(pauses)
    prepared, prepare_issues = [], []
    results = []
    ledger = None
    if _stage(upto) >= 2:
        prepared, prepare_issues = prepare_rows(intake["rows"], pause_state)
    if _stage(upto) >= 3:
        results = calculate_rows(prepared)
    if _stage(upto) >= 4:
        results = decide_rows(results)
    if _stage(upto) >= 5:
        ledger = build_ledger(intake, prepared, prepare_issues, results, pause_state)
    intake["counts"]["prepared"] = len(prepared)
    intake["counts"]["computed"] = len(results)
    counts = dict(intake["counts"])
    if ledger is not None:
        counts = dict(ledger["counts"])
    issues = intake["issues"] + prepare_issues
    summary = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    for item in results:
        summary[item.get("verdict", "REVIEW")] = summary.get(item.get("verdict", "REVIEW"), 0) + 1
    chart_field = {"0840": "rolling", "0849": "mean", "0850": "settlement_cents"}.get(SPEC["code"], "metric")
    chart = [{"label": item.get("label", item.get(SPEC["key"], "")),
              "value": float(item.get(chart_field) or 0),
              "limit": float(item.get("limit") or 0)}
             for item in results[:12]]
    rows = []
    raw_stage = _stage(upto) <= 2
    if raw_stage:
        stage_rows = intake["rows"] if _stage(upto) == 1 else prepared
        rows = [{key: item.get(key) for key in SPEC["columns"]} for item in stage_rows[:18]]
    else:
        for item in results[:18]:
            rows.append({key: value for key, value in item.items()
                         if key in {"label", "verdict", "reason", "metric", "limit", "status", "state", "breakdown"}
                         or key in SPEC["columns"] or key in SPEC["result_columns"]})
    filename = Path(intake["path"]).name
    digest = source_digest(intake["sha256"], pause_state)
    source = {
        "profile": profile,
        "filename": filename,
        "sha256": intake["sha256"],
        "digest": digest,
        "pause_digest": pause_state["digest"],
        "pause_count": pause_state["count"],
        "pause_valid": len(pause_state["hours"]),
        "pause_invalid": len(pause_state["invalid"]),
        "pauses": [{"waybill_id": key, "paused_hours": value, "ref": pause_state["refs"].get(key, "")}
                   for key, value in sorted(pause_state["hours"].items())],
        "invalid_pauses": [{"waybill_id": key, "code": code}
                           for key, code in sorted(pause_state["invalid"].items())],
    }
    calc_digest = calculation_digest(results)
    calculation = {
        "algorithm": ALGORITHM,
        "generation": int(generation),
        "digest": calc_digest,
        "version": "calc-" + calc_digest[:12],
        "rule": SPEC["rule"],
    }
    payload = {
        "project": SPEC["code"] + " " + SPEC["name"],
        "rule": SPEC["rule_short"],
        "profile": profile,
        "source": source,
        "calculation": calculation,
        "counts": counts,
        "issues": issues[:60],
        "rows": rows,
        "row_kind": "source" if raw_stage else "result",
        "chart": chart,
        "summary": summary,
        "ledger": ledger,
        "stages": [{"id": "intake", "name": SPEC["stages"][0]},
                   {"id": "prepare", "name": SPEC["stages"][1]},
                   {"id": "calculate", "name": SPEC["stages"][2]},
                   {"id": "decision", "name": SPEC["stages"][3]},
                   {"id": "reconcile", "name": SPEC["stages"][4]}],
        "run_key": run_key(intake["sha256"]),
    }
    return jsonable(payload)


def merge_credentials(existing, incoming):
    """把新到凭据并入已登记凭据，返回可再次归一的条目列表。"""
    return merge_pauses(existing, incoming)
