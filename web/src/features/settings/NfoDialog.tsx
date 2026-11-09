import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { useApp } from "../../state"
import { api } from "../../lib/api"
import { errorText } from "../../lib/format"
import { Button, Modal, Segmented } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings, NfoPreview } from "../../lib/types"

/** 批量更新已有 NFO：先预览影响面，再确认写入并备份。 */
export function NfoDialog({ settings, onClose }: { settings: AppSettings; onClose: () => void }) {
  const { selected, year, month, settings: live, refresh, notify } = useApp()
  const outputRoot = live.outputRoot
  const [scope, setScope] = useState("current")
  const [backup, setBackup] = useState(true)
  const [preview, setPreview] = useState<{ request: string; value: NfoPreview } | null>(null)
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
  const current = preview?.request === request ? preview.value : null

  useEffect(() => {
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus()
  }, [])

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
        if (!cancelled) setError(errorText(error))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [request, emptySelection, attempt])

  async function apply() {
    if (applying || loading || emptySelection || !current?.token || current.affected === 0) return
    setApplying(true)
    setError("")
    try {
      const result = await api<{ updated: number; backups: number }>("/nfo/apply", {
        ...JSON.parse(request),
        backup,
        token: current.token,
      })
      notify(`已更新 ${result.updated} 个 NFO，备份 ${result.backups} 个。`)
      onClose()
      void refresh()
    } catch (error) {
      setError(errorText(error))
      setPreview(null)
    } finally {
      setApplying(false)
    }
  }

  const disabled = loading || emptySelection || !current || current.affected === 0

  return (
    <Modal
      title="应用到已有 NFO"
      onClose={onClose}
      width="max-w-[620px]"
      footer={
        <>
          <Button onClick={onClose} disabled={applying}>
            取消
          </Button>
          <Button variant="accent" onClick={() => void apply()} disabled={disabled || applying}>
            <Icon.check size={14} />
            {applying ? "写入中…" : `应用到 ${current?.affected ?? 0} 个 NFO`}
          </Button>
        </>
      }
    >
      <div ref={dialogRef} className="space-y-3" onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => e.stopPropagation()}>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            label="应用范围"
            value={scope}
            options={[
              { value: "current", label: "本月全部" },
              { value: "selected", label: `已选 ${selected.size}` },
            ]}
            onChange={setScope}
          />
          <Segmented
            label="备份"
            value={backup ? "on" : "off"}
            options={[
              { value: "on", label: "备份原文件" },
              { value: "off", label: "不备份" },
            ]}
            onChange={(v) => setBackup(v === "on")}
          />
        </div>

        {emptySelection ? (
          <p className="rounded-md border border-line bg-panel px-3 py-2.5 text-[12px] text-muted-fg">
            尚未在媒体库中选择任何条目。
          </p>
        ) : loading ? (
          <p className="rounded-md border border-line bg-panel px-3 py-2.5 text-[12px] text-muted-fg">
            正在生成预览…
          </p>
        ) : current ? (
          <>
            <p className="text-[12px] text-muted-fg">
              将影响 <span className="font-mono font-semibold text-fg">{current.affected}</span> 个条目
              {current.unrecoverable > 0 ? (
                <span className="text-pending">，其中 {current.unrecoverable} 个缺少原始分类已无法还原</span>
              ) : null}
              。
            </p>
            <div className="max-h-[280px] space-y-2 overflow-y-auto">
              {current.preview.map((row) => (
                <div key={row.id} className="rounded-md border border-line bg-panel px-3 py-2">
                  <div className="text-[12px] font-medium text-fg">{row.title}</div>
                  <div className="mt-1 grid gap-1 font-mono text-[11px] leading-relaxed sm:grid-cols-2">
                    <div className="text-muted-fg">
                      <span className="text-failed">− </span>
                      {row.before || "（空）"}
                    </div>
                    <div className="text-fg">
                      <span className="text-ready">+ </span>
                      {row.after || "（空）"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {current.affected === 0 ? (
              <p className="text-[12px] text-muted-fg">当前设置下没有需要更新的 NFO。</p>
            ) : null}
          </>
        ) : null}

        {error ? (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-failed/30 bg-failed-soft px-3 py-2 text-[12px] text-failed">
            <span className="min-w-0 flex-1 break-words">{error}</span>
            <Button size="sm" variant="ghost" onClick={() => setAttempt((v) => v + 1)}>
              重试
            </Button>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
