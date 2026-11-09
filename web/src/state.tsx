import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react"
import { DEFAULT_FLARESOLVERR_URL, api, type BootstrapPayload } from "./lib/api"
import { errorText } from "./lib/format"
import { initialPeriod } from "./lib/period"
import type {
  AppSettings,
  LibraryResponse,
  LogLine,
  MediaEntry,
  DownloadTask,
  Snapshot,
  TaskKind,
} from "./lib/types"

export const EMPTY_SETTINGS: AppSettings = {
  outputRoot: "",
  openAfter: false,
  posterMode: "download",
  coverSite: "dmm",
  redownloadCover: false,
  existingVideo: "skip",
  retries: 3,
  downloadInterval: 5000,
  requestTimeout: 30,
  writeTags: true,
  writeGenres: true,
  unseenDefault: "exclude",
  proxyEnabled: false,
  proxyUrl: "",
  flaresolverrEnabled: false,
  flaresolverrUrl: DEFAULT_FLARESOLVERR_URL,
  flaresolverrSession: "",
  userAgent: "",
  hgSaveRoot: "",
  hgIntervalValue: 6,
  hgIntervalUnit: "hour",
  hgConcurrent: 4,
  hgRetries: 2,
  hgRetryInterval: 30,
  categories: [],
}

type TaskAction = "cancel" | "retry" | "retry-failed" | "clear-completed"

interface AppState {
  settings: AppSettings
  defaults: AppSettings
  entries: MediaEntry[]
  tasks: DownloadTask[]
  logs: LogLine[]
  year: number
  month: number
  monthDir: string
  loading: boolean
  ready: boolean
  selected: Set<string>
  setSelected: Dispatch<SetStateAction<Set<string>>>
  setPeriod: (year: number, month: number) => void
  refresh: () => Promise<void>
  saveSettings: (next: AppSettings) => Promise<AppSettings>
  pickDirectory: () => Promise<string | null>
  chooseDirectory: () => Promise<string | null>
  openPath: (path: string) => Promise<void>
  enqueue: (kind: TaskKind, ids?: string[]) => Promise<{ queued: number; skipped: number } | null>
  taskAction: (action: TaskAction, id?: string) => Promise<void>
  notify: (message: string) => void
  showLogs: (taskId?: string) => void
  logOpen: boolean
  setLogOpen: Dispatch<SetStateAction<boolean>>
  logTaskId?: string
  clearLogs: () => Promise<void>
  exportLogs: () => void
}

const Context = createContext<AppState | null>(null)

interface Toast {
  id: number
  message: string
  tone: "info" | "error"
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(EMPTY_SETTINGS)
  const [defaults, setDefaults] = useState<AppSettings>(EMPTY_SETTINGS)
  const [entries, setEntries] = useState<MediaEntry[]>([])
  const [tasks, setTasks] = useState<DownloadTask[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [period, setPeriodState] = useState(initialPeriod)
  const [monthDir, setMonthDir] = useState("")
  const [loading, setLoading] = useState(true)
  const [ready, setReady] = useState(false)
  const [connectionError, setConnectionError] = useState("")
  const [toasts, setToasts] = useState<Toast[]>([])
  const [logOpen, setLogOpen] = useState(false)
  const [logTaskId, setLogTaskId] = useState<string>()

  const toastId = useRef(0)
  const sequence = useRef(0)
  const revision = useRef(-1)

  /* ------------------------------------------------------------- 提示条 */

  const notify = useCallback((message: string) => {
    const id = ++toastId.current
    const tone: Toast["tone"] = /失败|错误|不能|无法|不存在|无效|超时/.test(message) ? "error" : "info"
    setToasts((prev) => [...prev.slice(-2), { id, message, tone }])
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4200)
  }, [])

  const run = useCallback(
    async <T,>(operation: () => Promise<T>): Promise<T | null> => {
      try {
        return await operation()
      } catch (error) {
        notify(errorText(error))
        return null
      }
    },
    [notify],
  )

  /* --------------------------------------------------------- 媒体库数据 */

  const settingsRef = useRef(settings)
  settingsRef.current = settings

  const refresh = useCallback(async () => {
    const root = settingsRef.current.outputRoot
    if (!root) {
      setEntries([])
      setMonthDir("")
      setLoading(false)
      return
    }
    const request = ++sequence.current
    setLoading(true)
    try {
      const query = new URLSearchParams({
        year: String(period.year),
        month: String(period.month),
        outputRoot: root,
      })
      const result = await api<LibraryResponse>(`/library?${query}`)
      if (sequence.current !== request) return
      setEntries(result.entries)
      setMonthDir(result.monthDir)
      const keep = new Set(result.entries.map((e) => e.id))
      setSelected((prev) => new Set([...prev].filter((id) => keep.has(id))))
      if (result.warnings.length) notify(result.warnings.join("；"))
    } catch (error) {
      if (sequence.current !== request) return
      setEntries([])
      setMonthDir("")
      notify(errorText(error))
    } finally {
      if (sequence.current === request) setLoading(false)
    }
  }, [period.year, period.month, notify])

  const refreshRef = useRef(refresh)
  refreshRef.current = refresh

