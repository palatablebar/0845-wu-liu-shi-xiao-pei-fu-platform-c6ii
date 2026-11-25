"""暂停凭据（pause credentials）。

凭据是来源行的补充材料，按运单号覆盖声明的暂停时长。凭据可能在批次
计算完成之后才补到，因此它属于「有效来源」的一部分，但不参与批次身份
（同一基础来源永远复用同一个批次），只影响来源摘要和重算结果。
"""

from app.domain.helpers import I
from app.evidence.manifest import stable_digest
from app.intake.normalize import canonical


# 这些原因码代表「暂停」层面的问题，对账时单列为无效暂停行。
PAUSE_CODES = {
    "BAD_PAUSE",
    "INVALID_PAUSED_HOURS",
    "PAUSE_CREDENTIAL_INVALID",
    "PAUSE_CREDENTIAL_NEGATIVE",
    "PAUSE_CREDENTIAL_CONFLICT",
}


def is_pause_code(code) -> bool:
    return code in PAUSE_CODES


def _entries(raw):
    """把入参整理为 [{waybill_id, paused_hours, ref}]，不做取值校验。

    支持三种形态：{运单号: 小时}、[{waybill_id, paused_hours, ref}]、
    [[运单号, 小时], ...]。
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    else:
        pairs = []
        for item in raw:
            if isinstance(item, dict):
                pairs.append((item.get("waybill_id", item.get("key", "")), item))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((item[0], item[1]))
            else:
                pairs.append((item, item))
    entries = []
    for key, value in pairs:
        waybill = canonical(key)
        if isinstance(value, dict):
            hours = value.get("paused_hours", value.get("hours", value.get("value")))
            ref = value.get("ref", value.get("credential_id", ""))
        else:
            hours = value
            ref = ""
        entries.append({"waybill_id": waybill, "paused_hours": hours, "ref": canonical(ref)})
    return entries


def merge(existing, incoming):
    """先按原凭据登记，再用新凭据覆盖同一运单，返回条目列表。"""
    merged = {}
    order = []
    for entry in list(existing or []) + _entries(incoming):
        key = entry["waybill_id"]
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = entry
    return [merged[key] for key in order]


def normalize_pauses(raw):
    """校验凭据并返回归一结果。

    hours:    {运单号: 有效暂停小时数}
    refs:     {运单号: 凭据号}
    invalid:  {运单号: 原因码}
    entries:  可原样回传的条目列表（用于合并与展示）
    signature: 用于计算来源摘要的稳定结构
    """
    if isinstance(raw, dict) and raw.get("_normalized") is True:
        return raw
    hours, refs, invalid = {}, {}, {}
    entries = _entries(raw)
    seen = {}
    for entry in entries:
        key = entry["waybill_id"]
        if not key:
            continue
        if key in seen:
            # 同一运单重复登记且取值不同，视为凭据冲突
            if seen[key] != canonical(entry["paused_hours"]):
                invalid[key] = "PAUSE_CREDENTIAL_CONFLICT"
                hours.pop(key, None)
                continue
        seen[key] = canonical(entry["paused_hours"])
        try:
            value = I(entry["paused_hours"], "PAUSE_CREDENTIAL_INVALID")
        except ValueError:
            invalid[key] = "PAUSE_CREDENTIAL_INVALID"
            hours.pop(key, None)
            continue
        if value < 0:
            invalid[key] = "PAUSE_CREDENTIAL_NEGATIVE"
            hours.pop(key, None)
            continue
        if key in invalid:
            continue
        hours[key] = value
        refs[key] = entry["ref"]
    # 签名只取归一结果，重复登记同值凭据不会改变来源摘要。
    signature = [[key, "INVALID:" + code, ""] for key, code in invalid.items()]
    signature += [[key, hours[key], refs.get(key, "")] for key in hours]
    signature.sort()
    return {
        "_normalized": True,
        "hours": hours,
        "refs": refs,
        "invalid": invalid,
        "entries": entries,
        "signature": signature,
        "digest": stable_digest(signature),
        "count": len(hours) + len(invalid),
    }
