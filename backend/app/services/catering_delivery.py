"""航空配餐「送达」口径：签收动作、列表展示、汇总统计共用的唯一一份实现。

之前同一件事在三处各写了一份判断（签收动作里看状态映射、列表里各自过滤、
汇总里数标记），餐食份数/餐食类别为空时三处处理不一样，接收人员的写法也
不统一。本模块只放常量和纯函数，不碰数据仓库；三条链路都调这里，
不再各写分支。

约定：
- 状态判断只认 entry 的 ``status`` 字段。
- 空值统一判法：None、空串、纯空白、数值 0 都算空（与登记时必填校验
  历来的写法一致：``str(value or "").strip()``）。
- 接收人员、餐食份数、餐食类别的读法统一在 clean_text 一处。
"""
from __future__ import annotations

from typing import Any

MODULE = "catering"

REQUIRED_FIELDS = ["配餐单号", "关联航班", "餐食份数"]
# 列表列名的唯一出处；餐食份数、餐食类别、接收人员都在这组字段里，
# 路由层与前端不再各自维护一份。
LIST_FIELDS = ["配餐单号", "关联航班", "餐食份数", "餐食类别", "配餐车辆", "送达时刻", "接收人员", "配餐状态"]
RECEIVER_FIELD = "接收人员"
PORTIONS_FIELD = "餐食份数"
CATEGORY_FIELD = "餐食类别"

STATUS_PENDING = "待配送"
STATUS_DELIVERING = "配送中"
STATUS_SIGNED = "已签收"
STATUS_CANCELLED = "已取消"
STATUS_ORDER = [STATUS_PENDING, STATUS_DELIVERING, STATUS_SIGNED, STATUS_CANCELLED]

ACTION_DISPATCH = "安排配送"
ACTION_SIGN = "确认签收"
ACTION_CANCEL = "取消配送"
ACTION_RULES = {
    ACTION_DISPATCH: STATUS_DELIVERING,
    ACTION_SIGN: STATUS_SIGNED,
    ACTION_CANCEL: STATUS_CANCELLED,
}
NEGATIVE_ACTIONS: list[str] = []

STATUS_FIELD = "status"
PENDING_FIELD = "pending"
ABNORMAL_FIELD = "abnormal"


def status_of(entry: dict[str, Any]) -> str:
    """取配餐单状态；缺字段或不是字符串时按空状态处理，不误判为已签收/已取消。"""
    status = entry.get(STATUS_FIELD)
    return status if isinstance(status, str) else ""


def is_signed(entry: dict[str, Any]) -> bool:
    """是否已确认签收——签收动作、列表筛选、汇总共用这一份判断。"""
    return status_of(entry) == STATUS_SIGNED


def is_cancelled(entry: dict[str, Any]) -> bool:
    """是否已取消配送。"""
    return status_of(entry) == STATUS_CANCELLED


def is_delivered(entry: dict[str, Any]) -> bool:
    """是否已送达：取消配送不算送达，只有确认签收才算。"""
    return is_signed(entry)


def is_pending(entry: dict[str, Any]) -> bool:
    """动作写入口径下是否仍待处理：取消配送后不待处理，其余状态（含已签收）都待处理。

    与 run_action 历来的写入规则保持一致：pending = status != 已取消。
    """
    return not is_cancelled(entry)


def is_abnormal(entry: dict[str, Any]) -> bool:
    """异常量口径：配餐三个动作都不算异常，动作链路与汇总统一返回 False。"""
    return False


def pending_flag(entry: dict[str, Any]) -> bool:
    """读取既有配餐单时的待处理标记：行里已有标记的以原值为准，不许改动历史数据；
    没有标记（新行）时回到 is_pending 的统一口径。"""
    if PENDING_FIELD in entry:
        return bool(entry[PENDING_FIELD])
    return is_pending(entry)


def abnormal_flag(entry: dict[str, Any]) -> bool:
    """读取既有配餐单时的异常标记，同样保留行内历史值，缺省回统一口径。"""
    if ABNORMAL_FIELD in entry:
        return bool(entry[ABNORMAL_FIELD])
    return is_abnormal(entry)


def clean_text(value: Any) -> Any:
    """文本/数字字段的统一读法：None、空串、纯空白、数值 0 归一为 None；
    非空字符串去首尾空白；其余值（如数字 5）原样返回。

    判空口径与登记必填校验历来的 ``str(value or "").strip()`` 完全一致：
    False、空容器等假值同样算空。
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    text = str(value or "").strip()
    if not text:
        return None
    return value


def receiver_name(value: Any) -> Any:
    """接收人员的统一写法。"""
    return clean_text(value)


def portion_text(value: Any) -> Any:
    """餐食份数的统一读法：空份数（含 0、空串、纯空白）为 None，非空保留原值。"""
    return clean_text(value)


def category_text(value: Any) -> Any:
    """餐食类别的统一读法，与餐食份数同一套空值处理。"""
    return clean_text(value)


def empty_required(values: dict[str, Any]) -> list[str]:
    """登记必填校验：按字段顺序列出为空（None/空白/0）的必填项。"""
    return [field for field in REQUIRED_FIELDS if clean_text(values.get(field)) is None]


def target_status(action: str) -> str | None:
    """动作到目标状态的唯一映射；不认识的动作返回 None，由调用方给错误提示。"""
    return ACTION_RULES.get(action)


def _numeric(value: Any) -> int | float:
    """把餐食份数转成可累加的数值；非数字（含 None、布尔、样例文本）一律按 0。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value


def summarize(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    """配餐汇总的唯一口径（纯函数）：运营概览、页面统计都取这一份。

    - created：配餐单总数；
    - pending/abnormal：既有单据按行内历史标记保留（不许改动历史数据），
      没有标记的新行回 is_pending/is_abnormal 统一口径；
    - signed/cancelled：签收、取消配送单数，全部走 is_signed/is_cancelled；
    - total_portions：餐食份数合计，空份数（None/空白/0/非数字）按 0 处理。
    """
    return {
        "created": len(rows),
        "pending": sum(1 for row in rows if pending_flag(row)),
        "abnormal": sum(1 for row in rows if abnormal_flag(row)),
        "signed": sum(1 for row in rows if is_signed(row)),
        "cancelled": sum(1 for row in rows if is_cancelled(row)),
        "total_portions": sum(
            _numeric(portion_text(row.get(PORTIONS_FIELD))) for row in rows
        ),
    }
