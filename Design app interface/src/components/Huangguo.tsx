import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, type AppSettings } from "../api"
import { useApp } from "../state"
import { Button, ProgressBar, Segmented, Select, StatusBadge, TextInput, Toggle } from "./ui"
import { Modal, SettingRow, SettingShell } from "./Shell"
import { Icon } from "./icons"

type SearchItem = {
  id: string
  title: string
  url: string
  cover: string
  description: string
  episodeLabel: string
  score: string
  tags: string[]
}
type Detail = SearchItem & { total: number; episodes: number[]; premiered: string; actors: string }
type Subscription = {
  id: string
  videoId: string
  title: string
  url: string
  total: number
  knownEpisodes: number[]
  autoCheck: boolean
  intervalValue: number
  intervalUnit: string
  saveRoot: string
  autoDownload: boolean
  scope: "all" | "new" | "list"
  episodeList: number[]
  baseline: number[]
  lastCheckedIso: string | null
  nextCheckIso: string | null
  downloadedCount: number
  pendingCount: number
  activeTask: { id: string; kind: string; state: string; message: string } | null
}
type HgTask = {
  id: string
  kind: string
  subscriptionId: string
  subscriptionTitle?: string
  state: string
  message: string
  progress: number
  error: string
  currentEpisode: number | null
  createdAt?: number
  finishedAt?: number | null
  detail: { episodes?: number[]; ok?: number[]; failed?: { episode: number; error: string }[] } | null
}

type Tab = "搜索" | "我的订阅" | "下载任务" | "默认设置"
const TABS: { value: string; label: string }[] = [
  { value: "搜索", label: "搜索" },
  { value: "我的订阅", label: "我的订阅" },
  { value: "下载任务", label: "下载任务" },
  { value: "默认设置", label: "默认设置" },
]
const STATE_LABELS: Record<string, string> = {
  waiting: "等待中",
  checking: "检查中",
  downloading: "下载中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  skipped: "跳过",
}
const badgeKind = (state: string) =>
  state === "completed" ? "ready"
    : state === "failed" ? "failed"
      : state === "cancelled" ? "missing"
        : state === "waiting" || state === "skipped" ? "pending"
          : "active"

const errorText = (value: unknown) => (value instanceof Error ? value.message : String(value))

const timeText = (ts?: number | null) =>
  ts ? new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""
const coverSrc = (url: string) => (url ? `/api/hg/image?url=${encodeURIComponent(url)}` : "")
const unitLabel = (unit: string) => (unit === "minute" ? "分钟" : unit === "hour" ? "小时" : "天")

function episodeRange(list: number[]): string {
  if (list.length === 0) return "暂无集数信息"
  const sorted = [...list].sort((a, b) => a - b)
  return sorted.length > 1 ? `${sorted[0]}–${sorted[sorted.length - 1]} 共 ${sorted.length} 集` : `第 ${sorted[0]} 集`
}

type Draft = {
  autoCheck: boolean
  intervalValue: number
  intervalUnit: string
  saveRoot: string
  autoDownload: boolean
  scope: "all" | "new" | "list"
  episodeList: number[]
}

function EpisodePicker({ options, picked, onPick }: { options: number[]; picked: number[]; onPick: (list: number[]) => void }) {
  return (
    <div className="flex max-h-[200px] flex-wrap gap-1.5 overflow-y-auto">
      {options.map((ep) => {
        const active = picked.includes(ep)
        return (
          <button
            key={ep}
            onClick={() => onPick(active ? picked.filter((e) => e !== ep) : [...picked, ep].sort((a, b) => a - b))}
            className={`h-7 min-w-[44px] rounded-[6px] border px-2 text-[12px] transition-colors ${
              active
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border-strong bg-card text-secondary-foreground hover:bg-secondary"
            }`}
          >
            E{String(ep).padStart(2, "0")}
          </button>
        )
      })}
    </div>
  )
}

