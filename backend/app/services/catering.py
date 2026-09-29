"""航空配餐业务规则。

签收动作、列表展示、汇总统计三条链路里关于「送达」的判断统一来自
app.services.catering_delivery，本模块只负责取数、落库与分页，不再各写分支。
"""
from __future__ import annotations

from typing import Any

from app.services import catering_delivery as delivery
from app.store import store

MODULE = delivery.MODULE
REQUIRED_FIELDS = delivery.REQUIRED_FIELDS
STATUS_ORDER = delivery.STATUS_ORDER
ACTION_RULES = delivery.ACTION_RULES
NEGATIVE_ACTIONS = delivery.NEGATIVE_ACTIONS


class CateringService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("配餐单号", ""))]
        if status:
            # 列表的状态口径与签收/汇总共用同一个 status_of，不再直接 row.get("status")。
            rows = [row for row in rows if delivery.status_of(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        # 必填/空值判定走统一口径（None、空白、0 都算缺）。
        missing = delivery.empty_required(values)
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry[delivery.STATUS_FIELD] = delivery.STATUS_PENDING
        entry[delivery.PENDING_FIELD] = delivery.is_pending(entry)
        entry[delivery.ABNORMAL_FIELD] = delivery.is_abnormal(entry)
        rows.append(entry)
        return entry, []

    def summarize_rows(self, rows: list[dict[str, Any]]) -> dict[str, int | float]:
        """配餐汇总：直接转调统一口径，页面统计与运营概览拿到的结果一致。"""
        return delivery.summarize(rows)

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配餐单 {entry_id} 不存在或已归档"
        target = delivery.target_status(action)
        if target is None:
            return None, f"动作「{action}」不属于航空配餐可执行范围"
        # 状态、待处理、异常三个写入位全部来自统一口径；
        # 目标状态必然在状态序列内（ACTION_RULES 与 STATUS_ORDER 同源），无需重复分支。
        entry[delivery.STATUS_FIELD] = target
        entry[delivery.PENDING_FIELD] = delivery.is_pending(entry)
        entry[delivery.ABNORMAL_FIELD] = delivery.is_abnormal(entry)
        return entry, f"配餐单已{action}"
