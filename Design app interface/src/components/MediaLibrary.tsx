import { useMemo, useState } from "react"
import type { MediaEntry } from "../data"
import { useApp } from "../state"
import { Button, Checkbox, FileBadge, Field, IconButton, Select, TextInput } from "./ui"
import { Icon } from "./icons"
import { LibraryProgress } from "./LibraryProgress"
import { DetailsDrawer } from "./DetailsDrawer"

type Filter = "全部" | "待下载" | "下载中" | "已完成" | "失败" | "缺少图片" | "缺少 NFO"
const FILTERS: Filter[] = ["全部", "待下载", "下载中", "已完成", "失败", "缺少图片", "缺少 NFO"]
const YEARS = Array.from({ length: new Date().getFullYear() - 1999 }, (_, i) => String(new Date().getFullYear() - i))
const MONTHS = Array.from({ length: 12 }, (_, i) => `${String(i + 1).padStart(2, "0")} 月`)

function matchesFilter(e: MediaEntry, f: Filter): boolean {
  switch (f) {
    case "全部": return true
    case "待下载": return e.video === "missing"
    case "下载中": return e.status === "downloading"
    case "已完成": return e.status === "completed"
    case "失败": return e.status === "failed"
    case "缺少图片": return e.image === "missing"
    case "缺少 NFO": return e.nfo === "missing"
  }
}

function Summary({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-[18px] font-medium leading-none" style={{ color: tone }}>{value}</span>
      <span className="text-[12px] text-muted-foreground">{label}</span>
    </div>
  )
}

