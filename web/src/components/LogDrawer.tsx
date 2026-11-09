import { useMemo, useState } from "react"
import { useApp } from "../state"
import { Button, IconButton, Segmented } from "./ui/primitives"
import { Icon } from "./ui/icons"

type Filter = "all" | "info" | "warn" | "error"

const LEVEL_COLOR: Record<string, string> = {
  info: "text-muted-fg",
  warn: "text-pending",
  error: "text-failed",
}

/** 底部日志面板：倒序展示（最新在上），按级别过滤。 */
export function LogDrawer() {
  const { logs, logOpen, setLogOpen, logTaskId, showLogs, clearLogs, exportLogs } = useApp()
  const [filter, setFilter] = useState<Filter>("all")

  const visible = useMemo(() => {
    const scoped = logs.filter((line) => !logTaskId || line.taskId === logTaskId)
    const byLevel = filter === "all" ? scoped : scoped.filter((line) => line.level === filter)
    return byLevel.slice(-600).reverse()
  }, [logs, logTaskId, filter])

  if (!logOpen) return null

  return (
    <section
      aria-label="操作日志"
      className="flex h-[224px] shrink-0 flex-col border-t border-line bg-card"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <span className="text-[12px] font-semibold text-fg">操作日志</span>
        <span className="font-mono text-[11px] text-muted-fg">{visible.length} 条</span>
        <Segmented
          size="sm"
          label="日志级别"
          value={filter}
          options={[
            { value: "all", label: "全部" },
            { value: "info", label: "信息" },
            { value: "warn", label: "警告" },
            { value: "error", label: "错误" },
          ]}
          onChange={setFilter}
        />
        <div className="ml-auto flex items-center gap-1">
          {logTaskId ? (
            <Button size="sm" variant="ghost" onClick={() => showLogs(undefined)}>
              全部日志
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={exportLogs}>
            导出
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void clearLogs()}>
            清空
          </Button>
          <IconButton title="收起日志" onClick={() => setLogOpen(false)}>
            <Icon.close size={14} />
          </IconButton>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-2 font-mono text-[12px] leading-relaxed">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-muted-fg">暂无操作日志</p>
        ) : (
          visible.map((line) => (
            <div key={line.id} className="flex gap-3 py-[1px]">
              <span className="shrink-0 text-muted-fg tabular-nums">{line.t}</span>
              <span className={`shrink-0 uppercase ${LEVEL_COLOR[line.level] ?? "text-muted-fg"}`}>
                [{line.level}]
              </span>
              <span className="min-w-0 break-words text-fg">{line.msg}</span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
