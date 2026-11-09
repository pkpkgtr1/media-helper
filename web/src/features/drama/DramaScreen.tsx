import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useApp } from "../../state"
import { api } from "../../lib/api"
import { episodeRange, errorText } from "../../lib/format"
import { Button, Modal, ProgressBar, Segmented, SettingRow, Select, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { DramaDetail, DramaSearchItem, DramaTask, SourceRef, Subscription } from "../../lib/types"
import {
  ConfigForm,
  type Draft,
} from "./ConfigForm"
import { SearchTab } from "./SearchTab"
import { SubscriptionTab } from "./SubscriptionTab"
import { TaskTab } from "./TaskTab"
import {
  EpisodePicker,
  SOURCE_FALLBACK,
  SourceBadge,
  coverSrc,
  itemKey,
  sourceKeyOf,
  sourceLabelOf,
} from "./shared"

type Tab = "搜索" | "我的订阅" | "下载任务" | "默认设置"

const TABS = [
  { value: "搜索", label: "搜索" },
  { value: "我的订阅", label: "我的订阅" },
  { value: "下载任务", label: "下载任务" },
  { value: "默认设置", label: "默认设置" },
] as const

export function DramaScreen() {
  const { settings, saveSettings, notify, ready } = useApp()
  const [tab, setTab] = useState<Tab>("我的订阅")
  const [keyword, setKeyword] = useState("")
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<DramaSearchItem[] | null>(null)
  const [subscribedKeys, setSubscribedKeys] = useState<string[]>([])
  const [sources, setSources] = useState<SourceRef[]>(SOURCE_FALLBACK)
  const [sourceFilter, setSourceFilter] = useState("all")
  const [subs, setSubs] = useState<Subscription[]>([])
  const [tasks, setTasks] = useState<DramaTask[]>([])

  const [detail, setDetail] = useState<DramaDetail | null>(null)
  const [subscribeFor, setSubscribeFor] = useState<{ item: DramaSearchItem; detail: DramaDetail } | null>(null)
  const [editSub, setEditSub] = useState<Subscription | null>(null)
  const [downloadFor, setDownloadFor] = useState<Subscription | null>(null)
  const [deleteSub, setDeleteSub] = useState<Subscription | null>(null)
  const [deleteFiles, setDeleteFiles] = useState(false)
  const [downloadPicks, setDownloadPicks] = useState<number[]>([])

  const [draft, setDraft] = useState<Draft>({
    autoCheck: true,
    intervalValue: 6,
    intervalUnit: "hour",
    saveRoot: "",
    autoDownload: true,
    scope: "all",
    episodeList: [],
  })

  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [subView, taskView] = await Promise.all([
        api<{ subscriptions: Subscription[] }>("/hg/subscriptions"),
        api<{ tasks: DramaTask[] }>("/hg/tasks"),
      ])
      if (!alive.current) return
      setSubs(subView.subscriptions)
      setTasks(taskView.tasks.slice().reverse())
      setSubscribedKeys(subView.subscriptions.map((sub) => `${sourceKeyOf(sub)}:${sub.videoId}`))
    } catch {
      /* 静默：后台轮询失败不打扰用户 */
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), 3000)
    return () => clearInterval(timer)
  }, [refresh])

  /* ------------------------------------------------------------- 搜索 */

  async function runSearch() {
    const value = keyword.trim()
    if (!value) {
      notify("请输入搜索关键词")
      return
    }
    setSearching(true)
    try {
      const response = await api<{
        results: DramaSearchItem[]
        sources?: SourceRef[]
        subscribedKeys?: string[]
        subscribedVideoIds?: string[]
        errors?: string[]
      }>(`/hg/search?keyword=${encodeURIComponent(value)}`)
      if (!alive.current) return
      setResults(response.results)
      if (response.sources?.length) setSources(response.sources)
      setSubscribedKeys(
        response.subscribedKeys ?? (response.subscribedVideoIds ?? []).map((id) => `huangguo:${id}`),
      )
      if (response.errors?.length) notify(response.errors.join("；"))
      else notify(`找到 ${response.results.length} 个结果`)
    } catch (error) {
      if (alive.current) notify(errorText(error))
    } finally {
      if (alive.current) setSearching(false)
    }
  }

  /** 详情弹窗打开后再补全集数与简介，避免空白等待。 */
  async function openDetail(item: DramaSearchItem) {
    setDetail({ ...item, total: 0, episodes: [], premiered: "", actors: "" })
    try {
      const full = await api<DramaDetail>(
        `/hg/detail?videoId=${encodeURIComponent(item.id)}&source=${sourceKeyOf(item)}`,
      )
      if (alive.current && full) setDetail({ ...full, source: sourceKeyOf(item) })
    } catch (error) {
      if (alive.current) notify(errorText(error))
    }
  }

  function beginSubscribe(item: DramaSearchItem, preset: DramaDetail | null) {
    setDraft({
      autoCheck: true,
      intervalValue: settings.hgIntervalValue ?? 6,
      intervalUnit: settings.hgIntervalUnit ?? "hour",
      saveRoot: settings.hgSaveRoot || "",
      autoDownload: true,
      scope: "all",
      episodeList: [],
    })
    void (async () => {
      let full = preset
      if (!full) {
        try {
          const fetched = await api<DramaDetail>(
            `/hg/detail?videoId=${encodeURIComponent(item.id)}&source=${sourceKeyOf(item)}`,
          )
          full = { ...fetched, source: sourceKeyOf(item), sourceLabel: fetched.sourceLabel || sourceLabelOf(item) }
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
    if (!draft.saveRoot.trim()) {
      notify("请先填写保存路径")
      return
    }
    try {
      await api("/hg/subscribe", {
        info: { ...subscribeFor.item, source: sourceKeyOf(subscribeFor.item) },
        ...draft,
      })
      notify(`已订阅《${subscribeFor.item.title}》`)
      setSubscribeFor(null)
      await refresh()
    } catch (error) {
      notify(errorText(error))
    }
  }

  /* ----------------------------------------------------------- 订阅操作 */

  async function act(path: string, body: Record<string, unknown>, okText?: string) {
    try {
      await api(path, body)
      if (okText) notify(okText)
      await refresh()
    } catch (error) {
      notify(errorText(error))
    }
  }

  function editSubscription(sub: Subscription) {
    setEditSub(sub)
    setDraft({
      autoCheck: sub.autoCheck,
      intervalValue: sub.intervalValue,
      intervalUnit: sub.intervalUnit,
      saveRoot: sub.saveRoot,
      autoDownload: sub.autoDownload,
      scope: sub.scope,
      episodeList: sub.episodeList,
    })
  }

  async function submitEdit() {
    if (!editSub) return
    if (!draft.saveRoot.trim()) {
      notify("保存路径不能为空")
      return
    }
    try {
      await api("/hg/subscription/update", { subscriptionId: editSub.id, changes: draft })
      notify("订阅已更新，将按新配置检查")
      setEditSub(null)
      await refresh()
    } catch (error) {
      notify(errorText(error))
    }
  }

  const runningCount = useMemo(
    () => tasks.filter((t) => t.state === "waiting" || t.state === "downloading" || t.state === "checking").length,
    [tasks],
  )

  const downloadOptions = useMemo(() => {
    if (!downloadFor) return []
    const base =
      downloadFor.scope === "list"
        ? downloadFor.episodeList
        : downloadFor.scope === "new"
          ? downloadFor.knownEpisodes.filter((ep) => !downloadFor.baseline.includes(ep))
          : downloadFor.knownEpisodes
    return base.length > 0 ? base : downloadFor.knownEpisodes
  }, [downloadFor])

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 页签固定在顶部，只有下方内容滚动 */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line bg-card px-4 py-2.5">
        <Segmented label="短剧页签" value={tab} options={TABS} onChange={(v) => setTab(v as Tab)} />
        <span className="text-[12px] text-muted-fg">
          {tab === "我的订阅" && `${subs.length} 条订阅${runningCount > 0 ? ` · ${runningCount} 条任务进行中` : ""}`}
          {tab === "下载任务" && `${tasks.length} 条记录`}
          {tab === "搜索" && "同时查询黄果与野果"}
          {tab === "默认设置" && "修改后影响新增订阅"}
        </span>
        {ready && !settings.proxyEnabled ? (
          <span className="ml-auto text-[12px] text-pending">
            提示：黄果与野果直连通常不可用，请在设置里开启代理。
          </span>
        ) : null}
      </div>

      {tab === "搜索" ? (
        <SearchTab
          keyword={keyword}
          onKeyword={setKeyword}
          onSearch={() => void runSearch()}
          searching={searching}
          results={results}
          sources={sources}
          sourceFilter={sourceFilter}
          onSourceFilter={setSourceFilter}
          subscribedKeys={subscribedKeys}
          onDetail={(item) => void openDetail(item)}
          onSubscribe={(item) => beginSubscribe(item, null)}
        />
      ) : null}

      {tab === "我的订阅" ? (
        <SubscriptionTab
          subs={subs}
          onCreate={() => setTab("搜索")}
          onCheck={(sub) => void act("/hg/check", { subscriptionId: sub.id }, "已开始检查更新（含缺失集数补齐）")}
          onRepair={(sub) => void act("/hg/subscription/repair", { subscriptionId: sub.id }, "封面与元数据已重新抓取")}
          onDownload={(sub) => {
            setDownloadFor(sub)
            setDownloadPicks([])
          }}
          onEdit={editSubscription}
          onToggle={(sub) =>
            void act(
              "/hg/subscription/update",
              { subscriptionId: sub.id, changes: { autoCheck: !sub.autoCheck } },
              sub.autoCheck ? "已暂停自动检查" : "已恢复自动检查",
            )
          }
          onRemove={(sub) => {
            setDeleteSub(sub)
            setDeleteFiles(false)
          }}
        />
      ) : null}

      {tab === "下载任务" ? (
        <TaskTab
          tasks={tasks}
          runningCount={runningCount}
          onCancel={(task) => void act("/hg/task/cancel", { taskId: task.id })}
          onRetry={(task) => void act("/hg/task/retry", { taskId: task.id })}
          onClear={() => void act("/hg/task/clear", {}, "任务记录已清空")}
        />
      ) : null}

      {tab === "默认设置" ? (
        <DefaultSettings
          settings={settings}
          onSave={(next) => void saveSettings(next).then(() => notify("短剧默认配置已保存")).catch((e) => notify(errorText(e)))}
        />
      ) : null}

      {/* --------------------------------------------------------- 弹窗 */}

      {detail ? (
        <Modal
          title={detail.title}
          onClose={() => setDetail(null)}
          width="max-w-[720px]"
          footer={
            <>
              <Button onClick={() => setDetail(null)}>关闭</Button>
              <a
                href={detail.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-card px-3 text-[13px] font-medium text-fg transition-colors hover:bg-elevated"
              >
                <Icon.link size={14} />
                原始网页
              </a>
              <Button
                variant="accent"
                disabled={subscribedKeys.includes(itemKey(detail))}
                onClick={() => {
                  const item = detail
                  setDetail(null)
                  beginSubscribe(item, item.total || item.episodes.length ? item : null)
                }}
              >
                {subscribedKeys.includes(itemKey(detail)) ? "已订阅" : "添加订阅"}
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="h-[180px] w-[128px] shrink-0 overflow-hidden rounded-md border border-line bg-elevated">
              {detail.cover ? (
                <img src={coverSrc(detail.cover, detail.source)} alt={`${detail.title} 封面`} className="h-full w-full object-cover" />
              ) : null}
            </div>
            <div className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted-fg">
              <p className="mb-1.5">
                <SourceBadge item={detail} />
              </p>
              <p className="text-fg">{detail.description || "暂无简介"}</p>
              <p className="mt-2">
                {detail.episodeLabel || (detail.total ? `更新至${detail.total}集` : "集数未知")}
                {detail.premiered ? ` · ${detail.premiered} 年` : ""}
              </p>
              {detail.tags.length > 0 ? <p className="mt-1">标签：{detail.tags.join(" / ")}</p> : null}
            </div>
          </div>
        </Modal>
      ) : null}

      {subscribeFor ? (
        <Modal
          title={`订阅《${subscribeFor.item.title}》`}
          onClose={() => setSubscribeFor(null)}
          width="max-w-[620px]"
          footer={
            <>
              <Button onClick={() => setSubscribeFor(null)}>取消</Button>
              <Button variant="accent" onClick={() => void submitSubscribe()}>
                确认订阅
              </Button>
            </>
          }
        >
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px] text-muted-fg">
            <SourceBadge item={subscribeFor.item} />
            <span>
              更新至 {subscribeFor.detail.total || subscribeFor.detail.episodes.length} 集
              {subscribeFor.detail.tags.length > 0 ? ` · ${subscribeFor.detail.tags.join(" / ")}` : ""}
            </span>
          </div>
          <ConfigForm
            draft={draft}
            patch={(value) => setDraft({ ...draft, ...value })}
            detail={subscribeFor.detail}
            pickEpisodes={false}
          />
        </Modal>
      ) : null}

      {editSub ? (
        <Modal
          title={`编辑订阅《${editSub.title}》`}
          onClose={() => setEditSub(null)}
          width="max-w-[620px]"
          footer={
            <>
              <Button onClick={() => setEditSub(null)}>取消</Button>
              <Button variant="accent" onClick={() => void submitEdit()}>
                保存修改
              </Button>
            </>
          }
        >
          <ConfigForm draft={draft} patch={(value) => setDraft({ ...draft, ...value })} detail={null} pickEpisodes={false} />
          <p className="py-2 text-[11px] text-muted-fg">指定集数范围如需变更，请删除后重新订阅。</p>
        </Modal>
      ) : null}

      {downloadFor ? (
        <Modal
          title={`下载《${downloadFor.title}》`}
          onClose={() => setDownloadFor(null)}
          width="max-w-[620px]"
          footer={
            <>
              <Button onClick={() => setDownloadFor(null)}>取消</Button>
              <Button
                onClick={() => {
                  void act("/hg/download", { subscriptionId: downloadFor.id }, "已加入下载队列")
                  setDownloadFor(null)
                }}
              >
                下载全部缺失
              </Button>
              <Button
                variant="accent"
                disabled={downloadPicks.length === 0}
                onClick={() => {
                  void act("/hg/download", { subscriptionId: downloadFor.id, episodes: downloadPicks }, "已加入下载队列")
                  setDownloadFor(null)
                }}
              >
                下载所选 {downloadPicks.length || ""} 集
              </Button>
            </>
          }
        >
          <p className="mb-2 text-[12px] text-muted-fg">
            勾选要下载的集数（候选 {episodeRange(downloadOptions)}）；不勾选则下载全部缺失集。
          </p>
          <EpisodePicker options={downloadOptions} picked={downloadPicks} onPick={setDownloadPicks} />
          {downloadOptions.length > 0 ? (
            <div className="mt-3">
              <ProgressBar value={(downloadPicks.length / downloadOptions.length) * 100} tone="ready" label="已选比例" />
            </div>
          ) : null}
        </Modal>
      ) : null}

      {deleteSub ? (
        <Modal
          title={`删除订阅《${deleteSub.title}》`}
          onClose={() => setDeleteSub(null)}
          footer={
            <>
              <Button onClick={() => setDeleteSub(null)}>取消</Button>
              <Button
                variant="danger"
                onClick={() => {
                  void act(
                    "/hg/subscription/remove",
                    { subscriptionId: deleteSub.id, keepFiles: !deleteFiles },
                    deleteFiles ? "订阅与文件已删除" : "订阅已删除，文件保留",
                  )
                  setDeleteSub(null)
                  setDeleteFiles(false)
                }}
              >
                {deleteFiles ? "删除订阅和文件" : "仅删除订阅"}
              </Button>
            </>
          }
        >
          <p className="py-2 text-[12px] leading-relaxed text-muted-fg">
            默认仅删除订阅与检查计划，已下载的 {deleteSub.downloadedCount} 集文件会保留。
          </p>
          <label className="flex cursor-pointer items-start gap-2 py-2 text-[12px] text-fg">
            <input
              type="checkbox"
              checked={deleteFiles}
              onChange={(event) => setDeleteFiles(event.target.checked)}
              className="mt-0.5 h-4 w-4 cursor-pointer accent-[var(--danger)]"
            />
            <span>
              同时删除已下载文件
              <span className="mt-0.5 block font-mono text-[11px] break-all text-muted-fg">
                {deleteSub.saveRoot}（不可恢复）
              </span>
            </span>
          </label>
        </Modal>
      ) : null}
    </div>
  )
}

/** 默认设置页签：只影响新增订阅，不改动已有订阅。 */
function DefaultSettings({
  settings,
  onSave,
}: {
  settings: import("../../lib/types").AppSettings
  onSave: (next: import("../../lib/types").AppSettings) => void
}) {
  const [draft, setDraft] = useState(settings)
  useEffect(() => setDraft(settings), [settings])
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <div className="mx-auto max-w-[820px]">
        <section className="rounded-lg border border-line bg-card shadow-[var(--shadow-sm)]">
          <header className="border-b border-line px-4 py-3">
            <h2 className="text-[13px] font-semibold text-fg">AI短剧默认配置</h2>
            <p className="mt-0.5 text-[12px] text-muted-fg">
              以下默认值用于新增订阅；每条订阅的独立配置优先，修改默认值不会改动已有订阅。
            </p>
          </header>
          <div className="px-4">
            <DramaDefaults draft={draft} patch={(value) => setDraft({ ...draft, ...value })} />
          </div>
        </section>
        <div className="mt-3 flex items-center gap-2">
          <Button variant="accent" disabled={!dirty} onClick={() => onSave(draft)}>
            保存默认配置
          </Button>
          {dirty ? <span className="text-[12px] text-pending">有未保存的更改</span> : null}
        </div>
      </div>
    </div>
  )
}

function DramaDefaults({
  draft,
  patch,
}: {
  draft: import("../../lib/types").AppSettings
  patch: (value: Partial<import("../../lib/types").AppSettings>) => void
}) {
  return (
    <>
      <SettingRow title="默认保存路径" hint="新增订阅的默认下载根目录。">
        <TextInput
          value={draft.hgSaveRoot ?? ""}
          mono
          ariaLabel="默认保存路径"
          onChange={(hgSaveRoot) => patch({ hgSaveRoot })}
          className="w-full min-w-[220px] sm:w-[340px]"
        />
      </SettingRow>
      <SettingRow title="默认检查周期">
        <div className="flex items-center gap-2">
          <TextInput
            value={String(draft.hgIntervalValue ?? 6)}
            ariaLabel="默认检查周期数值"
            className="w-[72px]"
            onChange={(v) =>
              patch({ hgIntervalValue: Math.max(1, Math.min(9999, Math.round(Number(v)) || 1)) })
            }
          />
          <Select
            value={draft.hgIntervalUnit ?? "hour"}
            options={[
              { value: "minute", label: "分钟" },
              { value: "hour", label: "小时" },
              { value: "day", label: "天" },
            ]}
            ariaLabel="默认检查周期单位"
            onChange={(hgIntervalUnit) => patch({ hgIntervalUnit })}
            className="w-[92px]"
          />
        </div>
      </SettingRow>
      <SettingRow title="下载并发数" hint="单集 HLS 分片并发下载数（1–8）。">
        <TextInput
          value={String(draft.hgConcurrent ?? 4)}
          ariaLabel="下载并发数"
          className="w-[72px]"
          onChange={(v) => patch({ hgConcurrent: Math.max(1, Math.min(8, Math.round(Number(v)) || 1)) })}
        />
      </SettingRow>
      <SettingRow title="失败重试次数" hint="每集下载失败后的自动重试次数（0–5）。">
        <TextInput
          value={String(draft.hgRetries ?? 2)}
          ariaLabel="失败重试次数"
          className="w-[72px]"
          onChange={(v) => patch({ hgRetries: Math.max(0, Math.min(5, Math.round(Number(v)) || 0)) })}
        />
      </SettingRow>
      <SettingRow title="重试间隔（秒）">
        <TextInput
          value={String(draft.hgRetryInterval ?? 30)}
          ariaLabel="重试间隔秒"
          className="w-[72px]"
          onChange={(v) => patch({ hgRetryInterval: Math.max(0, Math.min(3600, Math.round(Number(v)) || 0)) })}
        />
      </SettingRow>
    </>
  )
}
