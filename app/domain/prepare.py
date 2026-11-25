from app.catalog import SPEC
from app.domain.helpers import D, DAY, I, M, TS, optional
from app.intake.normalize import canonical


PARSERS = {
    "money": lambda value, code: M(value, code),
    "decimal": lambda value, code: D(value, code),
    "decimal_optional": lambda value, code: optional(D, value, code),
    "int": lambda value, code: I(value, code),
    "int_positive": lambda value, code: positive(I(value, code)),
    "date": lambda value, code: DAY(value, code),
    "date_optional": lambda value, code: optional(DAY, value, code),
    "datetime": lambda value, code: TS(value, code),
}


def positive(value):
    if value <= 0:
        raise ValueError("BAD_POSITIVE")
    return value


def _typed(rows):
    typed, issues = [], []
    for raw in rows:
        item = dict(raw)
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            for field, kind in SPEC["types"].items():
                code = "INVALID_" + field.upper()
                item[field] = PARSERS[kind](item.get(field), code)
            typed.append(item)
        except ValueError as exc:
            issues.append({"line": raw.get("_line", 0), "key": raw.get(SPEC["key"], ""), "code": str(exc)})
    return typed, issues


def _apply_pause(item, pauses):
    """用有效凭据覆盖声明的暂停时长；无效凭据抛出对应原因码。"""
    if not pauses:
        return
    key = item.get(SPEC["key"])
    if key in pauses.get("invalid", {}):
        raise ValueError(pauses["invalid"][key])
    if key in pauses.get("hours", {}):
        item["paused_hours"] = pauses["hours"][key]
        item["_pause_source"] = "credential"
        item["_pause_ref"] = pauses.get("refs", {}).get(key, "")
    else:
        item["_pause_source"] = "declared"


def prepare_rows(rows, pauses=None):
    typed, issues = _typed(rows)
    items = []
    for item in typed:
        try:
            if not canonical(item.get(SPEC["key"], "")):
                raise ValueError("KEY_MISSING")
            if item["delivered_at"] < item["pickup_at"]:
                raise ValueError("DELIVERED_BEFORE_PICKUP")
            _apply_pause(item, pauses)
            if item["paused_hours"] < 0:
                raise ValueError("BAD_PAUSE")
            if item["declared_value_cents"] < 0:
                raise ValueError("BAD_DECLARED")
            items.append(item)
        except ValueError as exc:
            issues.append({"line": item.get("_line", 0), "key": item.get(SPEC["key"], ""), "code": str(exc)})
    return items, issues
