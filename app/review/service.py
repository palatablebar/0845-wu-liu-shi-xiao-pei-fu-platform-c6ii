import json

from app.errors import DomainIssue
from app.review.policy import approval_blockers
from app.service import merge_credentials, pipeline, run_key


def _credentials(row):
    try:
        return json.loads(row.get("credentials") or "[]")
    except (TypeError, ValueError):
        return []


def _build(profile, credentials, generation):
    return pipeline(profile, pauses=credentials, generation=generation)


def create_run(store, profile="clean", credentials=None):
    """同一基础来源只建一个批次；新凭据到来时草稿原地重算，签发版本不动。"""
    # 先算基础来源身份（不含凭据），确保同一来源始终映射到同一批次。
    probe = pipeline(profile, pauses=None)
    key = run_key(probe["source"]["sha256"])
    row = store.find_by_request(key)
    incoming = merge_credentials(_credentials(row) if row else [], credentials)
    if row is None:
        payload = _build(profile, incoming, generation=1)
        row = store.create(
            key, profile, payload, generation=1,
            source_digest=payload["source"]["digest"],
            calc_version=payload["calculation"]["version"],
            credentials=incoming)
        return serialize(row, revalidated=False)

    if row["status"] == "APPROVED":
        # 已签发版本冻结：保留原金额与来源摘要，只回报批次当前状态。
        return serialize(row, revalidated=False)

    current = json.loads(row["payload"])
    digest_now = current.get("source", {}).get("digest")
    payload = _build(profile, incoming, generation=int(row["generation"] or 1))
    changed = payload["source"]["digest"] != digest_now
    if changed:
        generation = int(row["generation"] or 1) + 1
        payload = _build(profile, incoming, generation=generation)
        row, problem = store.update_draft(
            row["id"], payload, generation,
            payload["source"]["digest"], payload["calculation"]["version"], incoming)
        if problem == "signed":
            return serialize(store.get(row["id"]), revalidated=False)
        if problem == "missing":
            raise DomainIssue("RUN_NOT_FOUND", 404)
        return serialize(row, revalidated=True)
    # 来源未变：沿用既有草稿的登记凭据，不派生新批次也不递增版本。
    return serialize(row, revalidated=False)


def approve(store, run_id, decision, comment, expected_revision):
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if row["status"] == "APPROVED":
        # 已签发版本停止改写；再次提交视为陈旧。
        raise DomainIssue("STALE_REVIEW", 409)
    payload = json.loads(row["payload"])
    if decision == "APPROVED":
        blockers = approval_blockers(payload)
        if blockers:
            raise DomainIssue("GATE_BLOCKED", 409, detail=blockers[0])
    if decision not in {"APPROVED", "HELD"}:
        raise DomainIssue("BAD_REQUEST")
    row, problem = store.review(run_id, decision, comment.strip(), expected_revision)
    if problem == "missing":
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if problem == "stale":
        raise DomainIssue("STALE_REVIEW", 409)
    if problem == "signed":
        raise DomainIssue("STALE_REVIEW", 409)
    return serialize(row)


def add_credentials(store, run_id, credentials):
    """凭据补录入口：并入批次凭据；草稿重算，已签发版本冻结。"""
    row = store.get(run_id)
    if row is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    incoming = merge_credentials(_credentials(row), credentials)
    if row["status"] == "APPROVED":
        return {"run": serialize(row, revalidated=False), "recalculated": False,
                "reason": "SIGNED_FROZEN"}
    current = json.loads(row["payload"])
    payload = _build(row["profile"], incoming, generation=int(row["generation"] or 1))
    if payload["source"]["digest"] == current.get("source", {}).get("digest"):
        return {"run": serialize(row, revalidated=False), "recalculated": False,
                "reason": "SOURCE_UNCHANGED"}
    generation = int(row["generation"] or 1) + 1
    payload = _build(row["profile"], incoming, generation=generation)
    row, problem = store.update_draft(
        row["id"], payload, generation, payload["source"]["digest"],
        payload["calculation"]["version"], incoming)
    if problem == "missing":
        raise DomainIssue("RUN_NOT_FOUND", 404)
    return {"run": serialize(row, revalidated=problem is None),
            "recalculated": problem is None,
            "reason": "SOURCE_CHANGED" if problem is None else "SIGNED_FROZEN"}


def serialize(row, revalidated=False):
    if row is None:
        return None
    # 证据与展示都以冻结的签发快照为准，避免签发后凭据补录改写历史。
    approved = row.get("status") == "APPROVED"
    if approved and row.get("signed_payload"):
        payload = json.loads(row["signed_payload"])
    else:
        payload = json.loads(row["payload"])
    frozen = approved
    payload.update(
        run_id=row["id"],
        status=row["status"],
        revision=row["revision"],
        comment=row["comment"],
        created_at=row["created_at"],
        generation=row.get("generation", 1),
        revalidated=bool(revalidated),
        frozen=frozen,
        signed_at=row.get("signed_at"),
        signed_revision=row.get("signed_revision"),
        source_digest=payload.get("source", {}).get("digest", row.get("source_digest", "")),
        calc_version=payload.get("calculation", {}).get("version", row.get("calc_version", "")),
        pause_count=(payload.get("source") or {}).get("pause_count", 0),
        blockers=approval_blockers(payload),
    )
    return payload