  /* --------------------------------------------- 轮询：任务、日志、版本号 */

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        if (!ready) {
          const boot = await api<BootstrapPayload>("/bootstrap")
          if (cancelled) return
          setSettings(boot.settings)
          setDefaults(boot.defaults)
          setReady(true)
          if (boot.error) notify(boot.error)
        }
        const snapshot = await api<Snapshot>("/state")
        if (cancelled) return
        setTasks(snapshot.tasks)
        setLogs(snapshot.logs)
        setConnectionError("")
        if (revision.current !== snapshot.revision) {
          revision.current = snapshot.revision
          void refreshRef.current()
        }
      } catch (error) {
        if (!cancelled) {
          setConnectionError(`无法连接本地服务：${errorText(error)}`)
          setLoading(false)
        }
      }
      if (!cancelled) timer = setTimeout(poll, 1200)
    }

    void poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [ready, notify])

  useEffect(() => {
    if (!ready) return
    setEntries([])
    setSelected(new Set())
    void refresh()
  }, [ready, refresh])

  /* ------------------------------------------------------------ 写操作 */

  const saveSettings = useCallback(async (next: AppSettings) => {
    const saved = await api<AppSettings>("/settings", next)
    setSettings(saved)
    return saved
  }, [])

  const pickDirectory = useCallback(async () => {
    const result = await api<{ path: string | null }>("/choose-directory", {
      initial: settingsRef.current.outputRoot,
    })
    return result.path
  }, [])

  const chooseDirectory = useCallback(async () => {
    const path = await run(pickDirectory)
    if (path) await run(() => saveSettings({ ...settingsRef.current, outputRoot: path }))
    return path
  }, [pickDirectory, run, saveSettings])

  const openPath = useCallback(
    async (path: string) => {
      await run(() => api("/open-path", { path }))
    },
    [run],
  )

  const syncSnapshot = useCallback(async () => {
    const snapshot = await api<Snapshot>("/state")
    setTasks(snapshot.tasks)
    setLogs(snapshot.logs)
  }, [])

  const enqueue = useCallback(
    async (kind: TaskKind, ids?: string[]) => {
      return run(async () => {
        const result = await api<{ queued: number; skipped: number }>("/tasks", {
          kind,
          ...period,
          outputRoot: settingsRef.current.outputRoot,
          ids,
        })
        notify(
          `已加入 ${result.queued} 个任务${result.skipped ? `，跳过 ${result.skipped} 个已有或重复任务` : ""}`,
        )
        await syncSnapshot()
        await refreshRef.current()
        return result
      })
    },
    [period, run, notify, syncSnapshot],
  )

  const taskAction = useCallback(
    async (action: TaskAction, id?: string) => {
      await run(async () => {
        await api("/task-action", { action, id })
        await syncSnapshot()
        await refreshRef.current()
      })
    },
    [run, syncSnapshot],
  )

  const clearLogs = useCallback(async () => {
    await run(async () => {
      await api("/logs/clear", {})
      setLogs([])
    })
  }, [run])

  const exportLogs = useCallback(() => {
    const text = logs
      .filter((line) => !logTaskId || line.taskId === logTaskId)
      .map((line) => `${line.t} [${line.level}] ${line.msg}`)
      .join("\n")
    const link = document.createElement("a")
    link.href = URL.createObjectURL(
      new Blob(["\ufeff", text], { type: "text/plain;charset=utf-8" }),
    )
    link.download = `media-helper-${new Date().toISOString().slice(0, 10)}.log`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }, [logs, logTaskId])

  const setPeriod = useCallback((year: number, month: number) => {
    setSelected(new Set())
    setPeriodState({ year, month })
  }, [])

  const showLogs = useCallback((taskId?: string) => {
    setLogTaskId(taskId)
    setLogOpen(true)
  }, [])

  const value = useMemo<AppState>(
    () => ({
      settings,
      defaults,
      entries,
      tasks,
      logs,
      year: period.year,
      month: period.month,
      monthDir,
      loading,
      ready,
      selected,
      setSelected,
      setPeriod,
      refresh,
      saveSettings,
      pickDirectory,
      chooseDirectory,
      openPath,
      enqueue,
      taskAction,
      notify,
      showLogs,
      logOpen,
      setLogOpen,
      logTaskId,
      clearLogs,
      exportLogs,
    }),
    [
      settings, defaults, entries, tasks, logs, period.year, period.month, monthDir,
      loading, ready, selected, setPeriod, refresh, saveSettings, pickDirectory,
      chooseDirectory, openPath, enqueue, taskAction, notify, showLogs, logOpen,
      logTaskId, clearLogs, exportLogs,
    ],
  )

  return (
    <Context.Provider value={value}>
      {children}

      {connectionError ? (
        <div
          role="alert"
          className="fixed bottom-5 left-1/2 z-50 max-w-[92vw] -translate-x-1/2 rounded-lg border border-danger/40 bg-danger-soft px-5 py-3 text-[13px] text-danger shadow-[var(--shadow-md)]"
        >
          {connectionError}。请运行启动脚本，界面会自动重连。
        </div>
      ) : null}

      <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            aria-live="polite"
            className={`rise-in pointer-events-auto flex items-start gap-3 rounded-lg border bg-card px-4 py-3 text-[13px] shadow-[var(--shadow-md)] ${
              toast.tone === "error" ? "border-danger/40 text-danger" : "border-line text-fg"
            }`}
          >
            <span className="min-w-0 flex-1 break-words">{toast.message}</span>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              className="shrink-0 cursor-pointer text-muted-fg transition-colors hover:text-fg"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Context.Provider>
  )
}

export function useApp(): AppState {
  const value = useContext(Context)
  if (!value) throw new Error("AppProvider 未初始化")
  return value
}
