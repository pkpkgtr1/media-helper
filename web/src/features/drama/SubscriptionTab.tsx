import { useMemo, useState } from "react"
import { Button, EmptyState } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { isoText, unitLabel } from "../../lib/format"
import type { Subscription } from "../../lib/types"
import { STATE_LABELS, SourceBadge, badgeKind, sourceKeyOf } from "./shared"
import { StatusBadge } from "../../components/ui/primitives"

/** 订阅列表：每条订阅一行，含状态、集数概况与常用操作。 */
export function SubscriptionTab({
  subs,
  onCheck,
  onRepair,
  onDownload,
  onEdit,
  onToggle,
  onRemove,
  onCreate,
}: {
  subs: Subscription[]
  onCheck: (sub: Subscription) => void
  onRepair: (sub: Subscription) => void
  onDownload: (sub: Subscription) => void
  onEdit: (sub: Subscription) => void
  onToggle: (sub: Subscription) => void
  onRemove: (sub: Subscription) => void
  onCreate: () => void
}) {
  const [query, setQuery] = useState("")
  const [sourceFilter, setSourceFilter] = useState("all")

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return subs.filter(
      (sub) =>
        (sourceFilter === "all" || sourceKeyOf(sub) === sourceFilter) &&
        (!keyword || sub.title.toLowerCase().includes(keyword)),
    )
  }, [subs, query, sourceFilter])

  if (subs.length === 0) {
    return (
      <EmptyState
        icon={<Icon.drama size={22} />}
        title="还没有订阅"
        detail="去“搜索”页找到想追的短剧，添加订阅后会自动检查更新。"
        action={
          <Button size="sm" variant="accent" className="mt-1" onClick={onCreate}>
            <Icon.search size={13} />
            去搜索
          </Button>
        }
      />
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-4 py-2">
        <span className="text-[12px] text-muted-fg">共 {subs.length} 条订阅</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="筛选标题"
            aria-label="筛选订阅标题"
            className="h-7 w-[150px] rounded-md border border-line-strong bg-card px-2 text-[12px] text-fg placeholder:text-muted-fg/70 focus:border-ring focus:ring-2 focus:ring-ring/25 focus:outline-none"
          />
          <select
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value)}
            aria-label="按来源筛选"
            className="h-7 cursor-pointer rounded-md border border-line-strong bg-card px-2 text-[12px] text-fg focus:border-ring focus:ring-2 focus:ring-ring/25 focus:outline-none"
          >
            <option value="all">全部来源</option>
            <option value="huangguo">黄果短剧</option>
            <option value="yeguo">野果短剧</option>
          </select>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {visible.length === 0 ? (
          <EmptyState icon={<Icon.search size={22} />} title="没有匹配的订阅" detail="调整关键词或来源筛选再试。" />
        ) : (
          <ul className="divide-y divide-line">
            {visible.map((sub, index) => (
              <li
                key={sub.id}
                style={{ animationDelay: `${Math.min(index, 12) * 18}ms` }}
                className="rise-in flex flex-col gap-3 px-4 py-3 transition-colors duration-150 hover:bg-elevated/50 sm:flex-row sm:items-center"
              >
                <img
                  src={`/api/hg/cover?subscriptionId=${encodeURIComponent(sub.id)}`}
                  alt={`${sub.title} 封面`}
                  loading="lazy"
                  onError={(event) => {
                    event.currentTarget.style.visibility = "hidden"
                  }}
                  className="h-[96px] w-[68px] shrink-0 self-start rounded-md border border-line bg-elevated object-cover sm:self-center"
                />

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-[13px] font-semibold text-fg">{sub.title}</span>
                    <SourceBadge item={sub} />
                    {sub.activeTask ? (
                      <StatusBadge
                        kind={badgeKind(sub.activeTask.state)}
                        label={STATE_LABELS[sub.activeTask.state] ?? sub.activeTask.state}
                      />
                    ) : null}
                    {!sub.autoCheck ? <StatusBadge kind="pending" label="已暂停" /> : null}
                    {!sub.autoDownload ? <StatusBadge kind="missing" label="仅提示" /> : null}
                  </div>

                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-fg">
                    <span>
                      更新 已见 {sub.knownEpisodes.length}/{sub.total || "?"} 集
                    </span>
                    <span>
                      已下载 {sub.downloadedCount} 集 · 待处理 {sub.pendingCount} 集
                    </span>
                    <span>{sub.autoCheck ? `每 ${sub.intervalValue} ${unitLabel(sub.intervalUnit)}检查` : "自动检查已暂停"}</span>
                    <span>
                      {sub.scope === "all"
                        ? "全部下载"
                        : sub.scope === "new"
                          ? "仅后续新增"
                          : `指定 ${sub.episodeList.length} 集`}
                    </span>
                    <span title={sub.saveRoot} className="max-w-[260px] truncate">
                      路径 {sub.saveRoot}
                    </span>
                    <span>上次 {isoText(sub.lastCheckedIso)}</span>
                    <span>下次 {isoText(sub.nextCheckIso)}</span>
                  </div>
                </div>

                <div className="flex shrink-0 flex-wrap gap-2 sm:justify-end">
                  <Button size="sm" onClick={() => onCheck(sub)}>
                    <Icon.refresh size={13} />
                    检查
                  </Button>
                  <Button size="sm" variant="accent" onClick={() => onDownload(sub)}>
                    <Icon.download size={13} />
                    下载
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onEdit(sub)}>
                    <Icon.edit size={13} />
                    编辑
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onToggle(sub)}>
                    {sub.autoCheck ? <Icon.pause size={13} /> : <Icon.play size={13} />}
                    {sub.autoCheck ? "暂停" : "恢复"}
                  </Button>
                  <Button size="sm" variant="ghost" title="重新抓取封面与元数据" onClick={() => onRepair(sub)}>
                    <Icon.image size={13} />
                  </Button>
                  <Button size="sm" variant="danger" ariaLabel={`删除订阅 ${sub.title}`} onClick={() => onRemove(sub)}>
                    <Icon.trash size={13} />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
