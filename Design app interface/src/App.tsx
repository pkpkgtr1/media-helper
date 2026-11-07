import { useState } from "react"
import { Icon } from "./components/icons"
import { Huangguo } from "./components/Huangguo"
import { MediaLibrary } from "./components/MediaLibrary"
import { Settings } from "./components/Settings"
import { useApp } from "./state"
import { APP_NAME, APP_VERSION } from "./version"

type Screen = "library" | "huangguo" | "settings"

const NAV: { key: Screen; label: string; icon: (p: { size?: number }) => React.ReactNode }[] = [
  { key: "library", label: "hanime", icon: Icon.library },
  { key: "huangguo", label: "黄果短剧", icon: Icon.download },
  { key: "settings", label: "设置", icon: Icon.settings },
]

const TITLES: Record<Screen, string> = {
  library: "媒体库",
  huangguo: "黄果短剧",
  settings: "设置",
}

const logColor = { info: "var(--muted-foreground)", warn: "var(--status-pending)", error: "var(--status-failed)" }

const SCREEN_KEY = "media-helper.screen"

function initialScreen(): Screen {
  // 刷新后停留在原分类；非法或缺失值回落到 hanime
  try {
    const saved = window.localStorage.getItem(SCREEN_KEY)
    return saved === "library" || saved === "huangguo" || saved === "settings" ? saved : "library"
  } catch {
    return "library"
  }
}

export default function App() {
  const [screen, setScreenState] = useState<Screen>(initialScreen)
  const setScreen = (next: Screen) => {
    setScreenState(next)
    try {
      window.localStorage.setItem(SCREEN_KEY, next)
    } catch {
      /* 隐私模式下忽略，不影响本次使用 */
    }
  }
  const { entries, year, month, logs, logOpen, setLogOpen, logTaskId, showLogs, exportLogs, clearLogs } = useApp()
  // 倒序显示：最新日志置顶，1.2s 轮询实时刷新；导出仍保持时间正序
  const displayedLogs = logs.filter(l => !logTaskId || l.taskId === logTaskId).slice().reverse().slice(0, 500)

  return (
    <div className="flex h-full w-full items-center justify-center bg-[#e4e6ea] p-0 sm:p-6">
      {/* Desktop window frame */}
      <div className="flex h-full w-full max-w-[1440px] flex-col overflow-hidden bg-background sm:h-[min(900px,100%)] sm:rounded-[10px] sm:border sm:border-border-strong sm:shadow-[0_20px_60px_-20px_rgba(28,33,40,0.35)]">
        {/* Title bar */}
        <header className="flex h-9 shrink-0 items-center justify-between border-b border-border bg-card px-3">
          <div className="flex items-center gap-2">
            <div className="flex h-[18px] w-[18px] items-center justify-center rounded-[5px] bg-primary text-primary-foreground">
              <svg width="12" height="12" viewBox="0 0 20 20" fill="none"><rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.6"/><path d="M8 8.2v3.6l3-1.8z" fill="currentColor"/></svg>
            </div>
            <span className="text-[12.5px] font-medium text-foreground">{APP_NAME}</span>
            <span className="font-mono text-[11px] text-muted-foreground">本地版 {APP_VERSION}</span>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* Sidebar */}
          <aside className="flex w-[56px] sm:w-[164px] xl:w-[188px] shrink-0 flex-col border-r border-border bg-panel">
            <nav className="flex flex-col gap-0.5 p-1.5 sm:p-2.5">
              {NAV.map((n) => {
                const active = screen === n.key
                return (
                  <button
                    key={n.key}
                    aria-label={n.label}
                    title={n.label}
                    onClick={() => setScreen(n.key)}
                    className={`flex items-center gap-2.5 rounded-[7px] px-3 py-2 text-[13px] font-medium transition-colors ${
                      active ? "bg-primary text-primary-foreground" : "text-secondary-foreground hover:bg-secondary"
                    }`}
                  >
                    <n.icon size={17} />
                    <span className="hidden flex-1 text-left sm:inline">{n.label}</span>
                  </button>
                )
              })}
            </nav>

            <div className="mt-auto p-1.5 sm:p-2.5">
              <button
                aria-label="日志"
                onClick={() => logOpen ? setLogOpen(false) : showLogs()}
                className={`flex w-full items-center gap-2.5 rounded-[7px] px-3 py-2 text-[13px] transition-colors ${
                  logOpen ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
              >
                <Icon.logs size={17} />
                <span className="hidden flex-1 text-left sm:inline">日志</span>
                <span className={`hidden sm:inline transition-transform ${logOpen ? "rotate-90" : ""}`}><Icon.chevron size={14} /></span>
              </button>
            </div>
          </aside>

          {/* Main + log */}
          <main className="flex min-w-0 flex-1 flex-col">
            <div className="flex h-11 shrink-0 items-center border-b border-border bg-card px-5">
              <h1 className="text-[15px] font-semibold text-foreground">{TITLES[screen]}</h1>
              <span className="ml-3 text-[12px] text-muted-foreground">
                {screen === "library" && `${year} 年 ${String(month).padStart(2,"0")} 月 · 共 ${entries.length} 个条目`}
                {screen === "huangguo" && "搜索 · 订阅 · 定时检查 · Emby 目录下载"}
                {screen === "settings" && "更改在保存后生效"}
              </span>
            </div>

            <div className="min-h-0 flex-1">
              {screen === "library" && <MediaLibrary />}
              {screen === "huangguo" && <Huangguo />}
              <div className={screen === "settings" ? "h-full" : "hidden"}><Settings /></div>
            </div>

            {/* Collapsible log panel */}
            {logOpen && (
              <div className="flex h-[192px] shrink-0 flex-col border-t border-border bg-card">
                <div className="flex items-center justify-between border-b border-border px-5 py-2">
                  <span className="text-[12px] font-medium text-foreground">操作日志</span>
                  <div className="flex items-center gap-3 text-[12px]">
                    {logTaskId && <button onClick={() => showLogs()} className="text-muted-foreground hover:text-foreground">全部日志</button>}
                    <button onClick={exportLogs} className="text-muted-foreground hover:text-foreground">导出日志</button>
                    <button onClick={() => void clearLogs()} className="text-muted-foreground hover:text-foreground">清空</button>
                    <button onClick={() => setLogOpen(false)} className="text-muted-foreground hover:text-foreground"><Icon.close size={14} /></button>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto px-5 py-2 font-mono text-[12px] leading-relaxed">
                  {displayedLogs.length === 0 && <p className="text-muted-foreground">暂无操作日志</p>}
                  {displayedLogs.map((l) => (
                    <div key={l.id} className="flex gap-3">
                      <span className="shrink-0 text-muted-foreground">{l.t}</span>
                      <span style={{ color: logColor[l.level] }} className="uppercase">[{l.level}]</span>
                      <span className="text-foreground">{l.msg}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