function ConfigForm({ draft, patch, detail, pickEpisodes }: {
  draft: Draft
  patch: (value: Partial<Draft>) => void
  detail: Detail | null
  pickEpisodes: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      <SettingRow title="自动检查更新" hint="关闭后仅可手动检查。">
        <Toggle checked={draft.autoCheck} onChange={(v) => patch({ autoCheck: v })} />
      </SettingRow>
      <SettingRow title="检查周期" hint="每条订阅独立计时，修改后按新周期生效。">
        <div className="flex items-center gap-2">
          <TextInput
            value={String(draft.intervalValue)}
            className="w-[72px]"
            onChange={(v) => patch({ intervalValue: Math.max(1, Math.min(9999, Math.round(Number(v)) || 1)) })}
          />
          <Select value={draft.intervalUnit} options={["minute", "hour", "day"]} onChange={(v) => patch({ intervalUnit: v })} className="w-[90px]" />
          <span className="text-[12px] text-muted-foreground">{unitLabel(draft.intervalUnit)}</span>
        </div>
      </SettingRow>
      <SettingRow title="保存路径" hint="Emby 剧集目录建在此路径下。">
        <TextInput value={draft.saveRoot} mono placeholder="/path/to/media/黄果短剧" onChange={(v) => patch({ saveRoot: v })} className="w-full min-w-[220px] sm:w-[320px]" />
      </SettingRow>
      <SettingRow title="自动下载" hint="开启后发现新集数自动下载；关闭后只提示更新。">
        <Toggle checked={draft.autoDownload} onChange={(v) => patch({ autoDownload: v })} />
      </SettingRow>
      <SettingRow title="下载范围">
        <Segmented
          value={draft.scope}
          options={[
            { value: "all", label: "全部下载" },
            { value: "new", label: "仅后续新增" },
            { value: "list", label: "指定集数" },
          ]}
          onChange={(v) => patch({ scope: v as Draft["scope"] })}
        />
      </SettingRow>
      {draft.scope === "list" && detail && (
        <div className="py-3">
          <div className="mb-2 text-[12px] text-muted-foreground">选择要下载的集数（{episodeRange(detail.episodes)}）</div>
          <EpisodePicker options={detail.episodes} picked={draft.episodeList} onPick={(list) => patch({ episodeList: list })} />
        </div>
      )}
      {pickEpisodes && !detail && <p className="py-2 text-[11px] text-muted-foreground">指定集数需在订阅时选择；编辑时可留空。</p>}
    </div>
  )
}

function SubCover({ id, title }: { id: string; title: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [id])
  return (
    <div className="h-[96px] w-[68px] shrink-0 self-start overflow-hidden rounded-[6px] border border-border bg-secondary sm:self-center">
      {failed ? (
        <div className="flex h-full items-center justify-center text-muted-foreground"><Icon.image size={18} /></div>
      ) : (
        <img
          src={`/api/hg/cover?subscriptionId=${encodeURIComponent(id)}`}
          alt={title}
          loading="lazy"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      )}
    </div>
  )
}

