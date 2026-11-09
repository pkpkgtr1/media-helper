/** 默认月份：上个月（媒体库通常处理已完结的上一月）。 */
export function initialPeriod(): { year: number; month: number } {
  const date = new Date()
  date.setDate(1)
  date.setMonth(date.getMonth() - 1)
  return { year: date.getFullYear(), month: date.getMonth() + 1 }
}
