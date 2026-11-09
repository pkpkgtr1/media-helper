import { useState } from "react"
import { Button, EmptyState, Modal, ProgressBar, StatusBadge } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { timeText } from "../../lib/format"
import type { DramaTask } from "../../lib/types"
import { STATE_LABELS, SourceBadge, badgeKind } from "./shared"

const KIND_LABELS: Record<string, string> = {
  check: "检查更新",
  thumb: "截帧缩略图",
  download: "下载",
}

/** 下载任务列表：按时间倒序，进行中的排在最前。 */
export function TaskTab({
  tasks,
  runningCount,
  onCancel,
  onRetry,
  onClear,
}: {
  tasks: DramaTask[]
  runningCount: number
  onCancel: (task: DramaTask) => void
  onRetry: (task: DramaTask) => void
  onClear: () => void
}) {
  const [confirmClear, setConfirmClear] = useState(false)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-4 py-2">
        <span className="text-[12px] text-muted-fg">
          共 {tasks.length} 条记录{runningCount > 0 ? `（${runningCount} 条进行中）` : ""}
        </span>
        <Button
          size="sm"
          variant="danger"
          className="ml-auto"
          disabled={tasks.length === 0}
          title="清空已结束的任务记录，进行中的任务会保留"
          onClick={() => setConfirmClear(true)}
        >
          <Icon.trash size={13} />
          清空记录
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tasks.length === 0 ? (
          <EmptyState icon={<Icon.clock size={22} />} title="暂无短剧任务" detail="订阅检查更新或手动下载后，任务会出现在这里。" />
        ) : (
          <ul className="divide-y divide-line">
            {tasks.map((task, index) => (
              <li
                key={task.id}
                style={{ animationDelay: `${Math.min(index, 14) * 16}ms` }}
                className="rise-in px-4 py-3 transition-colors duration-150 hover:bg-elevated/40"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                  <span className="inline-flex items-baseline gap-1 text-[12px] leading-5 font-medium text-fg">
                    {KIND_LABELS[task.kind] ?? task.kind}
                    {task.subscriptionTitle ? (
                      <span className="text-[12px] font-normal text-fg">《{task.subscriptionTitle}》</span>
                    ) : null}
                  </span>
                  {task.subscriptionTitle ? <SourceBadge item={task} /> : null}
                  <StatusBadge kind={badgeKind(task.state)} label={STATE_LABELS[task.state] ?? task.state} />
                  <span className="truncate text-[12px] text-muted-fg">{task.message || "—"}</span>
                  {task.kind === "check" && task.finishedAt ? (
                    <span className="text-[12px] text-muted-fg">检测时间 {timeText(task.finishedAt)}</span>
                  ) : null}
                  {task.currentEpisode != null ? (
                    <span className="text-[12px] text-muted-fg">当前第 {task.currentEpisode} 集</span>
                  ) : null}

                  <div className="ml-auto flex gap-2">
                    {task.state === "waiting" || task.state === "downloading" || task.state === "checking" ? (
                      <Button size="sm" onClick={() => onCancel(task)}>
                        取消
                      </Button>
                    ) : null}
                    {task.state === "failed" || task.state === "cancelled" ? (
                      <Button size="sm" onClick={() => onRetry(task)}>
                        <Icon.retry size={13} />
                        重试
                      </Button>
                    ) : null}
                  </div>
                </div>

                {task.state === "downloading" || task.state === "checking" ? (
                  <div className="mt-2">
                    <ProgressBar
                      value={task.progress}
                      indeterminate={task.progress === 0}
                      label={`${task.subscriptionTitle ?? task.kind} 进度`}
                    />
                  </div>
                ) : null}

                {task.error ? (
                  <p role="alert" className="mt-1.5 text-[12px] break-words text-failed">
                    {task.error}
                  </p>
                ) : null}

                {task.detail?.failed?.length ? (
                  <p className="mt-1 text-[11px] text-muted-fg">
                    失败集数：{task.detail.failed.map((item) => `E${item.episode}`).join(", ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      {confirmClear ? (
        <Modal
          title="清空下载任务记录"
          onClose={() => setConfirmClear(false)}
          footer={
            <>
              <Button onClick={() => setConfirmClear(false)}>取消</Button>
              <Button
                variant="danger"
                onClick={() => {
                  onClear()
                  setConfirmClear(false)
                }}
              >
                确认清空
              </Button>
            </>
          }
        >
          <p className="py-2 text-[12px] leading-relaxed text-muted-fg">
            {runningCount > 0
              ? `将清除 ${tasks.length - runningCount} 条已结束的记录，${runningCount} 条进行中的任务会保留。`
              : `将清除全部 ${tasks.length} 条任务记录。`}
            此操作只清理任务列表，不会删除已下载的视频文件。
          </p>
        </Modal>
      ) : null}
    </div>
  )
}
