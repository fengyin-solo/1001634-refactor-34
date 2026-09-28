export type Row = Record<string, string | number | boolean | null>

export const ENDPOINT = '/api/catering'
export const columns = [
  '配餐单号',
  '关联航班',
  '餐食份数',
  '餐食类别',
  '配餐车辆',
  '送达时刻',
  '接收人员',
  '配餐状态',
] as const

export const actions = ['安排配送', '确认签收', '取消配送'] as const
export const statuses = ['待配送', '配送中', '已签收', '已取消'] as const

type SummaryCard = { label: string; value: number }

const summaryCards: SummaryCard[] = [
  { label: '待配送配餐', value: 0 },
  { label: '本月配餐份数', value: 0 },
  { label: '取消单数', value: 0 },
]

export function displayDeliveryCell(row: Row, column: string): string | number | boolean {
  const value = row[column]
  return value ?? '—'
}

export function deliveryActionBody(action: string): string {
  return JSON.stringify({ action })
}

export function deliverySummaryCards(): SummaryCard[] {
  return summaryCards
}
