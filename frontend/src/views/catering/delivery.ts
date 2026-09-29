/**
 * 航空配餐「送达」口径（前端唯一实现）。
 *
 * 签收动作、列表展示、汇总统计三处的判断都从这里取，不再各写一份。
 * 与后端 app/services/catering_delivery.py 的常量与空值口径保持一致。
 */

export type CateringRow = Record<string, string | number | boolean | null>

export const ENDPOINT = '/api/catering'

// 列表列名、动作名、状态序列都只在这里定义一份，页面不再各自硬编码。
export const columns = [
  '配餐单号', '关联航班', '餐食份数', '餐食类别',
  '配餐车辆', '送达时刻', '接收人员', '配餐状态',
] as const

export const ACTION_DISPATCH = '安排配送'
export const ACTION_SIGN = '确认签收'
export const ACTION_CANCEL = '取消配送'
export const actions = [ACTION_DISPATCH, ACTION_SIGN, ACTION_CANCEL] as const

export const STATUS_PENDING = '待配送'
export const STATUS_DELIVERING = '配送中'
export const STATUS_SIGNED = '已签收'
export const STATUS_CANCELLED = '已取消'
export const statuses = [
  STATUS_PENDING, STATUS_DELIVERING, STATUS_SIGNED, STATUS_CANCELLED,
] as const

const STATUS_FIELD = 'status'
const PENDING_FIELD = 'pending'
const ABNORMAL_FIELD = 'abnormal'
const PORTIONS_FIELD = '餐食份数'

function statusOf(row: CateringRow): string {
  const value = row[STATUS_FIELD]
  return typeof value === 'string' ? value : ''
}

/** 已确认签收：动作判定、列表标记、汇总共用同一份。 */
export function isSigned(row: CateringRow): boolean {
  return statusOf(row) === STATUS_SIGNED
}

/** 已取消配送。 */
export function isCancelled(row: CateringRow): boolean {
  return statusOf(row) === STATUS_CANCELLED
}

/** 已送达：取消配送不算，只有确认签收才算。 */
export function isDelivered(row: CateringRow): boolean {
  return isSigned(row)
}

/** 待处理：与动作写入口径一致（取消配送后不待处理，已签收仍待处理）。 */
export function isPending(row: CateringRow): boolean {
  return !isCancelled(row)
}

/** 读取既有配餐单时的待处理标记：有历史标记以原值为准，不改动历史数据。 */
export function pendingFlag(row: CateringRow): boolean {
  return PENDING_FIELD in row ? Boolean(row[PENDING_FIELD]) : isPending(row)
}

/** 读取既有配餐单时的异常标记，历史值优先；新行没有异常动作，缺省为 false。 */
export function abnormalFlag(row: CateringRow): boolean {
  return ABNORMAL_FIELD in row ? Boolean(row[ABNORMAL_FIELD]) : false
}

/**
 * 文本/数字字段的统一读法：null/undefined、空串、纯空白、数值 0 归一为 null；
 * 非空字符串去首尾空白；非 0 数字原样返回。
 * 判空口径与后端 str(value || '').trim() 一致。
 */
export function cleanValue(value: unknown): string | number | boolean | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') {
    const text = value.trim()
    return text.length ? text : null
  }
  if (typeof value === 'number') return value === 0 ? null : value
  if (typeof value === 'boolean') return value ? true : null
  return value ? (value as string | number) : null
}

/** 接收人员的统一写法。 */
export function receiverName(value: unknown): string | number | boolean | null {
  return cleanValue(value)
}

/** 餐食份数的统一读法：空份数（含 0、空串、纯空白）为 null，非空保留原值。 */
export function portionValue(value: unknown): string | number | boolean | null {
  return cleanValue(value)
}

/**
 * 列表单元格的统一展示：与原模板 row[column] ?? '—' 完全等价——
 * null/undefined 显示「—」，其余值（含空串）原样展示。
 * 空值归一发生在签收/汇总口径（cleanValue）里，列表渲染不改变原有结果。
 */
export function formatCell(row: CateringRow, column: string): string | number | boolean {
  const value = row[column]
  return value === null || value === undefined ? '—' : value
}

function numericPortions(value: unknown): number {
  const cleaned = portionValue(value)
  return typeof cleaned === 'number' ? cleaned : 0
}

export interface CateringSummary {
  created: number
  pending: number
  abnormal: number
  signed: number
  cancelled: number
  totalPortions: number
}

/** 配餐汇总的唯一口径，与后端 catering_delivery.summarize 对齐。 */
export function summarize(rows: CateringRow[]): CateringSummary {
  return {
    created: rows.length,
    pending: rows.filter(pendingFlag).length,
    abnormal: rows.filter(abnormalFlag).length,
    signed: rows.filter(isSigned).length,
    cancelled: rows.filter(isCancelled).length,
    totalPortions: rows.reduce(
      (sum, row) => sum + numericPortions(row[PORTIONS_FIELD]), 0,
    ),
  }
}
