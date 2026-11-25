from decimal import Decimal

from app.catalog import SPEC
from app.domain.pauses import is_pause_code
from app.reconcile.checks import all_checks


def build_ledger(intake, prepared, prepare_issues, results, pauses=None):
    pauses = pauses or {}
    counts = dict(intake["counts"])
    counts["prepared"] = len(prepared)
    counts["prepare_issues"] = len(prepare_issues)
    counts["computed"] = len(results)

    pause_issues = [issue for issue in prepare_issues if is_pause_code(issue.get("code"))]
    other_issues = [issue for issue in prepare_issues if not is_pause_code(issue.get("code"))]
    counts["invalid_pause"] = len(pause_issues)
    counts["prepare_other"] = len(other_issues)
    counts["posted"] = len(results)
    counts["pause_credential_posts"] = sum(1 for item in prepared if item.get("_pause_source") == "credential")

    # 来源行被下列互斥桶完整划分：精确重复、忽略、采信层隔离、
    # 无效暂停、其他整理隔离、入账。和必须等于来源行。
    buckets = (counts["duplicates"] + counts["ignored"] + counts["isolated"]
               + counts["invalid_pause"] + counts["prepare_other"] + counts["posted"])
    balanced = counts["input"] == buckets
    # 采信行必须等于入账 + 无效暂停 + 其他整理隔离。
    accepted_balanced = counts["accepted"] == counts["posted"] + counts["invalid_pause"] + counts["prepare_other"]
    # 进入计算的条目必须全部入账。
    computed_balanced = counts["computed"] == counts["posted"] == len(results)

    metric = sum((item.get("metric") for item in results if item.get("metric") is not None), Decimal("0"))
    posted_total = sum((Decimal(str(item.get("compensation_cents") or 0)) for item in results), Decimal("0"))
    metric_balanced = metric == posted_total

    # 凭据覆盖的部分不得绕过判定：无效凭据对应到采信行的必须全部出现在无效暂停行。
    accepted_keys = {str(row.get(SPEC["key"], "")) for row in intake["rows"]}
    invalid_credential_keys = set(pauses.get("invalid", {}))
    expected_pause_rows = invalid_credential_keys & accepted_keys
    invalid_seen = {str(issue.get("key", "")) for issue in pause_issues}
    pause_ok = expected_pause_rows.issubset(invalid_seen)
    orphan_credentials = sorted(invalid_credential_keys - accepted_keys)

    checks = [
        {"id": "source", "label": "来源行守恒", "ok": balanced,
         "detail": f"{counts['input']} = {counts['duplicates']}+{counts['ignored']}+{counts['isolated']}"
                   f"+{counts['invalid_pause']}+{counts['prepare_other']}+{counts['posted']}"},
        {"id": "accepted", "label": "采信行守恒", "ok": accepted_balanced,
         "detail": f"{counts['accepted']} = {counts['posted']}+{counts['invalid_pause']}+{counts['prepare_other']}"},
        {"id": "computed", "label": "计算条目完整", "ok": computed_balanced,
         "detail": f"{counts['computed']} = {counts['posted']}"},
        {"id": "posting", "label": "入账金额守恒", "ok": metric_balanced,
         "detail": f"{metric} = {posted_total}"},
        {"id": "pause", "label": "无效暂停行核准", "ok": pause_ok,
         "detail": f"{len(expected_pause_rows)} 条凭据对应无效暂停行"},
    ]

    return {
        "counts": counts,
        "balanced": balanced,
        "metric_field": SPEC.get("metric_field", "metric"),
        "metric_total": str(metric),
        "posted_total": str(posted_total),
        "pause_digest": pauses.get("digest", ""),
        "orphan_credentials": orphan_credentials,
        "checks": checks,
        "all_checks": all_checks(checks),
    }
