import { useEffect, useState, type ReactNode } from "react"
import { useApp } from "../state"
import { APP_NAME, APP_VERSION } from "../lib/api"
import { applyTheme, initialTheme, saveScreen, type Screen, type Theme } from "../lib/store"
import { Icon } from "./ui/icons"
import { cx } from "./ui/primitives"

const NAV: { key: Screen; label: string; hint: string; icon: (p: { size?: number }) => ReactNode }[] = [
  { key: "library", label: "媒体库", hint: "hanime 月度批量抓取", icon: Icon.library },
  { key: "drama", label: "AI短剧", hint: "搜索 · 订阅 · 自动下载", icon: Icon.drama },
  { key: "settings", label: "设置", hint: "下载、网络与标签", icon: Icon.settings },
]

export function Shell({
  screen,
  onScreen,
  children,
}: {
  screen: Screen
  onScreen: (next: Screen) => void
  children: ReactNode
}) {
  const { tasks, logOpen, setLogOpen, showLogs, year, month, entries } = useApp()
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const running = tasks.filter((t) => t.state === "waiting" || t.state === "downloading").length
  const current = NAV.find((n) => n.key === screen) ?? NAV[0]

  const subtitle =
    screen === "library"
      ? `${year} 年 ${String(month).padStart(2, "0")} 月 · 共 ${entries.length} 个条目`
      : screen === "drama"
        ? "搜索 · 订阅 · 定时检查 · Emby 目录下载"
        : "更改在保存后生效"

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-bg">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-card px-3 sm:px-4">
        <button
          type="button"
          aria-label="打开导航"
          aria-expanded={navOpen}
          onClick={() => setNavOpen((v) => !v)}
          className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-muted-fg transition-colors hover:bg-elevated hover:text-fg lg:hidden"
        >
          <Icon.logs size={18} />
        </button>

        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-[6px] bg-primary text-primary-fg">
            <Icon.film size={14} />
          </span>
          <span className="text-[13px] font-semibold tracking-tight text-fg">{APP_NAME}</span>
          <span className="hidden font-mono text-[11px] text-muted-fg sm:inline">{APP_VERSION}</span>
        </div>

        <div className="mx-1 hidden h-5 w-px bg-line sm:block" />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h1 className="truncate text-[13px] font-semibold text-fg">{current.label}</h1>
            <span className="hidden truncate text-[11px] text-muted-fg md:inline">{subtitle}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {running > 0 ? (
            <button
              type="button"
              onClick={() => showLogs(undefined)}
              className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full bg-active-soft px-2.5 text-[11px] font-medium text-active transition-opacity hover:opacity-80"
            >
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-active" />
              {running} 个任务进行中
            </button>
          ) : null}
          <button
            type="button"
            aria-pressed={logOpen}
            onClick={() => setLogOpen((v) => !v)}
            title="操作日志"
            className={cx(
              "inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md px-2 text-[12px] transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              logOpen ? "bg-elevated text-fg" : "text-muted-fg hover:bg-elevated hover:text-fg",
            )}
          >
            <Icon.logs size={16} />
            <span className="hidden sm:inline">日志</span>
          </button>
          <button
            type="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title={theme === "dark" ? "切换到浅色" : "切换到深色"}
            aria-label={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"}
            className="inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md text-muted-fg transition-colors hover:bg-elevated hover:text-fg"
          >
            {theme === "dark" ? <Icon.sun size={16} /> : <Icon.moon size={16} />}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside
          className={cx(
            "absolute inset-y-12 left-0 z-30 w-[210px] shrink-0 border-r border-line bg-panel",
            "transition-transform duration-200 lg:static lg:z-auto lg:translate-x-0",
            navOpen ? "translate-x-0 shadow-[var(--shadow-lg)]" : "-translate-x-full",
          )}
        >
          <nav aria-label="主导航" className="flex flex-col gap-0.5 p-2">
            {NAV.map((item) => {
              const active = screen === item.key
              const Glyph = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  aria-current={active ? "page" : undefined}
                  onClick={() => {
                    onScreen(item.key)
                    saveScreen(item.key)
                    setNavOpen(false)
                  }}
                  className={cx(
                    "group flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors duration-150",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                    active
                      ? "bg-primary text-primary-fg"
                      : "text-muted-fg hover:bg-elevated hover:text-fg",
                  )}
                >
                  <span className="shrink-0">
                    <Glyph size={17} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{item.label}</span>
                    <span
                      className={cx(
                        "block truncate text-[11px]",
                        active ? "text-primary-fg/70" : "text-muted-fg",
                      )}
                    >
                      {item.hint}
                    </span>
                  </span>
                </button>
              )
            })}
          </nav>

          <div className="absolute inset-x-0 bottom-0 border-t border-line p-2">
            <p className="px-2 py-1.5 font-mono text-[11px] leading-relaxed text-muted-fg">
              本地服务 · 8766
              <br />
              数据目录 · config/
            </p>
          </div>
        </aside>

        {navOpen ? (
          <div
            className="absolute inset-0 z-20 bg-[rgb(9_14_26/0.4)] lg:hidden"
            onClick={() => setNavOpen(false)}
            aria-hidden="true"
          />
        ) : null}

        <main className="flex min-w-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  )
}
