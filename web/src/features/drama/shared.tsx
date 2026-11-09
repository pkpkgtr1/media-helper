import { useEffect, useState } from "react"
import { Icon } from "../../components/ui/icons"
import { episodeTag, unitLabel } from "../../lib/format"

export type SourceKey = "huangguo" | "yeguo"

export const SOURCE_FALLBACK: { key: SourceKey; label: string }[] = [
  { key: "huangguo", label: "黄果短剧" },
  { key: "yeguo", label: "野果短剧" },
]

/** 两个源可能用相同数字 id，订阅态与封面都要带上源区分。 */
export const sourceKeyOf = (item: { source?: string }): SourceKey =>
  item.source === "yeguo" ? "yeguo" : "huangguo"

export const sourceLabelOf = (item: { source?: string; sourceLabel?: string }): string =>
  item.sourceLabel ??
  SOURCE_FALLBACK.find((source) => source.key === sourceKeyOf(item))?.label ??
  "黄果短剧"

export const itemKey = (item: { id: string; source?: string }): string =>
  `${sourceKeyOf(item)}:${item.id}`

export const coverSrc = (url: string, source?: string): string =>
  url ? `/api/hg/image?url=${encodeURIComponent(url)}&source=${sourceKeyOf({ source })}` : ""

export const STATE_LABELS: Record<string, string> = {
  waiting: "等待中",
  checking: "检查中",
  downloading: "下载中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  skipped: "跳过",
}

export function badgeKind(state: string): "ready" | "failed" | "missing" | "pending" | "active" {
  if (state === "completed") return "ready"
  if (state === "failed") return "failed"
  if (state === "cancelled") return "missing"
  if (state === "waiting" || state === "skipped") return "pending"
  return "active"
}

/** 来源角标：野果用强调色，黄果用中性色，一眼区分。 */
export function SourceBadge({ item }: { item: { source?: string; sourceLabel?: string } }) {
  const yeguo = sourceKeyOf(item) === "yeguo"
  return (
    <span
      className={`inline-flex h-4 shrink-0 items-center rounded-full px-2 text-[11px] leading-none font-medium ${
        yeguo ? "bg-active-soft text-active" : "bg-elevated text-muted-fg"
      }`}
    >
      {sourceLabelOf(item)}
    </span>
  )
}

/** 封面：加载失败时回落到占位图标。 */
export function Cover({
  src,
  title,
  className = "",
}: {
  src: string
  title: string
  className?: string
}) {
  const [failed, setFailed] = useState(!src)
  useEffect(() => setFailed(!src), [src])
  return (
    <div
      className={`flex items-center justify-center overflow-hidden rounded-md border border-line bg-elevated text-muted-fg ${className}`}
    >
      {failed ? (
        <Icon.image size={18} />
      ) : (
        <img
          src={src}
          alt={`${title} 封面`}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      )}
    </div>
  )
}

/** 集数选择器：可多选，键盘可达。 */
export function EpisodePicker({
  options,
  picked,
  onPick,
}: {
  options: number[]
  picked: number[]
  onPick: (list: number[]) => void
}) {
  if (options.length === 0) {
    return <p className="py-2 text-[12px] text-muted-fg">暂无可选集数。</p>
  }
  return (
    <div className="flex max-h-[200px] flex-wrap gap-1.5 overflow-y-auto p-0.5">
      {options.map((episode) => {
        const active = picked.includes(episode)
        return (
          <button
            key={episode}
            type="button"
            aria-pressed={active}
            onClick={() =>
              onPick(
                active
                  ? picked.filter((value) => value !== episode)
                  : [...picked, episode].sort((a, b) => a - b),
              )
            }
            className={`h-7 min-w-[44px] cursor-pointer rounded-md border px-2 font-mono text-[12px] transition-colors duration-150 ${
              active
                ? "border-accent bg-accent text-accent-fg"
                : "border-line-strong bg-card text-fg hover:bg-elevated"
            }`}
          >
            {episodeTag(episode)}
          </button>
        )
      })}
    </div>
  )
}

export const intervalHint = (value: number, unit: string): string =>
  `每 ${value} ${unitLabel(unit)}检查`
