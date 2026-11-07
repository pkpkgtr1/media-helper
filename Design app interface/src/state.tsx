import { createContext, useCallback, useContext, useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react"
import { api, DEFAULT_FLARESOLVERR_URL, type AppSettings, type LibraryResponse, type LogLine, type Snapshot } from "./api"
import type { DownloadTask, MediaEntry } from "./data"

type Kind = "metadata" | "covers" | "video" | "repair" | "resolutions"
interface AppState {
  settings: AppSettings; defaults: AppSettings; entries: MediaEntry[]; tasks: DownloadTask[]; logs: LogLine[]
  year: number; month: number; outputRoot: string; monthDir: string; loading: boolean; ready: boolean
  selected: Set<string>; setSelected: Dispatch<SetStateAction<Set<string>>>
  setPeriod: (year: number, month: number) => void; refresh: () => Promise<void>
  chooseDirectory: () => Promise<string | null>; pickDirectory: () => Promise<string | null>
  openPath: (path: string) => Promise<void>; enqueue: (kind: Kind, ids?: string[]) => Promise<void>
  taskAction: (action: "cancel" | "retry" | "retry-failed" | "clear-completed", id?: string) => Promise<void>
  saveSettings: (settings: AppSettings) => Promise<AppSettings>; notify: (message: string) => void
  showLogs: (taskId?: string) => void; logOpen: boolean; setLogOpen: Dispatch<SetStateAction<boolean>>
  logTaskId?: string; clearLogs: () => Promise<void>; exportLogs: () => void
}
const Context = createContext<AppState | null>(null)
const date = new Date()
date.setDate(1)
date.setMonth(date.getMonth() - 1)
const initial: AppSettings = { outputRoot: "", openAfter: false, posterMode: "download", coverSite: "dmm", redownloadCover: false, existingVideo: "skip", retries: 3, downloadInterval: 5000, requestTimeout: 30, writeTags: true, writeGenres: true, unseenDefault: "exclude", proxyEnabled: false, proxyUrl: "", flaresolverrEnabled: false, flaresolverrUrl: DEFAULT_FLARESOLVERR_URL, hgSaveRoot: "", hgIntervalValue: 6, hgIntervalUnit: "hour", hgConcurrent: 4, hgRetries: 2, hgRetryInterval: 30, categories: [] }
const messageOf = (error: unknown) => error instanceof Error ? error.message : String(error)

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(initial)
  const [defaults, setDefaults] = useState<AppSettings>(initial)
  const [period, setPeriodState] = useState({ year: date.getFullYear(), month: date.getMonth() + 1 })
  const [entries, setEntries] = useState<MediaEntry[]>([])
  const [tasks, setTasks] = useState<DownloadTask[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [monthDir, setMonthDir] = useState("")
  const [loading, setLoading] = useState(true)
  const [ready, setReady] = useState(false)
  const [connectionError, setConnectionError] = useState("")
  const [notice, setNotice] = useState("")
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [logOpen, setLogOpen] = useState(false)
  const [logTaskId, setLogTaskId] = useState<string>()
  const sequence = useRef(0)
  const revision = useRef(-1)
  // 提示会自动消失，避免长期悬浮遮挡页面内容（尤其"我的订阅"顶部区域）
  const notify = useCallback((message: string) => {
    setNotice(message)
    if (noticeTimer.current) clearTimeout(noticeTimer.current)
    noticeTimer.current = setTimeout(() => setNotice(""), 4000)
  }, [])

  const refresh = useCallback(async () => {
    if (!settings.outputRoot) return
    const request = ++sequence.current
    setLoading(true)
    try {
      const query = new URLSearchParams({ year: String(period.year), month: String(period.month), outputRoot: settings.outputRoot })
      const result = await api<LibraryResponse>(`/library?${query}`)
      if (sequence.current !== request) return
      setEntries(result.entries)
      setMonthDir(result.monthDir)
      const keys = new Set(result.entries.map(e => e.id))
      setSelected(previous => new Set([...previous].filter(id => keys.has(id))))
      if (result.warnings.length) notify(result.warnings.join("；"))
    } catch (error) {
      if (sequence.current === request) { setEntries([]); notify(messageOf(error)) }
    } finally { if (sequence.current === request) setLoading(false) }
  }, [settings.outputRoot, period.year, period.month, notify])
  const refreshRef = useRef(refresh)
  refreshRef.current = refresh

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        if (!ready) {
          const boot = await api<{ settings: AppSettings; defaults: AppSettings; error?: string }>("/bootstrap")
          if (cancelled) return
          setSettings(boot.settings); setDefaults(boot.defaults); setReady(true)
          if (boot.error) notify(boot.error)
        }
        const result = await api<Snapshot>("/state")
        if (cancelled) return
        setTasks(result.tasks); setLogs(result.logs); setConnectionError("")
        if (revision.current !== result.revision) { revision.current = result.revision; void refreshRef.current() }
      } catch (error) { if (!cancelled) { setConnectionError(`无法连接本地服务：${messageOf(error)}`); setLoading(false) } }
      if (!cancelled) timer = setTimeout(poll, 1200)
    }
    void poll()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [ready, notify])
  useEffect(() => { if (ready) { setEntries([]); setSelected(new Set()); void refresh() } }, [ready, refresh])

  async function saveSettings(next: AppSettings) {
    const saved = await api<AppSettings>("/settings", next)
    setSettings(saved)
    return saved
  }
  async function pickDirectory() {
    const result = await api<{ path: string | null }>("/choose-directory", { initial: settings.outputRoot })
    return result.path
  }
  async function chooseDirectory() {
    try { const path = await pickDirectory(); if (path) await saveSettings({ ...settings, outputRoot: path }); return path }
    catch (error) { notify(messageOf(error)); return null }
  }
  async function openPath(path: string) {
    try { await api("/open-path", { path }) } catch (error) { notify(messageOf(error)) }
  }
  async function enqueue(kind: Kind, ids?: string[]) {
    try {
      const result = await api<{ queued: number; skipped: number }>("/tasks", { kind, ...period, outputRoot: settings.outputRoot, ids })
      notify(`已加入 ${result.queued} 个任务${result.skipped ? `，跳过 ${result.skipped} 个已有或重复任务` : ""}`)
      const state = await api<Snapshot>("/state"); setTasks(state.tasks); setLogs(state.logs)
      await refresh()
    } catch (error) { notify(messageOf(error)) }
  }
  async function taskAction(action: "cancel" | "retry" | "retry-failed" | "clear-completed", id?: string) {
    try { await api("/task-action", { action, id }); const state = await api<Snapshot>("/state"); setTasks(state.tasks); await refresh() }
    catch (error) { notify(messageOf(error)) }
  }
  function exportLogs() {
    const text = logs.filter(l => !logTaskId || l.taskId === logTaskId).map(l => `${l.t} [${l.level}] ${l.msg}`).join("\n")
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob(["\ufeff", text], { type: "text/plain;charset=utf-8" })); link.download = `media-helper-${new Date().toISOString().slice(0,10)}.log`; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }
  async function clearLogs() { try { await api("/logs/clear", {}); setLogs([]) } catch (error) { notify(messageOf(error)) } }
  return <Context.Provider value={{ settings, defaults, entries, tasks, logs, ...period, outputRoot: settings.outputRoot, monthDir, loading, ready, selected, setSelected,
    setPeriod: (year, month) => { setSelected(new Set()); setPeriodState({year,month}) }, refresh, saveSettings, chooseDirectory, pickDirectory, openPath, enqueue, taskAction, notify,
    showLogs: taskId => { setLogTaskId(taskId); setLogOpen(true) }, logOpen, setLogOpen, logTaskId, clearLogs, exportLogs }}>
    {children}
    {connectionError && <div role="alert" className="fixed bottom-5 left-1/2 z-50 max-w-[90vw] -translate-x-1/2 rounded-lg border border-red-300 bg-red-50 px-5 py-3 text-sm text-red-800">{connectionError}。请运行“启动新界面.bat”，正在自动重连。</div>}
    {notice && <div role="status" className="fixed bottom-6 right-6 z-50 flex max-w-md items-start gap-4 rounded-lg border border-border-strong bg-card px-5 py-3 text-sm shadow-xl"><span>{notice}</span><button aria-label="关闭通知" onClick={() => setNotice("")}>×</button></div>}
  </Context.Provider>
}
export function useApp() { const value = useContext(Context); if (!value) throw new Error("AppProvider 未初始化"); return value }
