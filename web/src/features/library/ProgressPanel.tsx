import { useApp } from "../../state"
import { Button, ProgressBar } from "../../components/ui/primitives"

const LABELS: Record<string, string> = {
  waiting: "等待处理",
  downloading: "正在处理",
  completed: "处理完成",
  failed: "处理失败",
  cancelled: "已取消",
}

const PHASE_FALLBACK: Record<string, string> = {
  视频: "正在下载视频",
  画质: "正在查询下载页画质…",
  NFO: "正在生成 NFO",
  图片: "正在下载封面",
}

/** 本月任务进度条：仅展示与当前月份目录相关的任务。 */
export function ProgressPanel() {
  const { tasks, monthDir, year, month, taskAction, showLogs } = useApp()
  const normalize = (p?: string) => (p ?? "").replace(/\\/g, "/").toLowerCase()
  const local = tasks.filter((task) => normalize(task.outputDir) === normalize(monthDir))
  const running = local.find((task) => task.state === "downloading")
  const waiting = local.filter((task) => task.state === "waiting")
  const task = running ?? waiting[0] ?? local.at(-1)
  if (!task) return null

  const active = task.state === "downloading" || task.state === "waiting"
  const source = `https://hanime1.me/search?genre=${encodeURIComponent("裏番")}&date=${encodeURIComponent(
    `${year} 年 ${month} 月`,
  )}`

  return (
    <section
      aria-label="本月处理进度"
      aria-live="polite"
      className="shrink-0 space-y-2 border-b border-line bg-card px-4 py-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-[12px]">
        <div className="min-w-0">
          <span
            className={`font-semibold ${task.state === "failed" ? "text-failed" : "text-fg"}`}
          >
            {LABELS[task.state] ?? task.state}
          </span>
          <span className="ml-2 text-fg">{task.title}</span>
          {task.itemTotal ? (
            <span className="ml-3 text-muted-fg">
              已处理 {task.processed ?? 0} / {task.itemTotal} 部
            </span>
          ) : null}
          {waiting.length > 0 ? (
            <span className="ml-3 text-muted-fg">{waiting.length} 项等待中</span>
          ) : null}
        </div>
        <div className="flex gap-2">
          {active ? (
            <Button size="sm" onClick={() => void taskAction("cancel", task.id)}>
              取消
            </Button>
          ) : null}
          {task.state === "failed" || task.state === "cancelled" ? (
            <Button size="sm" onClick={() => void taskAction("retry", task.id)}>
              重试
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => showLogs(task.id)}>
            查看日志
          </Button>
        </div>
      </div>

      {active ? (
        <>
          <p className="truncate text-[12px] text-muted-fg" title={task.currentTitle}>
            {task.currentTitle ? `第 ${task.currentIndex ?? 1} 部：${task.currentTitle} · ` : ""}
            {task.phase ??
              (task.state === "waiting" ? "等待前一项完成" : (PHASE_FALLBACK[task.type] ?? "正在处理"))}
          </p>
          <ProgressBar value={task.progress} indeterminate={task.indeterminate} label="本月任务进度" />
          {task.type === "视频" ? (
            <p className="font-mono text-[11px] text-muted-fg">
              {task.downloaded ?? "0 B"} / {task.total ?? "大小待获取"}
              {task.speed ? ` · ${task.speed}` : ""}
              {task.eta ? ` · 剩余 ${task.eta}` : ""}
            </p>
          ) : null}
        </>
      ) : null}

      {task.state === "failed" ? (
        <p role="alert" className="text-[12px] break-words text-failed">
          {task.error || "获取失败，请查看日志。"}
          {task.type !== "视频" ? (
            <a className="ml-2 underline" href={source} target="_blank" rel="noreferrer">
              查看网站月份页
            </a>
          ) : null}
        </p>
      ) : null}
    </section>
  )
}
