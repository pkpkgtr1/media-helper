import { useMemo, useState } from "react"
import { useApp } from "../../state"
import { Button, Checkbox, FileBadge, IconButton, ProgressBar } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { parentDir } from "../../lib/format"
import type { MediaEntry } from "../../lib/types"
import { FilterBar, Toolbar } from "./Toolbar"
import { ProgressPanel } from "./ProgressPanel"
import { DetailsPanel } from "./DetailsPanel"

type Filter = "全部" | "待下载" | "下载中" | "已完成" | "失败" | "缺少图片" | "缺少 NFO"

function matches(entry: MediaEntry, filter: Filter): boolean {
  switch (filter) {
    case "全部":
      return true
    case "待下载":
      return entry.video === "missing"
    case "下载中":
      return entry.status === "downloading"
    case "已完成":
      return entry.status === "completed"
    case "失败":
      return entry.status === "failed"
    case "缺少图片":
      return entry.image === "missing"
    case "缺少 NFO":
      return entry.nfo === "missing"
  }
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-mono text-[17px] leading-none font-semibold" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      <span className="text-[12px] text-muted-fg">{label}</span>
    </div>
  )
}

export function LibraryScreen() {
  const {
    entries,
    tasks,
    monthDir,
    loading,
    selected,
    setSelected,
    refresh,
    chooseDirectory,
    openPath,
    enqueue,
    taskAction,
  } = useApp()
  const [filter, setFilter] = useState<Filter>("全部")
  const [query, setQuery] = useState("")
  const [activeId, setActiveId] = useState<string | null>(null)

  const active = entries.find((entry) => entry.id === activeId) ?? null
  const metadataRunning = tasks.some(
    (task) =>
      task.outputDir === monthDir &&
      task.type === "NFO" &&
      (task.state === "waiting" || task.state === "downloading"),
  )

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return entries.filter(
      (entry) =>
        matches(entry, filter) &&
        (!keyword ||
          entry.title.toLowerCase().includes(keyword) ||
          entry.code.toLowerCase().includes(keyword)),
    )
  }, [entries, filter, query])

  const counts = useMemo(() => {
    const names: Filter[] = ["全部", "待下载", "下载中", "已完成", "失败", "缺少图片", "缺少 NFO"]
    return Object.fromEntries(
      names.map((name) => [name, entries.filter((entry) => matches(entry, name)).length]),
    ) as Record<string, number>
  }, [entries])

  const stats = useMemo(
    () => ({
      total: entries.length,
      ready: entries.filter((entry) => entry.video === "ready").length,
      pending: entries.filter((entry) => entry.video === "missing").length,
      missing: entries.filter(
        (entry) => entry.image === "missing" || entry.nfo === "missing" || entry.video === "missing",
      ).length,
    }),
    [entries],
  )

  const selectable = filtered.filter((entry) => !entry.isProcessingPlaceholder)
  const allVisibleSelected = selectable.length > 0 && selectable.every((entry) => selected.has(entry.id))
  const someSelected = selectable.some((entry) => selected.has(entry.id))

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) selectable.forEach((entry) => next.delete(entry.id))
      else selectable.forEach((entry) => next.add(entry.id))
      return next
    })
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function retryEntry(id: string) {
    const failed = [...tasks].reverse().find((task) => task.entryId === id && task.state === "failed")
    void (failed ? taskAction("retry", failed.id) : enqueue("video", [id]))
  }

  const count = selected.size
  const selectedIds = count > 0 ? [...selected] : undefined
  const failedIds = entries.filter((entry) => selected.has(entry.id) && entry.status === "failed").map((e) => e.id)
  const hasEntries = entries.some((entry) => !entry.isProcessingPlaceholder)

  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <Toolbar onPickDirectory={() => void chooseDirectory()} />

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-line bg-panel px-4 py-2.5">
        <Stat label="条目总数" value={stats.total} tone="var(--fg)" />
        <Stat label="视频已就绪" value={stats.ready} tone="var(--ready)" />
        <Stat label="待下载" value={stats.pending} tone="var(--pending)" />
        <Stat label="文件缺失" value={stats.missing} tone="var(--failed)" />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button
            disabled={metadataRunning}
            onClick={() => {
              setFilter("全部")
              setQuery("")
              void enqueue("metadata")
            }}
          >
            <Icon.image size={15} />
            {metadataRunning ? "正在获取图片与 NFO…" : "获取图片与 NFO"}
          </Button>
          <Button disabled={!hasEntries} onClick={() => void enqueue("covers", selectedIds)}>
            <Icon.refresh size={15} />
            重新下载封面
          </Button>
          <Button variant="accent" disabled={!hasEntries} onClick={() => void enqueue("video", selectedIds)}>
            <Icon.download size={15} />
            {count > 0 ? `下载所选（${count}）` : "下载本月视频"}
          </Button>
        </div>
      </div>

      <ProgressPanel />

      <FilterBar filter={filter} onFilter={(v) => setFilter(v as Filter)} query={query} onQuery={setQuery} counts={counts} />

      {count > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-accent-soft px-4 py-2 text-[12px] text-accent">
          <span className="font-medium">已选择 {count} 项</span>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => void enqueue("video", selectedIds)}>
              <Icon.download size={13} />
              下载所选（{count}）
            </Button>
            <Button
              size="sm"
              disabled={failedIds.length === 0}
              onClick={() => failedIds.forEach((id) => retryEntry(id))}
            >
              <Icon.retry size={13} />
              重试失败项
            </Button>
            <Button size="sm" onClick={() => void enqueue("repair", selectedIds)}>
              补齐缺失文件
            </Button>
          </div>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="ml-auto cursor-pointer text-accent transition-opacity hover:opacity-75"
          >
            清除选择
          </button>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto" aria-busy={loading}>
        {filtered.length === 0 ? (
          <EmptyResults query={query} emptyLibrary={entries.length === 0} loading={loading} onRefresh={() => void refresh()} />
        ) : (
          <table className="w-full min-w-[820px] border-collapse text-left">
            <thead className="sticky top-0 z-10 bg-panel text-[11px] tracking-wide text-muted-fg uppercase">
              <tr className="border-b border-line">
                <th className="w-[42px] px-4 py-2">
                  <Checkbox
                    checked={allVisibleSelected}
                    indeterminate={!allVisibleSelected && someSelected}
                    onChange={toggleAll}
                    label="全选当前筛选结果"
                  />
                </th>
                <th className="w-[52px] py-2 font-medium">封面</th>
                <th className="py-2 font-medium">标题</th>
                <th className="w-[104px] py-2 font-medium">
                  <span className="inline-flex items-center gap-1">
                    分辨率
                    <IconButton title="刷新本月分辨率" onClick={() => void enqueue("resolutions")}>
                      <Icon.refresh size={12} />
                    </IconButton>
                  </span>
                </th>
                <th className="w-[88px] py-2 font-medium">图片</th>
                <th className="w-[88px] py-2 font-medium">NFO</th>
                <th className="w-[100px] py-2 font-medium">视频</th>
                <th className="w-[136px] py-2 pr-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, index) => (
                <tr
                  key={entry.id}
                  onClick={() => !entry.isProcessingPlaceholder && setActiveId(entry.id)}
                  style={{ animationDelay: `${Math.min(index, 12) * 18}ms` }}
                  className={`group rise-in border-b border-line transition-colors duration-150 ${
                    entry.isProcessingPlaceholder ? "" : "cursor-pointer hover:bg-elevated/70"
                  } ${selected.has(entry.id) ? "bg-accent-soft/50" : ""}`}
                >
                  <td className="px-4 py-2.5" onClick={(event) => event.stopPropagation()}>
                    {entry.isProcessingPlaceholder ? (
                      <span className="text-muted-fg">…</span>
                    ) : (
                      <Checkbox
                        checked={selected.has(entry.id)}
                        onChange={() => toggleOne(entry.id)}
                        label={`选择 ${entry.title}`}
                      />
                    )}
                  </td>
                  <td className="py-2.5">
                    <div className="flex h-[42px] w-[30px] items-center justify-center overflow-hidden rounded-[4px] border border-line bg-elevated text-muted-fg">
                      {entry.cover ? (
                        <img src={entry.cover} alt="" loading="lazy" className="h-full w-full object-cover" />
                      ) : (
                        <Icon.image size={15} />
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        if (!entry.isProcessingPlaceholder) setActiveId(entry.id)
                      }}
                      className="cursor-pointer text-left text-[13px] font-medium text-fg transition-colors hover:text-accent"
                    >
                      {entry.title}
                    </button>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-fg">{entry.code}</div>
                  </td>
                  <td className="py-2.5" title={entry.resolutionSource ?? "尚未获取到视频画质"}>
                    {entry.resolution ? (
                      <span className="rounded-[4px] bg-elevated px-2 py-1 font-mono text-[11px] font-medium text-fg">
                        {entry.resolution}
                      </span>
                    ) : (
                      <span className="text-[12px] text-muted-fg">未知</span>
                    )}
                  </td>
                  <td className="py-2.5">
                    <FileBadge state={entry.image} />
                  </td>
                  <td className="py-2.5">
                    <FileBadge state={entry.nfo} />
                  </td>
                  <td className="py-2.5">
                    {entry.video === "downloading" ? (
                      <div className="w-[72px] space-y-1">
                        <span className="font-mono text-[11px] text-active">
                          {entry.videoProgress === undefined ? "下载中" : `${Math.round(entry.videoProgress)}%`}
                        </span>
                        <ProgressBar
                          value={entry.videoProgress ?? 0}
                          indeterminate={entry.videoProgress === undefined}
                          label={`${entry.title} 下载进度`}
                        />
                      </div>
                    ) : (
                      <FileBadge state={entry.status === "pending" ? "pending" : entry.video} />
                    )}
                  </td>
                  <td className="py-2.5 pr-4" onClick={(event) => event.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1 opacity-70 transition-opacity duration-150 group-hover:opacity-100">
                      {entry.status === "failed" ? (
                        <Button size="sm" onClick={() => retryEntry(entry.id)}>
                          <Icon.retry size={13} />
                          重试
                        </Button>
                      ) : entry.video !== "ready" ? (
                        <Button
                          size="sm"
                          disabled={entry.status === "downloading"}
                          onClick={() => void enqueue("video", [entry.id])}
                        >
                          <Icon.download size={13} />
                          {entry.status === "downloading" ? "下载中" : "下载"}
                        </Button>
                      ) : (
                        <IconButton
                          title="打开目录"
                          onClick={() => void openPath(parentDir(entry.paths.video) || monthDir)}
                        >
                          <Icon.open size={15} />
                        </IconButton>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <DetailsPanel entry={active} onClose={() => setActiveId(null)} />
    </div>
  )
}

function EmptyResults({
  query,
  emptyLibrary,
  loading,
  onRefresh,
}: {
  query: string
  emptyLibrary: boolean
  loading: boolean
  onRefresh: () => void
}) {
  const title = loading ? "正在读取媒体库…" : emptyLibrary ? "本月还没有媒体条目" : "未找到匹配的条目"
  const detail = loading
    ? "读取完成后将显示本月文件状态。"
    : emptyLibrary
      ? "点击“获取图片与 NFO”抓取本月元数据，或在设置里换一个输出目录。"
      : query.trim()
        ? `没有与“${query}”匹配的结果，请尝试其他关键词或调整筛选条件。`
        : "当前筛选下没有条目，请调整筛选条件。"

  return (
    <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-2 px-5 py-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-muted-fg">
        <Icon.search size={22} />
      </div>
      <p className="text-[14px] font-medium text-fg">{title}</p>
      <p className="max-w-[420px] text-[12px] leading-relaxed text-muted-fg">{detail}</p>
      {!loading ? (
        <Button size="sm" className="mt-1" onClick={onRefresh}>
          <Icon.refresh size={13} />
          重新读取
        </Button>
      ) : null}
    </div>
  )
}
