def _ledger_ok(payload):
    ledger = payload.get("ledger")
    if not isinstance(ledger, dict):
        return False
    if ledger.get("balanced") is not True:
        return False
    if ledger.get("all_checks") is not True:
        return False
    checks = ledger.get("checks") or []
    return bool(checks) and all(item.get("ok") for item in checks)


def approval_blockers(payload):
    """返回阻断签发的原因码列表；为空才允许签发。"""
    blockers = []
    if int(payload.get("summary", {}).get("REJECT", 0)) > 0:
        blockers.append("REJECT_ROWS")
    if not _ledger_ok(payload):
        blockers.append("LEDGER_UNBALANCED")
    source = payload.get("source") or {}
    if not source.get("digest"):
        blockers.append("SOURCE_DIGEST_MISSING")
    if source.get("pause_invalid", 0) and not source.get("pause_digest"):
        blockers.append("PAUSE_DIGEST_MISSING")
    calculation = payload.get("calculation") or {}
    if not calculation.get("version") or not calculation.get("digest"):
        blockers.append("CALCULATION_VERSION_MISSING")
    return blockers


def approval_allowed(payload):
    return not approval_blockers(payload)
