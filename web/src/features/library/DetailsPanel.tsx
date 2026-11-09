import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react"
import { useApp } from "../../state"
import { Button, FileBadge, IconButton } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { parentDir } from "../../lib/format"
import type { MediaEntry } from "../../lib/types"

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-3 border-b border-line py-2.5 last:border-0">
      <div className="text-[12px] text-muted-fg">{label}</div>
      <div className="min-w-0 text-[13px] text-fg">{children}</div>
    </div>
  )
}

function Tags({ items, muted }: { items: string[]; muted?: boolean }) {
  if (items.length === 0) return <span className="text-[12px] text-muted-fg">无</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((name) => (
        <span
          key={name}
          className={`rounded-[4px] px-1.5 py-[2px] text-[12px] ${
            muted ? "bg-elevated text-muted-fg line-through" : "bg-accent-soft text-accent"
          }`}
        >
          {name}
        </span>
      ))}
    </div>
  )
}

/** 条目详情抽屉：右侧滑出，带遮罩、焦点管理与 Esc 关闭。 */
export function DetailsPanel({ entry, onClose }: { entry: MediaEntry | null; onClose: () => void }) {
  const { enqueue, tasks, taskAction, openPath, monthDir } = useApp()
  const drawerRef = useRef<HTMLElement>(null)
  const entryId = entry?.id
  const excluded = entry
    ? entry.originalCategories.filter((name) => !entry.exportedCategories.includes(name))
    : []

  useEffect(() => {
    if (!entryId) return
    const previous = document.activeElement
    drawerRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    }
  }, [entryId])

  function downloadOrRetry() {
    if (!entry) return
    const failed =
      entry.status === "failed"
        ? [...tasks].reverse().find((task) => task.entryId === entry.id && task.state === "failed")
        : undefined
    if (failed) void taskAction("retry", failed.id)
    else void enqueue("video", [entry.id])
  }

  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape" && entry) onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [entry, onClose])

  function trapFocus(event: KeyboardEvent<HTMLElement>) {
    if (event.key !== "Tab") return
    const controls = drawerRef.current?.querySelectorAll<HTMLElement>(
      "button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex='0']",
    )
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

  const busy = entry?.status === "downloading"

  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`absolute inset-0 z-20 bg-[rgb(9_14_26/0.45)] transition-opacity duration-200 ${
          entry ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal={entry ? true : undefined}
        aria-hidden={!entry}
        aria-labelledby={entry ? "media-details-title" : undefined}
        onKeyDown={trapFocus}
        className={`absolute top-0 right-0 z-30 flex h-full w-[420px] max-w-full flex-col border-l border-line bg-card shadow-[var(--shadow-lg)] transition-transform duration-200 ${
          entry ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {entry ? (
          <>
            <header className="flex shrink-0 items-center justify-between border-b border-line px-4 py-3">
              <span className="font-mono text-[12px] text-muted-fg">{entry.code}</span>
              <IconButton title="关闭详情" onClick={onClose}>
                <Icon.close size={16} />
              </IconButton>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <div className="flex gap-3.5">
                <div className="flex h-[128px] w-[96px] shrink-0 items-center justify-center overflow-hidden rounded-md border border-line bg-elevated text-muted-fg">
                  {entry.cover ? (
                    <img src={entry.cover} alt={`${entry.title} 封面`} className="h-full w-full object-cover" />
                  ) : (
                    <Icon.image size={28} />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <h2
                    id="media-details-title"
                    className="text-[15px] leading-snug font-semibold break-words text-fg"
                  >
                    {entry.title}
                  </h2>
                  <p className="mt-2 text-[12px] leading-relaxed break-words text-muted-fg">
                    {entry.description || "暂无简介"}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-1.5">
                {(
                  [
                    ["图片", entry.image],
                    ["NFO", entry.nfo],
                    ["视频", entry.video],
                  ] as const
                ).map(([label, state]) => (
                  <div
                    key={label}
                    className="flex flex-col items-center gap-1 rounded-md border border-line bg-panel py-2"
                  >
                    <span className="text-[11px] text-muted-fg">{label}</span>
                    <FileBadge state={state} />
                  </div>
                ))}
              </div>

              <div className="mt-4 border-t border-line">
                <Row label="编号">
                  <span className="font-mono">{entry.code}</span>
                </Row>
                <Row label={entry.originalCategoriesAvailable === false ? "已有分类" : "原始分类"}>
                  <Tags items={entry.originalCategories} />
                  {entry.originalCategoriesAvailable === false ? (
                    <p className="mt-1.5 text-[11px] leading-relaxed text-muted-fg">
                      历史记录未保存完整原始分类，已删除的分类无法从现有文件恢复。
                    </p>
                  ) : null}
                </Row>
                <Row label="写入分类">
                  <Tags items={entry.exportedCategories} />
                </Row>
                {excluded.length > 0 ? (
                  <Row label="已排除">
                    <Tags items={excluded} muted />
                  </Row>
                ) : null}
                <Row label="视频路径">
                  <span className="font-mono text-[12px] break-all text-muted-fg">
                    {entry.paths.video || "尚未生成"}
                  </span>
                </Row>
                <Row label="NFO 路径">
                  <span className="font-mono text-[12px] break-all text-muted-fg">
                    {entry.paths.nfo || "尚未生成"}
                  </span>
                </Row>
                <Row label="封面路径">
                  <span className="font-mono text-[12px] break-all text-muted-fg">
                    {entry.paths.cover || "尚未生成"}
                  </span>
                </Row>
              </div>

              {entry.error ? (
                <div className="mt-4 flex gap-2 rounded-md border border-failed/30 bg-failed-soft px-3 py-2.5 text-failed">
                  <span className="mt-[1px] shrink-0">
                    <Icon.warn size={15} />
                  </span>
                  <div className="min-w-0 break-words">
                    <div className="text-[12px] font-medium">错误详情</div>
                    <div className="mt-0.5 text-[12px] leading-relaxed">{entry.error}</div>
                  </div>
                </div>
              ) : null}
            </div>

            <footer className="flex shrink-0 flex-wrap items-center gap-2 border-t border-line bg-panel px-4 py-3">
              <Button
                variant="accent"
                size="sm"
                disabled={busy || (entry.video === "ready" && entry.status !== "failed")}
                onClick={downloadOrRetry}
              >
                {entry.status === "failed" ? <Icon.retry size={14} /> : <Icon.download size={14} />}
                {entry.status === "failed"
                  ? "重试任务"
                  : entry.video === "ready"
                    ? "视频已就绪"
                    : busy
                      ? "下载中"
                      : "下载视频"}
              </Button>
              <Button
                size="sm"
                disabled={!entry.paths.video && !monthDir}
                onClick={() => {
                  const dir = entry.paths.video ? parentDir(entry.paths.video) : ""
                  void openPath(dir || monthDir)
                }}
              >
                <Icon.open size={14} />
                打开目录
              </Button>
            </footer>
          </>
        ) : null}
      </aside>
    </>
  )
}
