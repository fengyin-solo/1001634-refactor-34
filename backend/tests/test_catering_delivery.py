"""航空配餐「送达」统一口径的回归测试。

签收动作、列表展示、汇总统计三条链路共用 app.services.catering_delivery。
本文件不依赖 pytest，直接执行即可：python3 tests/test_catering_delivery.py
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.seed import SEED_ROWS
from app.services import catering_delivery as delivery
from app.services.catering import CateringService
from app.store import Store, store

client = TestClient(app)
service = CateringService()


def test_status_predicates() -> None:
    assert delivery.is_signed({"status": delivery.STATUS_SIGNED})
    assert not delivery.is_signed({"status": delivery.STATUS_DELIVERING})
    assert not delivery.is_signed({})
    assert not delivery.is_signed({"status": None})
    assert delivery.is_cancelled({"status": delivery.STATUS_CANCELLED})
    assert delivery.is_delivered({"status": delivery.STATUS_SIGNED})
    assert not delivery.is_delivered({"status": delivery.STATUS_CANCELLED})
    # 待处理写入口径：取消配送后不待处理，已签收仍待处理
    for status in ("待配送", "配送中", "已签收"):
        assert delivery.is_pending({"status": status})
    assert not delivery.is_pending({"status": "已取消"})
    assert delivery.is_pending({})
    # 历史标记优先，不改动既有配餐单上的值
    assert delivery.pending_flag({"status": "已签收", "pending": False}) is False
    assert delivery.pending_flag({"status": "已签收"}) is True
    assert delivery.abnormal_flag({"abnormal": True}) is True
    assert delivery.abnormal_flag({}) is False


def test_empty_and_boundary_values() -> None:
    # 与旧的 str(value or "").strip() 必填判空完全一致
    def old_empty(value: object) -> bool:
        return not str(value or "").strip()

    for value in (None, "", "   ", "\t\n", "0", 0, 0.0, 5, -1,
                  "12份", " 张三 ", True, False, [], {}, [1], {"a": 1}):
        assert (delivery.clean_text(value) is None) == old_empty(value), value
    assert delivery.clean_text(" 张三 ") == "张三"
    assert delivery.clean_text(5) == 5
    assert delivery.portion_text(0) is None
    assert delivery.category_text("  ") is None
    assert delivery.receiver_name(None) is None
    assert delivery.empty_required(
        {"配餐单号": "", "关联航班": " ", "餐食份数": 0}
    ) == ["配餐单号", "关联航班", "餐食份数"]
    assert delivery.empty_required(
        {"配餐单号": "A", "关联航班": "B", "餐食份数": "3"}
    ) == []


def test_action_mapping() -> None:
    assert delivery.target_status("安排配送") == "配送中"
    assert delivery.target_status("确认签收") == "已签收"
    assert delivery.target_status("取消配送") == "已取消"
    assert delivery.target_status("乱填") is None
    assert delivery.target_status("") is None


def test_summary_matches_seed_flags() -> None:
    summary = delivery.summarize(store.rows(delivery.MODULE))
    rows = store.rows(delivery.MODULE)
    assert summary["created"] == len(rows)
    assert summary["pending"] == sum(1 for row in rows if row.get("pending"))
    assert summary["abnormal"] == sum(1 for row in rows if row.get("abnormal"))
    assert summary["signed"] == 1
    assert summary["cancelled"] == 0
    # 样例里的份数是文本，合计按 0；数字份数才累加
    assert summary["total_portions"] == 0
    numeric = [{"status": "已签收", "餐食份数": 10},
               {"status": "已取消", "餐食份数": 0},
               {"status": "待配送", "餐食份数": "五点五份"}]
    s2 = delivery.summarize(numeric)
    assert (s2["signed"], s2["cancelled"], s2["total_portions"]) == (1, 1, 10)


def test_seed_rows_and_statuses_untouched() -> None:
    fresh = Store()
    assert fresh.rows("catering") == SEED_ROWS["catering"]
    assert [row["status"] for row in fresh.rows("catering")] == ["待配送", "配送中", "已签收"]
    assert [row["pending"] for row in fresh.rows("catering")] == [True, True, False]
    assert [row["abnormal"] for row in fresh.rows("catering")] == [False, True, False]


def test_action_lifecycle_http() -> None:
    r = client.post("/api/catering", json={"values": {
        "配餐单号": "CATE-LIFE", "关联航班": "F", "餐食份数": "8"}})
    entry_id = r.json()["entry"]["id"]
    expected = [
        ("安排配送", "配送中", True),
        ("确认签收", "已签收", True),
        ("取消配送", "已取消", False),
    ]
    for action, status, pending in expected:
        r = client.post(f"/api/catering/{entry_id}/actions",
                        json={"values": {"action": action}})
        assert r.json()["ok"] is True
        body = client.get(f"/api/catering/{entry_id}").json()
        assert (body["status"], body["pending"], body["abnormal"]) == (status, pending, False)
    # 旧实现没有状态前置校验，已取消后仍可再签收——边界行为保持不变
    r = client.post(f"/api/catering/{entry_id}/actions",
                    json={"values": {"action": "确认签收"}})
    assert r.json()["ok"] is True
    assert client.get(f"/api/catering/{entry_id}").json()["status"] == "已签收"
    # 未知/空白动作被拦下
    for raw in ("", "   ", "乱填"):
        r = client.post(f"/api/catering/{entry_id}/actions",
                        json={"values": {"action": raw}})
        assert r.json()["ok"] is False


def test_list_filter_and_summary_share_canonical_rules() -> None:
    items, total = service.list_entries(status="已签收")
    assert all(delivery.is_signed(row) for row in items)
    assert total == sum(1 for row in store.rows(delivery.MODULE) if delivery.is_signed(row))
    overview = next(
        module for module in client.get("/api/overview").json()["modules"]
        if module["name"] == delivery.MODULE
    )
    summary = delivery.summarize(store.rows(delivery.MODULE))
    assert overview["created"] == summary["created"]
    assert overview["pending"] == summary["pending"]
    assert overview["abnormal"] == summary["abnormal"]


def main() -> None:
    tests = [
        test_status_predicates,
        test_empty_and_boundary_values,
        test_action_mapping,
        test_summary_matches_seed_flags,
        test_seed_rows_and_statuses_untouched,
        test_action_lifecycle_http,
        test_list_filter_and_summary_share_canonical_rules,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} tests passed")


if __name__ == "__main__":
    main()
