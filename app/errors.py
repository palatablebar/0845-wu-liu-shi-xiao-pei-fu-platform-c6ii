from flask import jsonify


MESSAGES = {
    "EMPTY_FILE": "文件为空",
    "BLANK_FILE": "文件只有空白",
    "HEADER_ONLY": "文件只有表头",
    "HEADER_MISMATCH": "表头与本项目字段不一致",
    "UNCLOSED_QUOTE": "引号未闭合，文件已拒收",
    "TOO_MANY_ROWS": "数据行超过上限",
    "FILE_TOO_LARGE": "文件超过大小上限",
    "KEY_MISSING": "主键为空",
    "CONFLICT_DUPLICATE": "同一键存在冲突内容",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "阶段不存在",
    "RUN_NOT_FOUND": "批次不存在",
    "STALE_REVIEW": "批次已被更新，请刷新后复核",
    "GATE_BLOCKED": "存在阻断项，不能签发",
    "NOT_APPROVED": "批次尚未签发",
    "BAD_REQUEST": "请求内容不完整",
    "REJECT_ROWS": "存在阻断项，不能签发",
    "LEDGER_UNBALANCED": "来源行、隔离行、无效暂停行与入账行未对平，不能签发",
    "SOURCE_DIGEST_MISSING": "缺少来源摘要，不能签发",
    "PAUSE_DIGEST_MISSING": "缺少暂停凭据摘要，不能签发",
    "CALCULATION_VERSION_MISSING": "缺少计算版本，不能签发",
    "SIGNED_FROZEN": "批次已签发，保留原金额与来源摘要",
    "SOURCE_CHANGED": "来源数据变化，已重算",
}


class DomainIssue(Exception):
    def __init__(self, code: str, status: int = 400, detail: str | None = None):
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


def error_response(exc: DomainIssue):
    message = exc.detail or MESSAGES.get(exc.code, "请求无法处理")
    # 签发阻断的 detail 是原因码集合：优先转成可读文案，同时把原因码留在响应里。
    reasons = [part for part in str(message).split(",") if part]
    if exc.code == "GATE_BLOCKED" and all(part in MESSAGES for part in reasons):
        return jsonify(error=MESSAGES[reasons[0]], code=exc.code, reasons=reasons), exc.status
    return jsonify(error=message, code=exc.code), exc.status
