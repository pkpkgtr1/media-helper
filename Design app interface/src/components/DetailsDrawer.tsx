import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react"
import type { MediaEntry } from "../data"
import { useApp } from "../state"
import { Button, FileBadge, IconButton } from "./ui"
import { Icon } from "./icons"

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[92px_1fr] gap-3 py-2.5">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className="min-w-0 text-[13px] text-foreground">{children}</div>
    </div>
  )
}

function Tags({ items, muted }: { items: string[]; muted?: boolean }) {
  if (items.length === 0) return <span className="text-[12px] text-muted-foreground">无</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((c) => (
        <span
          key={c}
          className={`rounded-[4px] px-1.5 py-[2px] text-[12px] ${
            muted
              ? "bg-secondary text-muted-foreground line-through"
              : "bg-accent text-accent-foreground"
          }`}
        >
          {c}
        </span>
      ))}
    </div>
  )
}

export function DetailsDrawer({
  entry,
  onClose,
}: {
  entry: MediaEntry | null
  onClose: () => void
}) {
  const { enqueue, tasks, taskAction, openPath, monthDir, notify } = useApp()
  const drawerRef = useRef<HTMLElement>(null)
  const entryId = entry?.id
  const excluded = entry
    ? entry.originalCategories.filter((c) => !entry.exportedCategories.includes(c))
    : []

  useEffect(() => {
    if (!entryId) return
    const previousFocus = document.activeElement
    drawerRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [entryId])

  function run(operation: Promise<unknown>) {
    void operation.catch((error: unknown) => notify(error instanceof Error ? error.message : String(error)))
  }

  function downloadOrRetry() {
    if (!entry) return
    const failedTask = entry.status === "failed"
      ? [...tasks].reverse().find((task) => task.entryId === entry.id && task.state === "failed")
      : undefined
    run(failedTask ? taskAction("retry", failedTask.id) : enqueue("video", [entry.id]))
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault()
      onClose()
    } else if (event.key === "Tab") {
      const controls = drawerRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex='0']")
      if (!controls?.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  return (
    <>
      <div
        onClick={onClose}
        className={`absolute inset-0 z-20 bg-foreground/20 transition-opacity duration-200 ${
          entry ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal={entry ? true : undefined}
        aria-hidden={!entry}
        aria-labelledby={entry ? "media-details-title" : undefined}
        onKeyDown={handleKeyDown}
        className={`absolute right-0 top-0 z-30 flex h-full w-[420px] max-w-full flex-col border-l border-border bg-card shadow-xl transition-transform duration-200 ${
          entry ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {entry && (
          <>
            <header className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[12px] text-muted-foreground">{entry.code}</span>
              </div>
              <IconButton title="关闭" onClick={onClose}>
                <Icon.close />
              </IconButton>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <div className="flex gap-3.5">
                <div className="flex h-[128px] w-[96px] shrink-0 items-center justify-center overflow-hidden rounded-[6px] border border-border bg-secondary text-muted-foreground">
                  {entry.cover ? <img src={entry.cover} alt={`${entry.title} 封面`} className="h-full w-full object-cover" /> : <Icon.image size={32} />}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 id="media-details-title" className="break-words text-[15px] font-medium leading-snug text-foreground">{entry.title}</h2>
                  <p className="mt-2 break-words text-[12px] leading-relaxed text-muted-foreground">{entry.description || "暂无简介"}</p>
                </div>
              </div>

              <div className="mt-4 flex gap-1.5">
                <div className="flex flex-1 flex-col items-center gap-1 rounded-[6px] border border-border bg-panel py-2">
                  <span className="text-[11px] text-muted-foreground">图片</span>
                  <FileBadge state={entry.image} />
                </div>
                <div className="flex flex-1 flex-col items-center gap-1 rounded-[6px] border border-border bg-panel py-2">
                  <span className="text-[11px] text-muted-foreground">NFO</span>
                  <FileBadge state={entry.nfo} />
                </div>
                <div className="flex flex-1 flex-col items-center gap-1 rounded-[6px] border border-border bg-panel py-2">
                  <span className="text-[11px] text-muted-foreground">视频</span>
                  <FileBadge state={entry.video} />
                </div>
              </div>

              <div className="mt-4 divide-y divide-border border-t border-border">
                <Row label="编号">
                  <span className="font-mono">{entry.code}</span>
                </Row>
                <Row label={entry.originalCategoriesAvailable === false ? "已有分类" : "原始分类"}>
                  <Tags items={entry.originalCategories} />
                  {entry.originalCategoriesAvailable === false && <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">历史记录未保存完整原始分类，已删除的分类无法从现有文件恢复。</p>}
                </Row>
                <Row label="写入分类">
                  <Tags items={entry.exportedCategories} />
                </Row>
                {excluded.length > 0 && (
                  <Row label="已排除">
                    <Tags items={excluded} muted />
                  </Row>
                )}
                <Row label="视频路径">
                  <span className="break-all font-mono text-[12px] text-muted-foreground">{entry.paths.video || "尚未生成"}</span>
                </Row>
                <Row label="NFO 路径">
                  <span className="break-all font-mono text-[12px] text-muted-foreground">{entry.paths.nfo || "尚未生成"}</span>
                </Row>
                <Row label="封面路径">
                  <span className="break-all font-mono text-[12px] text-muted-foreground">{entry.paths.cover || "尚未生成"}</span>
                </Row>
              </div>

              {entry.error && (
                <div className="mt-4 flex gap-2 rounded-[6px] border border-[color:var(--status-failed-bg)] bg-[color:var(--status-failed-bg)] px-3 py-2.5 text-[color:var(--status-failed)]">
                  <span className="mt-[1px] shrink-0"><Icon.warn size={15} /></span>
                  <div className="min-w-0 break-words">
                    <div className="text-[12px] font-medium">错误详情</div>
                    <div className="mt-0.5 text-[12px] leading-relaxed">{entry.error}</div>
                  </div>
                </div>
              )}
            </div>
            <footer className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
              <Button variant="primary" size="sm" disabled={entry.status === "downloading" || (entry.video === "ready" && entry.status !== "failed")} onClick={downloadOrRetry}>
                {entry.status === "failed" ? <Icon.retry /> : <Icon.download size={14} />}
                {entry.status === "failed" ? "重试任务" : entry.video === "ready" ? "视频已就绪" : entry.status === "downloading" ? "下载中" : "下载视频"}
              </Button>
              <Button variant="default" size="sm" disabled={!entry.paths.video && !monthDir} onClick={() => run(openPath(entry.paths.video.replace(/[\\/][^\\/]*$/, "") || monthDir))}><Icon.open size={14} />打开目录</Button>
            </footer>
          </>
        )}
      </aside>
    </>
  )
}

export default DetailsDrawer