export function Huangguo() {
  const { settings, saveSettings, notify, ready } = useApp()
  const [tab, setTab] = useState<Tab>("我的订阅")
  const [keyword, setKeyword] = useState("")
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<SearchItem[] | null>(null)
  const [subscribedIds, setSubscribedIds] = useState<string[]>([])
  const [subs, setSubs] = useState<Subscription[]>([])
  const [tasks, setTasks] = useState<HgTask[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [subscribeFor, setSubscribeFor] = useState<{ item: SearchItem; detail: Detail } | null>(null)
  const [editSub, setEditSub] = useState<Subscription | null>(null)
  const [downloadFor, setDownloadFor] = useState<Subscription | null>(null)
  const [deleteSub, setDeleteSub] = useState<Subscription | null>(null)
  const [deleteFiles, setDeleteFiles] = useState(false)
  const [downloadPicks, setDownloadPicks] = useState<number[]>([])
  const [draft, setDraft] = useState<Draft>({ autoCheck: true, intervalValue: 6, intervalUnit: "hour", saveRoot: "", autoDownload: true, scope: "all", episodeList: [] })
  const [defaultDraft, setDefaultDraft] = useState<AppSettings>(settings)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])
  useEffect(() => setDefaultDraft(settings), [settings])

  const refresh = useCallback(async () => {
    try {
      const [subView, taskView] = await Promise.all([
        api<{ subscriptions: Subscription[] }>("/hg/subscriptions"),
        api<{ tasks: HgTask[] }>("/hg/tasks"),
      ])
      if (!alive.current) return
      setSubs(subView.subscriptions)
      setTasks(taskView.tasks.slice().reverse())
      setSubscribedIds(subView.subscriptions.map((s) => s.videoId))
    } catch {
      /* 静默：后台轮询失败不打扰 */
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), 3000)
    return () => clearInterval(timer)
  }, [refresh])

  async function runSearch() {
    const value = keyword.trim()
    if (!value) return
    setSearching(true)
    try {
      const response = await api<{ results: SearchItem[]; subscribedVideoIds: string[] }>(
        `/hg/search?keyword=${encodeURIComponent(value)}`,
      )
      if (!alive.current) return
      setResults(response.results)
      setSubscribedIds(response.subscribedVideoIds)
    } catch (error) {
      if (alive.current) notify(errorText(error))
    } finally {
      if (alive.current) setSearching(false)
    }
  }

  function openDetail(item: SearchItem) {
    // 详情弹窗完全复用搜索卡片数据（封面/简介/更新至X集），不再回源采集。
    // 订阅所需的全量集数由 beginSubscribe 自己拉取详情接口。
    setDetail({ ...item, total: 0, episodes: [], premiered: "", actors: "" })
  }

  function beginSubscribe(item: SearchItem, presetDetail: Detail | null) {
    setDraft({ autoCheck: true, intervalValue: settings.hgIntervalValue ?? 6, intervalUnit: settings.hgIntervalUnit ?? "hour", saveRoot: settings.hgSaveRoot || "", autoDownload: true, scope: "all", episodeList: [] })
    void (async () => {
      let full = presetDetail
      if (!full) {
        try {
          full = await api<Detail>(`/hg/detail?videoId=${encodeURIComponent(item.id)}`)
        } catch (error) {
          notify(errorText(error))
          return
        }
      }
      if (alive.current) setSubscribeFor({ item, detail: full })
    })()
  }

  async function submitSubscribe() {
    if (!subscribeFor) return
    if (!draft.saveRoot.trim()) { notify("请先填写保存路径"); return }
    try {
      await api("/hg/subscribe", { info: subscribeFor.item, ...draft })
      notify(`已订阅《${subscribeFor.item.title}》`)
      setSubscribeFor(null)
      await refresh()
    } catch (error) { notify(errorText(error)) }
  }

  async function act(path: string, body: Record<string, unknown>, okText?: string) {
    try {
      await api(path, body)
      if (okText) notify(okText)
      await refresh()
    } catch (error) { notify(errorText(error)) }
  }

  function editSubscription(sub: Subscription) {
    setEditSub(sub)
    setDraft({ autoCheck: sub.autoCheck, intervalValue: sub.intervalValue, intervalUnit: sub.intervalUnit, saveRoot: sub.saveRoot, autoDownload: sub.autoDownload, scope: sub.scope, episodeList: sub.episodeList })
  }

  async function submitEdit() {
    if (!editSub) return
    if (!draft.saveRoot.trim()) { notify("保存路径不能为空"); return }
    try {
      await api("/hg/subscription/update", { subscriptionId: editSub.id, changes: draft })
      notify("订阅已更新，将按新配置检查")
      setEditSub(null)
      await refresh()
    } catch (error) { notify(errorText(error)) }
  }

  const downloadOptions = useMemo(() => {
    if (!downloadFor) return [] as number[]
    const base =
      downloadFor.scope === "list"
        ? downloadFor.episodeList
        : downloadFor.scope === "new"
          ? downloadFor.knownEpisodes.filter((e) => !downloadFor.baseline.includes(e))
          : downloadFor.knownEpisodes
    return base.length > 0 ? base : downloadFor.knownEpisodes
  }, [downloadFor])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={tab} options={TABS} onChange={(v) => setTab(v as Tab)} />
        {tab === "搜索" && (
          <div className="flex min-w-[240px] flex-1 items-center gap-2">
            <TextInput value={keyword} placeholder="输入短剧关键词，回车搜索" onChange={(v) => setKeyword(v)} onEnter={() => void runSearch()} className="h-8 flex-1" />
            <Button variant="primary" onClick={() => void runSearch()} disabled={searching}>
              <Icon.search size={14} />
              {searching ? "搜索中…" : "搜索"}
            </Button>
          </div>
        )}
      </div>

      {ready && !settings.proxyEnabled && (
        <p className="text-[12px] text-[color:var(--status-pending)]">
          提示：黄果站点直连通常不可用，请在“设置 → 高级”开启代理后再搜索或下载。
        </p>
      )}

      {tab === "搜索" && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(results ?? []).map((item) => (
            <SettingShell key={item.id}>
              <div className="flex gap-3 p-3">
                <div className="h-[120px] w-[84px] shrink-0 overflow-hidden rounded-[6px] border border-border bg-secondary">
                  {item.cover ? (
                    <img src={coverSrc(item.cover)} alt={item.title} loading="lazy" className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full items-center justify-center text-muted-foreground"><Icon.image size={18} /></div>
                  )}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-medium text-foreground">{item.title}</span>
                    {subscribedIds.includes(item.id) && (
                      <span className="shrink-0 rounded-full bg-secondary px-1.5 py-[1px] text-[10px] text-muted-foreground">已订阅</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                    {item.episodeLabel && <span>{item.episodeLabel}</span>}
                    {item.score && <span>· {item.score}</span>}
                    {item.tags.slice(0, 3).map((t) => (<span key={t} className="rounded bg-secondary px-1">{t}</span>))}
                  </div>
                  <p className="line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{item.description || "暂无简介"}</p>
                  <div className="mt-auto flex gap-2 pt-1">
                    <Button size="sm" onClick={() => void openDetail(item)}>详情</Button>
                    <Button size="sm" variant="primary" disabled={subscribedIds.includes(item.id)} onClick={() => beginSubscribe(item, detail && detail.id === item.id ? detail : null)}>
                      {subscribedIds.includes(item.id) ? "已订阅" : "添加订阅"}
                    </Button>
                  </div>
                </div>
              </div>
            </SettingShell>
          ))}
          {results !== null && results.length === 0 && (
            <p className="col-span-full py-8 text-center text-[12px] text-muted-foreground">没有找到相关短剧，换个关键词试试。</p>
          )}
          {results === null && (
            <p className="col-span-full py-8 text-center text-[12px] text-muted-foreground">输入关键词开始搜索 huangguoai.com 短剧。</p>
          )}
        </div>
      )}

      {tab === "我的订阅" && (
        <SettingShell>
          {subs.length === 0 && <p className="py-8 text-center text-[12px] text-muted-foreground">还没有订阅，去“搜索”页添加短剧吧。</p>}
          {subs.map((sub) => (
            <div key={sub.id} className="flex flex-col gap-2 border-b border-border py-3 last:border-0 sm:flex-row sm:items-center">
              <SubCover id={sub.id} title={sub.title} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-[13px] font-medium text-foreground">{sub.title}</span>
                  {sub.activeTask && <StatusBadge kind={badgeKind(sub.activeTask.state) as "ready"} label={STATE_LABELS[sub.activeTask.state] ?? sub.activeTask.state} />}
                  {!sub.autoCheck && <StatusBadge kind="pending" label="已暂停" />}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                  <span>更新：已见 {sub.knownEpisodes.length}/{sub.total || "?"} 集</span>
                  <span>已下载 {sub.downloadedCount} 集 · 待处理 {sub.pendingCount} 集</span>
                  <span>{sub.autoCheck ? `每 ${sub.intervalValue} ${unitLabel(sub.intervalUnit)}检查` : "自动检查已暂停"}</span>
                  <span>{sub.scope === "all" ? "全部下载" : sub.scope === "new" ? "仅后续新增" : `指定 ${sub.episodeList.length} 集`}</span>
                  <span>自动下载 {sub.autoDownload ? "开" : "关"}</span>
                  <span title={sub.saveRoot} className="max-w-[260px] truncate">路径：{sub.saveRoot}</span>
                  <span>上次：{sub.lastCheckedIso ? sub.lastCheckedIso.replace("T", " ") : "从未"}</span>
                  <span>下次：{sub.nextCheckIso ? sub.nextCheckIso.replace("T", " ") : "—"}</span>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button size="sm" onClick={() => void act("/hg/check", { subscriptionId: sub.id }, "已开始检查更新（含缺失集数补齐）")}><Icon.refresh size={13} />检查</Button>
                <Button size="sm" onClick={() => void act("/hg/subscription/repair", { subscriptionId: sub.id }, "封面与元数据已重新抓取")}>修复封面</Button>
                <Button size="sm" variant="primary" onClick={() => { setDownloadFor(sub); setDownloadPicks([]) }}><Icon.download size={13} />下载</Button>
                <Button size="sm" onClick={() => void act("/hg/subscription/update", { subscriptionId: sub.id, changes: { autoCheck: !sub.autoCheck } })}>{sub.autoCheck ? "暂停" : "恢复"}</Button>
                <Button size="sm" onClick={() => editSubscription(sub)}>编辑</Button>
                <Button size="sm" variant="danger" onClick={() => setDeleteSub(sub)}>删除</Button>
              </div>
            </div>
          ))}
        </SettingShell>
      )}

      {tab === "下载任务" && (
        <SettingShell>
          {tasks.length === 0 && <p className="py-8 text-center text-[12px] text-muted-foreground">暂无黄果任务。</p>}
          {tasks.map((task) => (
            <div key={task.id} className="border-b border-border py-3 last:border-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium text-foreground">
                  {task.kind === "check" ? "检查更新" : task.kind === "thumb" ? "截帧缩略图" : "下载"}
                  {task.subscriptionTitle && <span className="ml-1 text-[12px] font-normal text-foreground">《{task.subscriptionTitle}》</span>}
                </span>
                <StatusBadge kind={badgeKind(task.state) as "ready"} label={STATE_LABELS[task.state] ?? task.state} />
                <span className="text-[12px] text-muted-foreground">{task.message || "—"}</span>
                {task.kind === "check" && task.finishedAt && (
                  <span className="text-[12px] text-muted-foreground">检测时间 {timeText(task.finishedAt)}</span>
                )}
                {task.currentEpisode != null && <span className="text-[12px] text-muted-foreground">当前第 {task.currentEpisode} 集</span>}
                <div className="ml-auto flex gap-2">
                  {(task.state === "waiting" || task.state === "downloading" || task.state === "checking") && (
                    <Button size="sm" onClick={() => void act("/hg/task/cancel", { taskId: task.id })}>取消</Button>
                  )}
                  {(task.state === "failed" || task.state === "cancelled") && (
                    <Button size="sm" onClick={() => void act("/hg/task/retry", { taskId: task.id })}><Icon.retry size={13} />重试</Button>
                  )}
                </div>
              </div>
              {(task.state === "downloading" || task.state === "checking") && (
                <div className="mt-2"><ProgressBar value={task.progress} indeterminate={task.progress === 0} /></div>
              )}
              {task.error && <p className="mt-1.5 text-[12px] text-[color:var(--status-failed)]">{task.error}</p>}
              {task.detail?.failed?.length ? (
                <p className="mt-1 text-[11px] text-muted-foreground">失败集数：{task.detail.failed.map((f) => `E${f.episode}`).join(", ")}</p>
              ) : null}
            </div>
          ))}
        </SettingShell>
      )}

      {tab === "默认设置" && (
        <SettingShell title="黄果短剧默认配置">
          <p className="pt-2 text-[12px] text-muted-foreground">以下默认值用于新增订阅；每条订阅的独立配置优先，修改默认值不会改动已有订阅。</p>
          <SettingRow title="默认保存路径" hint="新增订阅的默认下载根目录。">
            <TextInput value={defaultDraft.hgSaveRoot ?? ""} mono onChange={(v) => setDefaultDraft({ ...defaultDraft, hgSaveRoot: v })} className="w-full min-w-[220px] sm:w-[320px]" />
          </SettingRow>
          <SettingRow title="默认检查周期">
            <div className="flex items-center gap-2">
              <TextInput value={String(defaultDraft.hgIntervalValue ?? 6)} className="w-[72px]" onChange={(v) => setDefaultDraft({ ...defaultDraft, hgIntervalValue: Math.max(1, Math.min(9999, Math.round(Number(v)) || 1)) })} />
              <Select value={defaultDraft.hgIntervalUnit ?? "hour"} options={["minute", "hour", "day"]} onChange={(v) => setDefaultDraft({ ...defaultDraft, hgIntervalUnit: v as AppSettings["hgIntervalUnit"] })} className="w-[90px]" />
            </div>
          </SettingRow>
          <SettingRow title="下载并发数" hint="单集 HLS 分片并发下载数（1–8）。">
            <TextInput value={String(defaultDraft.hgConcurrent ?? 4)} className="w-[72px]" onChange={(v) => setDefaultDraft({ ...defaultDraft, hgConcurrent: Math.max(1, Math.min(8, Math.round(Number(v)) || 1)) })} />
          </SettingRow>
          <SettingRow title="失败重试次数" hint="每集下载失败后的自动重试次数（0–5）。">
            <TextInput value={String(defaultDraft.hgRetries ?? 2)} className="w-[72px]" onChange={(v) => setDefaultDraft({ ...defaultDraft, hgRetries: Math.max(0, Math.min(5, Math.round(Number(v)) || 0)) })} />
          </SettingRow>
          <SettingRow title="重试间隔（秒）">
            <TextInput value={String(defaultDraft.hgRetryInterval ?? 30)} className="w-[72px]" onChange={(v) => setDefaultDraft({ ...defaultDraft, hgRetryInterval: Math.max(0, Math.min(3600, Math.round(Number(v)) || 0)) })} />
          </SettingRow>
          <div className="py-3">
            <Button variant="primary" onClick={() => {
              if (!defaultDraft.hgSaveRoot?.trim()) { notify("默认保存路径不能为空"); return }
              void saveSettings(defaultDraft).then(() => notify("黄果默认配置已保存")).catch((error) => notify(errorText(error)))
            }}>保存默认配置</Button>
          </div>
        </SettingShell>
      )}

      {subscribeFor && (
        <Modal title={`订阅《${subscribeFor.item.title}》`} onClose={() => setSubscribeFor(null)}>
          <div className="mb-2 text-[12px] text-muted-foreground">
            更新至{subscribeFor.detail.total || subscribeFor.detail.episodes.length}集
            {subscribeFor.detail.tags.length > 0 && ` · ${subscribeFor.detail.tags.join(" / ")}`}
          </div>
          <ConfigForm draft={draft} patch={(value) => setDraft({ ...draft, ...value })} detail={subscribeFor.detail} pickEpisodes={false} />
          <div className="flex justify-end gap-2 py-3">
            <Button onClick={() => setSubscribeFor(null)}>取消</Button>
            <Button variant="primary" onClick={() => void submitSubscribe()}>确认订阅</Button>
          </div>
        </Modal>
      )}

      {editSub && (
        <Modal title={`编辑订阅《${editSub.title}》`} onClose={() => setEditSub(null)}>
          <ConfigForm draft={draft} patch={(value) => setDraft({ ...draft, ...value })} detail={null} pickEpisodes={false} />
          <p className="py-2 text-[11px] text-muted-foreground">指定集数范围如需变更，请删除后重新订阅。</p>
          <div className="flex justify-end gap-2 pb-3">
            <Button onClick={() => setEditSub(null)}>取消</Button>
            <Button variant="primary" onClick={() => void submitEdit()}>保存修改</Button>
          </div>
        </Modal>
      )}

      {downloadFor && (
        <Modal title={`下载《${downloadFor.title}》`} onClose={() => setDownloadFor(null)}>
          <div className="mb-2 text-[12px] text-muted-foreground">勾选要下载的集数（候选 {episodeRange(downloadOptions)}）；不勾选则下载全部缺失集。</div>
          <EpisodePicker options={downloadOptions} picked={downloadPicks} onPick={setDownloadPicks} />
          <div className="flex justify-end gap-2 py-3">
            <Button onClick={() => setDownloadFor(null)}>取消</Button>
            <Button onClick={() => { void act("/hg/download", { subscriptionId: downloadFor.id }, "已加入下载队列"); setDownloadFor(null) }}>下载全部缺失</Button>
            <Button variant="primary" disabled={downloadPicks.length === 0} onClick={() => { void act("/hg/download", { subscriptionId: downloadFor.id, episodes: downloadPicks }, "已加入下载队列"); setDownloadFor(null) }}>
              下载所选 {downloadPicks.length || ""} 集
            </Button>
          </div>
        </Modal>
      )}

      {deleteSub && (
        <Modal title={`删除订阅《${deleteSub.title}》`} onClose={() => setDeleteSub(null)}>
          <p className="py-2 text-[12px] leading-relaxed text-muted-foreground">
            默认仅删除订阅与检查计划，已下载的 {deleteSub.downloadedCount} 集文件会保留。
          </p>
          <label className="flex items-center gap-2 py-2 text-[12px] text-foreground">
            <input type="checkbox" checked={deleteFiles} onChange={(e) => setDeleteFiles(e.target.checked)} />
            同时删除已下载文件（{deleteSub.saveRoot}，不可恢复）
          </label>
          <div className="flex justify-end gap-2 py-3">
            <Button onClick={() => setDeleteSub(null)}>取消</Button>
            <Button
              variant="danger"
              onClick={() => {
                void act("/hg/subscription/remove", { subscriptionId: deleteSub.id, keepFiles: !deleteFiles },
                  deleteFiles ? "订阅与文件已删除" : "订阅已删除，文件保留")
                setDeleteSub(null)
                setDeleteFiles(false)
              }}
            >
              {deleteFiles ? "删除订阅和文件" : "仅删除订阅"}
            </Button>
          </div>
        </Modal>
      )}

      {detail && !subscribeFor && (
        <Modal title={detail.title} onClose={() => setDetail(null)} width="max-w-[720px]">
          <div className="flex gap-4">
            <div className="h-[180px] w-[128px] shrink-0 overflow-hidden rounded-[6px] border border-border">
              {detail.cover && <img src={coverSrc(detail.cover)} alt={detail.title} className="h-full w-full object-cover" />}
            </div>
            <div className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted-foreground">
              <p>{detail.description || "暂无简介"}</p>
              <p className="mt-2">{detail.episodeLabel || (detail.total ? `更新至${detail.total}集` : "")}{detail.premiered && ` · ${detail.premiered} 年`}</p>
              {detail.tags.length > 0 && <p className="mt-1">标签：{detail.tags.join(" / ")}</p>}
              <p className="mt-2"><a className="text-primary underline" href={detail.url} target="_blank" rel="noreferrer">打开原始网页</a></p>
            </div>
          </div>
          <div className="flex justify-end gap-2 py-3">
            <Button onClick={() => setDetail(null)}>关闭</Button>
            <Button variant="primary" disabled={subscribedIds.includes(detail.id)} onClick={() => { const item = { ...detail }; setDetail(null); beginSubscribe(item, detail.total || detail.episodes.length ? detail : null) }}>
              {subscribedIds.includes(detail.id) ? "已订阅" : "添加订阅"}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
