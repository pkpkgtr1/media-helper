import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { api, type AppSettings } from "../api"
import { useApp } from "../state"
import { Button, Segmented, Toggle } from "./ui"
import { Icon } from "./icons"

interface NfoPreview {
  affected: number
  unrecoverable: number
  preview: { id: string; title: string; before: string; after: string }[]
  token: string
}

export function UpdateNfoDialog({
  settings,
  onClose,
}: {
  settings: AppSettings
  onClose: () => void
}) {
  const { selected, year, month, outputRoot, refresh, notify } = useApp()
  const [scope, setScope] = useState("current")
  const [backup, setBackup] = useState(true)
  const [preview, setPreview] = useState<{
    request: string
    value: NfoPreview
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState("")
  const [attempt, setAttempt] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const request = JSON.stringify({
    year,
    month,
    outputRoot,
    ...(scope === "selected" ? { ids: [...selected].sort() } : {}),
    settings,
  })
  const emptySelection = scope === "selected" && selected.size === 0
  const currentPreview = preview?.request === request ? preview.value : null

  useEffect(() => {
    const previousFocus = document.activeElement
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [])

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && !applying) {
      event.preventDefault()
      onClose()
    } else if (event.key === "Tab") {
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex='0']")
      if (!controls?.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
  }

  useEffect(() => {
    let cancelled = false
    setPreview(null)
    setError("")
    if (emptySelection) {
      setLoading(false)
      return
    }
    setLoading(true)
    void api<NfoPreview>("/nfo/preview", JSON.parse(request))
      .then((value) => {
        if (!cancelled) setPreview({ request, value })
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setError(error instanceof Error ? error.message : String(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [request, emptySelection, attempt])

  async function apply() {
    if (
      applying ||
      loading ||
      emptySelection ||
      !currentPreview?.token ||
      currentPreview.affected === 0
    )
      return
    setApplying(true)
    setError("")
    try {
      const result = await api<{ updated: number; backups: number }>(
        "/nfo/apply",
        { ...JSON.parse(request), backup, token: currentPreview.token },
      )
      notify(`已更新 ${result.updated} 个 NFO，备份 ${result.backups} 个。`)
      onClose()
      void refresh().catch((error: unknown) =>
        notify(
          `NFO 已更新，刷新记录失败：${
            error instanceof Error ? error.message : String(error)
          }`,
        ),
      )
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
      setPreview(null)
    } finally {
      setApplying(false)
    }
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="nfo-dialog-title"
      onKeyDown={handleKeyDown}
      className="absolute inset-0 z-40 flex items-center justify-center bg-foreground/25 p-3 sm:p-6"
    >
      <div className="flex max-h-full w-[640px] max-w-full flex-col rounded-[9px] border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-3 sm:px-5 py-3.5">
          <h3
            id="nfo-dialog-title"
            className="text-[14px] font-medium text-foreground"
          >
            应用到已有 NFO
          </h3>
          <button
            aria-label="关闭"
            disabled={applying}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground disabled:opacity-45"
          >
            <Icon.close />
          </button>
        </header>
        <fieldset
          disabled={applying}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto border-0 px-3 sm:px-5 py-4"
        >
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            此操作将按当前草稿中的分类规则重写选定范围内已有的 NFO
            文件。视频文件与其他 NFO 字段不受影响。
          </p>
          <div className="mt-4">
            <div className="mb-1.5 text-[12px] font-medium text-foreground">
              应用范围 · {year}-{String(month).padStart(2, "0")}
            </div>
            <Segmented
              value={scope}
              onChange={setScope}
              options={[
                { value: "selected", label: `所选条目（${selected.size}）` },
                { value: "current", label: "当前月份" },
              ]}
            />
          </div>
          <div className="mt-4 flex items-center justify-between rounded-[6px] border border-border bg-panel px-3 py-2.5">
            <span className="text-[12px] text-muted-foreground">
              受影响文件
            </span>
            <span
              role="status"
              className="font-mono text-[13px] font-medium text-foreground"
            >
              {loading
                ? "正在预览…"
                : currentPreview
                  ? `${currentPreview.affected} 个`
                  : "—"}
            </span>
          </div>
          {emptySelection && (
            <p
              role="alert"
              className="mt-3 text-[12px] text-[color:var(--status-pending)]"
            >
              未选择任何条目。请先在媒体库勾选条目，或切换到当前月份。
            </p>
          )}
          {error && (
            <div
              role="alert"
              className="mt-3 space-y-2 text-[12px] text-[color:var(--status-failed)]"
            >
              <p>{error}</p>
              <Button
                size="sm"
                disabled={loading}
                onClick={() => setAttempt((value) => value + 1)}
              >
                重新预览
              </Button>
            </div>
          )}
          {currentPreview?.preview.map((item) => (
            <div key={item.id} className="mt-4">
              <div className="mb-1.5 text-[12px] font-medium text-foreground">
                修改前后对比 · {item.title || item.id}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <div className="min-w-0 rounded-[6px] border border-border bg-panel p-2.5">
                  <div className="mb-1.5 text-[11px] text-muted-foreground">
                    修改前
                  </div>
                  <pre className="max-h-[240px] overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-foreground">
                    {item.before}
                  </pre>
                </div>
                <div className="min-w-0 rounded-[6px] border border-[color:var(--status-ready)] bg-[color:var(--status-ready-bg)] p-2.5">
                  <div className="mb-1.5 text-[11px] text-[color:var(--status-ready)]">
                    修改后
                  </div>
                  <pre className="max-h-[240px] overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-foreground">
                    {item.after}
                  </pre>
                </div>
              </div>
            </div>
          ))}
          {currentPreview && currentPreview.affected === 0 && (
            <p className="mt-3 text-[12px] text-muted-foreground">
              此范围没有需要更新的 NFO 文件。
            </p>
          )}
          <div className="mt-4 flex items-center gap-2.5 rounded-[6px] border border-border bg-panel px-3 py-2.5">
            <Toggle checked={backup} onChange={setBackup} />
            <div>
              <div className="text-[12px] font-medium text-foreground">
                修改前备份 NFO
              </div>
              <div className="text-[11px] text-muted-foreground">
                将原文件另存为 <span className="font-mono">.nfo.bak</span>{" "}
                后再写入。
              </div>
            </div>
          </div>
          {currentPreview && currentPreview.unrecoverable > 0 && (
            <div className="mt-3 flex items-start gap-2 rounded-[6px] border border-[color:var(--status-pending-bg)] bg-[color:var(--status-pending-bg)] px-3 py-2.5 text-[color:var(--status-pending)]">
              <span className="mt-[1px] shrink-0">
                <Icon.warn size={14} />
              </span>
              <p className="text-[11px] leading-relaxed">
                {currentPreview.unrecoverable}{" "}
                条历史记录缺少原始分类，需要重新获取元数据后才能恢复。这些条目不会被标记为已还原。
              </p>
            </div>
          )}
        </fieldset>
        <footer className="flex items-center justify-end gap-2 border-t border-border px-3 sm:px-5 py-3">
          <Button variant="ghost" disabled={applying} onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            disabled={
              applying ||
              loading ||
              emptySelection ||
              !currentPreview?.token ||
              currentPreview.affected === 0
            }
            onClick={() => void apply()}
          >
            <Icon.check size={14} />
            {applying ? "正在更新…" : "确认更新"}
          </Button>
        </footer>
      </div>
    </div>
  )
}

export default UpdateNfoDialog