export function MediaLibrary() {
  const { entries, tasks, year, month, monthDir, loading, selected, setSelected, setPeriod, refresh, chooseDirectory, openPath, enqueue, taskAction, notify } = useApp()
  const [filter, setFilter] = useState<Filter>("全部")
  const [query, setQuery] = useState("")
  const [activeId, setActiveId] = useState<string | null>(null)
  const activeMetadata = tasks.some(t => t.outputDir === monthDir && t.type === "NFO" && (t.state === "waiting" || t.state === "downloading"))
  const active = entries.find((entry) => entry.id === activeId) ?? null

  function run(operation: Promise<unknown>) {
    void operation.catch((error: unknown) => notify(error instanceof Error ? error.message : String(error)))
  }

  function retryEntry(id: string) {
    const failedTask = [...tasks].reverse().find((task) => task.entryId === id && task.state === "failed")
    return failedTask ? taskAction("retry", failedTask.id) : enqueue("video", [id])
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return entries.filter(
      (e) => matchesFilter(e, filter) && (!q || e.title.toLowerCase().includes(q) || e.code.toLowerCase().includes(q)),
    )
  }, [entries, filter, query])

  const stats = useMemo(() => ({
    total: entries.length,
    ready: entries.filter((e) => e.video === "ready").length,
    pending: entries.filter((e) => e.video === "missing").length,
    missing: entries.filter((e) => e.image === "missing" || e.nfo === "missing" || e.video === "missing").length,
  }), [entries])

  const allVisibleSelected = filtered.some(e => !e.isProcessingPlaceholder) && filtered.filter(e => !e.isProcessingPlaceholder).every((e) => selected.has(e.id))
  const someSelected = filtered.some((e) => selected.has(e.id))

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) filtered.forEach((e) => next.delete(e.id))
      else filtered.filter(e => !e.isProcessingPlaceholder).forEach((e) => next.add(e.id))
      return next
    })
  }
  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const count = selected.size
  const selectedIds = count > 0 ? Array.from(selected) : undefined
  const failedIds = entries.filter((entry) => selected.has(entry.id) && entry.status === "failed").map((entry) => entry.id)
  const downloadLabel = count > 0 ? `下载所选（${count}）` : "下载本月视频"

  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-end gap-3 border-b border-border bg-card px-5 py-3">
        <Field label="年份"><Select value={String(year)} options={YEARS} onChange={(value) => setPeriod(Number(value), month)} className="w-[92px]" /></Field>
        <Field label="月份"><Select value={`${String(month).padStart(2, "0")} 月`} options={MONTHS} onChange={(value) => setPeriod(year, Number.parseInt(value, 10))} className="w-[92px]" /></Field>
        <Field label="输出目录">
          <div title={monthDir} className="flex h-8 w-[min(280px,calc(100vw-5rem))] items-center rounded-[6px] border border-border-strong bg-panel px-2.5 font-mono text-[12px] text-muted-foreground">
            <span className="truncate">{monthDir || "尚未选择目录"}</span>
          </div>
        </Field>
        <Button variant="default" onClick={() => run(chooseDirectory())}><Icon.folder />选择目录</Button>
        <Button variant="default" disabled={!monthDir} onClick={() => run(openPath(monthDir))}><Icon.open />打开目录</Button>
        <div className="ml-auto flex items-end gap-2">
          <Button variant="default" disabled={loading} onClick={() => run(refresh())}><Icon.refresh />{loading ? "刷新中…" : "刷新"}</Button>
        </div>
      </div>

      {/* Summary + primary actions */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-border bg-panel px-5 py-2.5">
        <Summary label="条目总数" value={stats.total} tone="var(--foreground)" />
        <Summary label="视频已就绪" value={stats.ready} tone="var(--status-ready)" />
        <Summary label="待下载" value={stats.pending} tone="var(--status-pending)" />
        <Summary label="文件缺失" value={stats.missing} tone="var(--status-failed)" />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant="default" disabled={activeMetadata} onClick={() => { setFilter("全部"); setQuery(""); run(enqueue("metadata")) }}><Icon.image />{activeMetadata ? "正在获取图片与 NFO…" : "获取图片与 NFO"}</Button>
          <Button variant="default" disabled={entries.filter(e => !e.isProcessingPlaceholder).length === 0} onClick={() => run(enqueue("covers", selectedIds))}>重新下载封面</Button>
          <Button variant="primary" disabled={entries.filter(e => !e.isProcessingPlaceholder).length === 0} onClick={() => run(enqueue("video", selectedIds))}><Icon.download size={15} />{downloadLabel}</Button>
        </div>
      </div>

      <LibraryProgress />

      {/* Filters + search + batch */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-5 py-2.5">
        <div className="flex flex-wrap items-center gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={`rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors ${
                filter === f
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-[240px] max-w-full">
          <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"><Icon.search /></span>
          <TextInput value={query} onChange={setQuery} placeholder="搜索标题或编号" className="w-full pl-8" />
        </div>
      </div>

      {/* Batch bar (only when selection) */}
      {count > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-accent/60 px-5 py-2 text-[12px] text-accent-foreground">
          <span className="font-medium">已选择 {count} 项</span>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="default" size="sm" onClick={() => run(enqueue("video", selectedIds))}><Icon.download size={13} />下载所选（{count}）</Button>
            <Button variant="default" size="sm" disabled={failedIds.length === 0} onClick={() => run(Promise.all(failedIds.map(retryEntry)))}><Icon.retry />重试失败项</Button>
            <Button variant="default" size="sm" onClick={() => run(enqueue("repair", selectedIds))}>补齐缺失文件</Button>
          </div>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-muted-foreground hover:text-foreground">清除选择</button>
        </div>
      )}

      {/* Table */}
      <div className="min-h-0 flex-1 overflow-auto" aria-busy={loading}>
        {filtered.length === 0 ? (
          <EmptyResults query={query} emptyLibrary={entries.length === 0} loading={loading} />
        ) : (
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead className="sticky top-0 z-10 bg-panel text-[11px] text-muted-foreground">
              <tr className="border-b border-border">
                <th className="w-[44px] px-5 py-2"><Checkbox checked={allVisibleSelected} indeterminate={!allVisibleSelected && someSelected} onChange={toggleAll} /></th>
                <th className="w-[56px] py-2 font-medium">封面</th>
                <th className="py-2 font-medium">标题</th>
                <th className="w-[96px] py-2 font-medium"><span className="inline-flex items-center gap-1">分辨率<IconButton title="刷新本月分辨率" onClick={() => run(enqueue("resolutions"))}><Icon.refresh size={12} /></IconButton></span></th>
                <th className="w-[92px] py-2 font-medium">图片</th>
                <th className="w-[92px] py-2 font-medium">NFO</th>
                <th className="w-[104px] py-2 font-medium">视频</th>
                <th className="w-[150px] py-2 pr-5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr
                  key={e.id}
                  onClick={() => !e.isProcessingPlaceholder && setActiveId(e.id)}
                  className={`group cursor-pointer border-b border-border transition-colors hover:bg-secondary/50 ${
                    selected.has(e.id) ? "bg-accent/40" : ""
                  }`}
                >
                  <td className="px-5 py-2.5" onClick={(ev) => ev.stopPropagation()}>
                    {e.isProcessingPlaceholder ? <span className="text-muted-foreground">…</span> : <Checkbox checked={selected.has(e.id)} onChange={() => toggleOne(e.id)} />}
                  </td>
                  <td className="py-2.5">
                    <div className="flex h-[42px] w-[32px] items-center justify-center overflow-hidden rounded-[4px] border border-border bg-secondary text-muted-foreground">
                      {e.cover ? <img src={e.cover} alt="" loading="lazy" className="h-full w-full object-cover" /> : <Icon.image size={16} />}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4">
                    <button onClick={() => !e.isProcessingPlaceholder && setActiveId(e.id)} className="text-left text-[13px] font-medium text-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50">{e.title}</button>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{e.code}</div>
                  </td>
                  <td className="py-2.5" title={e.resolutionSource ?? "尚未获取到视频画质"}>
                    {e.resolution ? <span className="rounded-[4px] bg-accent px-2 py-1 font-mono text-[11px] font-medium text-accent-foreground">{e.resolution}</span> : <span className="text-[12px] text-muted-foreground">未知</span>}
                  </td>
                  <td className="py-2.5"><FileBadge state={e.image} /></td>
                  <td className="py-2.5"><FileBadge state={e.nfo} /></td>
                  <td className="py-2.5">
                    {e.video === "downloading" ? (
                      <div className="flex items-center gap-1.5 font-mono text-[11px] text-[color:var(--status-active)]">
                        {e.videoProgress === undefined ? "下载中" : `${Math.round(e.videoProgress)}%`}
                      </div>
                    ) : (
                      <FileBadge state={e.status === "pending" ? "pending" : e.video} />
                    )}
                  </td>
                  <td className="py-2.5 pr-5" onClick={(ev) => ev.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1 opacity-70 transition-opacity group-hover:opacity-100">
                      {e.status === "failed" ? (
                        <Button variant="default" size="sm" onClick={() => run(retryEntry(e.id))}><Icon.retry />重试</Button>
                      ) : e.video !== "ready" ? (
                        <Button variant="default" size="sm" disabled={e.status === "downloading"} onClick={() => run(enqueue("video", [e.id]))}><Icon.download size={13} />{e.status === "downloading" ? "下载中" : "下载"}</Button>
                      ) : (
                        <IconButton title="打开目录" onClick={() => run(openPath(e.paths.video.replace(/[\\/][^\\/]*$/, "") || monthDir))}><Icon.open size={15} /></IconButton>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <DetailsDrawer entry={active} onClose={() => setActiveId(null)} />
    </div>
  )
}

function EmptyResults({ query, emptyLibrary, loading }: { query: string; emptyLibrary: boolean; loading: boolean }) {
  return (
    <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-2 px-5 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary text-muted-foreground">
        <Icon.search size={22} />
      </div>
      <p className="text-[14px] font-medium text-foreground">{loading ? "正在读取媒体库…" : emptyLibrary ? "本月还没有媒体条目" : "未找到匹配的条目"}</p>
      <p className="text-[12px] text-muted-foreground">
        {loading ? "读取完成后将显示本月文件状态。" : emptyLibrary ? "点击“获取图片与 NFO”获取本月元数据，或选择已有媒体目录。" : query.trim() ? `没有与“${query}”匹配的结果，请尝试其他关键词或调整筛选条件。` : "当前筛选下没有条目，请调整筛选条件。"}
      </p>
    </div>
  )
}

export default MediaLibrary
