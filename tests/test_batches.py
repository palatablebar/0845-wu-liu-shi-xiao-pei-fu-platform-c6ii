"""批次版本、暂停凭据补录与守恒签发的回归用例。"""

import json

from app.domain.pauses import normalize_pauses
from app.review.policy import approval_blockers
from app.service import pipeline


def create(client, profile="clean", **extra):
    response = client.post("/api/runs", json={"profile": profile, **extra})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def sign(client, run, revision=None, decision="APPROVED"):
    return client.post(f"/api/runs/{run['run_id']}/review", json={
        "decision": decision, "comment": "复核", "expected_revision": run["revision"] if revision is None else revision})


# --- 同一来源重跑只沿用原批次，不新增一笔赔付 ---------------------------------


def test_same_source_reruns_reuse_single_batch(client):
    first = create(client)
    second = create(client)
    assert first["run_id"] == second["run_id"]
    assert first["ledger"]["metric_total"] == second["ledger"]["metric_total"]


def test_rerun_does_not_add_posting(client):
    first = create(client)
    for _ in range(3):
        again = create(client)
    assert again["run_id"] == first["run_id"]
    assert again["counts"]["posted"] == first["counts"]["posted"]
    assert again["ledger"]["metric_total"] == first["ledger"]["metric_total"]
    assert again["generation"] == first["generation"]


# --- 暂停凭据补齐：草稿重算，签发版本冻结 -------------------------------------


def test_credentials_recalculate_draft_in_place(client):
    run = create(client)
    before = run["source_digest"]
    result = client.post(f"/api/runs/{run['run_id']}/credentials", json={"credentials": {"W1": 5}}).get_json()
    assert result["recalculated"] is True
    after = result["run"]
    assert after["run_id"] == run["run_id"]          # 不派生新批次
    assert after["source_digest"] != before          # 来源摘要变化
    assert after["generation"] == run["generation"] + 1
    assert any(p["waybill_id"] == "W1" for p in after["source"]["pauses"])


def test_credentials_do_not_create_second_batch(client):
    run = create(client)
    client.post(f"/api/runs/{run['run_id']}/credentials", json={"credentials": {"W1": 5}})
    rerun = create(client)
    assert rerun["run_id"] == run["run_id"]


def test_signed_batch_freezes_amount_and_source(client):
    run = create(client)
    assert sign(client, run).status_code == 200
    evidence_before = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()

    result = client.post(f"/api/runs/{run['run_id']}/credentials",
                         json={"credentials": {"W5": 40}}).get_json()
    assert result["recalculated"] is False
    assert result["reason"] == "SIGNED_FROZEN"

    evidence_after = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
    assert evidence_after["source_digest"] == evidence_before["source_digest"]
    assert evidence_after["ledger"]["metric_total"] == evidence_before["ledger"]["metric_total"]
    assert evidence_after["artifact_sha256"] == evidence_before["artifact_sha256"]


def test_signed_batch_rerun_stays_frozen(client):
    run = create(client)
    sign(client, run)
    frozen = create(client)
    assert frozen["run_id"] == run["run_id"]
    assert frozen["frozen"] is True
    assert frozen["ledger"]["metric_total"] == run["ledger"]["metric_total"]


def test_held_batch_is_recalculated_by_credentials(client):
    run = create(client)
    held = sign(client, run, decision="HELD").get_json()
    assert held["status"] == "HELD"
    result = client.post(f"/api/runs/{run['run_id']}/credentials",
                         json={"credentials": {"W1": 4}}).get_json()
    assert result["recalculated"] is True
    assert result["run"]["generation"] == run["generation"] + 1


# --- 守恒：来源行、隔离行、无效暂停行、入账行必须对平 -------------------------


def test_ledger_reconciles_by_bucket(client):
    run = create(client)
    counts = run["ledger"]["counts"]
    assert counts["input"] == (counts["duplicates"] + counts["ignored"] + counts["isolated"]
                               + counts["invalid_pause"] + counts["prepare_other"] + counts["posted"])
    assert counts["accepted"] == counts["posted"] + counts["invalid_pause"] + counts["prepare_other"]
    assert run["ledger"]["balanced"] is True
    assert run["ledger"]["all_checks"] is True


def test_invalid_credential_becomes_invalid_pause_row(client):
    run = create(client)
    result = client.post(f"/api/runs/{run['run_id']}/credentials",
                         json={"credentials": {"W1": "abc"}}).get_json()["run"]
    assert result["source"]["invalid_pauses"] == [{"waybill_id": "W1", "code": "PAUSE_CREDENTIAL_INVALID"}]
    assert result["counts"]["invalid_pause"] == 1
    assert result["counts"]["accepted"] == result["counts"]["posted"] + 1
    assert result["ledger"]["balanced"] is True


def test_unbalanced_ledger_blocks_approval():
    payload = pipeline("clean")
    payload["ledger"]["checks"] = [dict(item, ok=False) for item in payload["ledger"]["checks"]]
    payload["ledger"]["all_checks"] = False
    assert "LEDGER_UNBALANCED" in approval_blockers(payload)


def test_missing_source_digest_blocks_approval():
    payload = pipeline("clean")
    payload["source"]["digest"] = ""
    payload["source_digest"] = ""
    assert "SOURCE_DIGEST_MISSING" in approval_blockers(payload)


def test_dirty_batch_cannot_be_signed(client):
    run = create(client, "dirty")
    response = sign(client, run)
    assert response.status_code == 409
    assert response.get_json()["code"] == "GATE_BLOCKED"


# --- 页面与证据：来源摘要、计算版本、同一份证据 -------------------------------


def test_page_shows_source_digest_and_calc_version(client):
    page = client.get("/").get_data(as_text=True)
    assert "来源与版本" in page
    assert "panel-version" in page
    assert "补录凭据" in page
    script = client.get("/static/workbench.js").get_data(as_text=True)
    assert "来源摘要" in script
    assert "计算版本" in script
    assert "无效暂停" in script


def test_run_exposes_digest_and_version(client):
    run = create(client)
    assert len(run["source_digest"]) == 64
    assert run["calc_version"].startswith("calc-")
    assert run["calculation"]["generation"] == 1


def test_evidence_matches_signed_version(client):
    run = create(client)
    sign(client, run)
    artifact = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
    assert artifact["source_digest"] == run["source_digest"]
    assert artifact["calc_version"] == run["calc_version"]
    assert artifact["calculation"]["generation"] == run["generation"]


def test_evidence_is_repeatable(client):
    run = create(client)
    sign(client, run)
    first = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
    second = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
    assert first["artifact_sha256"] == second["artifact_sha256"]


# --- 凭据归一单元 -------------------------------------------------------------


def test_pause_normalization_rejects_conflict():
    state = normalize_pauses([{"waybill_id": "W1", "paused_hours": 2},
                              {"waybill_id": "W1", "paused_hours": 3}])
    assert state["invalid"]["W1"] == "PAUSE_CREDENTIAL_CONFLICT"
    assert "W1" not in state["hours"]


def test_pause_digest_is_order_independent():
    a = normalize_pauses({"W1": 2, "W2": 3})
    b = normalize_pauses({"W2": 3, "W1": 2})
    assert a["digest"] == b["digest"]
