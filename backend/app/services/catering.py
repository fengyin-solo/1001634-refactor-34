"""航空配餐业务规则：配餐送达状态、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.store import Store

MODULE = "catering"

ORDER_FIELD = "配餐单号"
FLIGHT_FIELD = "关联航班"
PORTION_FIELD = "餐食份数"
CATEGORY_FIELD = "餐食类别"
VEHICLE_FIELD = "配餐车辆"
DELIVERED_AT_FIELD = "送达时刻"
RECEIVER_FIELD = "接收人员"
DISPLAY_STATUS_FIELD = "配餐状态"

LIST_FIELDS = [
    ORDER_FIELD,
    FLIGHT_FIELD,
    PORTION_FIELD,
    CATEGORY_FIELD,
    VEHICLE_FIELD,
    DELIVERED_AT_FIELD,
    RECEIVER_FIELD,
    DISPLAY_STATUS_FIELD,
]
REQUIRED_FIELDS = [ORDER_FIELD, FLIGHT_FIELD, PORTION_FIELD]

STATUS_FIELD = "status"
PENDING_FIELD = "pending"
ABNORMAL_FIELD = "abnormal"
STATUS_ORDER = ["待配送", "配送中", "已签收", "已取消"]
ACTION_RULES = {"安排配送": "配送中", "确认签收": "已签收", "取消配送": "已取消"}
NEGATIVE_ACTIONS = []
FINAL_STATUS = STATUS_ORDER[-1]


@dataclass(frozen=True)
class DeliveryState:
    """配餐单在动作、列表和汇总中共用的送达状态。"""

    status: Any
    pending: bool
    abnormal: bool


def delivery_state(entry: dict[str, Any], action: str | None = None) -> DeliveryState:
    """读取或计算配餐单的送达状态；不在此函数里改写原始配餐单。"""
    if action is not None:
        if action not in ACTION_RULES:
            raise ValueError(f"动作「{action}」不属于航空配餐可执行范围")
        target = ACTION_RULES[action]
        return DeliveryState(
            status=target,
            pending=target != FINAL_STATUS,
            abnormal=action in NEGATIVE_ACTIONS,
        )

    return DeliveryState(
        status=entry.get(STATUS_FIELD),
        pending=bool(entry.get(PENDING_FIELD)),
        abnormal=bool(entry.get(ABNORMAL_FIELD)),
    )


def matches_delivery_filters(
    entry: dict[str, Any],
    *,
    keyword: str | None = None,
    status: str | None = None,
) -> bool:
    """按列表接口原有口径判断配餐单是否命中筛选条件。"""
    if keyword and keyword not in str(entry.get(ORDER_FIELD, "")):
        return False
    if status and delivery_state(entry).status != status:
        return False
    return True


class CateringService:
    def __init__(self, store: Store | None = None) -> None:
        if store is None:
            from app.store import store as default_store

            store = default_store
        self.store = store

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [
            row
            for row in self.store.rows(MODULE)
            if matches_delivery_filters(row, keyword=keyword, status=status)
        ]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return self.store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = self.store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry[PENDING_FIELD] = True
        entry[ABNORMAL_FIELD] = False
        rows.append(entry)
        return entry, []

    def summarize_entries(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        """汇总配餐单数量及共用状态口径下的待处理、异常数量。"""
        states = [delivery_state(row) for row in rows]
        return {
            "created": len(rows),
            "pending": sum(1 for state in states if state.pending),
            "abnormal": sum(1 for state in states if state.abnormal),
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = self.store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配餐单 {entry_id} 不存在或已归档"
        try:
            state = delivery_state(entry, action)
        except ValueError as exc:
            return None, str(exc)
        entry[STATUS_FIELD] = state.status
        entry[PENDING_FIELD] = state.pending
        entry[ABNORMAL_FIELD] = state.abnormal
        return entry, f"配餐单已{action}"
