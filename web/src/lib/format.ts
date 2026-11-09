export const errorText = (error: unknown): string =>
  error instanceof Error ? error.message : String(error)

export const messageOf = errorText

/** 2026-11-09T12:09 → 2026-11-09 12:09 */
export const isoText = (iso?: string | null): string =>
  iso ? iso.replace("T", " ") : "—"

export const timeText = (ts?: number | null): string =>
  ts
    ? new Date(ts * 1000).toLocaleString("zh-CN", {
        hour12: false,
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : ""

export const unitLabel = (unit: string): string =>
  unit === "minute" ? "分钟" : unit === "hour" ? "小时" : "天"

export const pad2 = (value: number): string => String(value).padStart(2, "0")

/** 剧集列表压缩成区间文案：1–12 共 12 集 */
export function episodeRange(list: number[]): string {
  if (list.length === 0) return "暂无集数信息"
  const sorted = [...list].sort((a, b) => a - b)
  return sorted.length > 1
    ? `${sorted[0]}–${sorted[sorted.length - 1]} 共 ${sorted.length} 集`
    : `第 ${sorted[0]} 集`
}

export const episodeTag = (episode: number): string => `E${pad2(episode)}`

export const clampInt = (value: unknown, min: number, max: number, fallback: number): number => {
  const number = typeof value === "number" && Number.isFinite(value) ? Math.round(value) : NaN
  return Number.isInteger(number) && number >= min && number <= max ? number : fallback
}

export const parentDir = (path: string): string => path.replace(/[\\/][^\\/]*$/, "")
