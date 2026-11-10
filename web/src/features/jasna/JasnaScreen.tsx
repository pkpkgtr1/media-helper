import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Button, Card, Select, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { api, apiGet } from "../../lib/api"
import { copyText } from "../../lib/clipboard"
import { errorText, timeText } from "../../lib/format"
import type { LtxDetail, LtxItem, LtxPage, LtxStatus } from "../../lib/types"
import { useApp } from "../../state"

const PAGE_SIZE = 48

const SORTS = [
  { value: "date", label: "按发行日期" },
  { value: "score", label: "按评分" },
  { value: "votes", label: "按热度" },
  { value: "added", label: "按收录时间" },
] as const

type Sort = (typeof SORTS)[number]["value"]

/** Jasna 资源库：本地 SQLite（config/ltxdb/ltx.db）的浏览与搜索。 */
export function JasnaScreen() {
  const { notify, settings } = useApp()
  const [data, setData] = useState<LtxPage | null>(null)
  const [status, setStatus] = useState<LtxStatus | null>(null)
  const [keyword, setKeyword] = useState("")
  const [query, setQuery] = useState("")
  const [maker, setMaker] = useState("")
  const [genre, setGenre] = useState("")
  const [sort, setSort] = useState<Sort>("date")
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState("")
  const [detail, setDetail] = useState<LtxDetail | null>(null)
  const [makers, setMakers] = useState<string[]>([])
  const [genres, setGenres] = useState<string[]>([])
  const sequence = useRef(0)

  const load = useCallback(async () => {
    const request = ++sequence.current
    setLoading(true)
    try {
      const result = await apiGet<LtxPage>("/ltx/items", {
        keyword: query,
        maker,
        genre,
        sort,
        page,
        limit: PAGE_SIZE,
      })
      if (sequence.current !== request) return
      setData(result)
      setError("")
    } catch (error) {
      if (sequence.current !== request) return
      setData(null)
      setError(errorText(error))
    } finally {
      if (sequence.current === request) setLoading(false)
    }
  }, [query, maker, genre, sort, page])

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await api<LtxStatus>("/ltx/status"))
    } catch {
      /* 状态失败不影响列表，界面会显示「未知」 */
    }
  }, [])

  const loadFilters = useCallback(async () => {
    try {
      const result = await apiGet<{ makers: { name: string }[]; genres: Record<string, string[]> }>(
        "/ltx/filters",
      )
      setMakers(result.makers.map((row) => row.name))
      setGenres(Object.values(result.genres).map((names) => names[0]).filter(Boolean))
    } catch {
      /* 过滤项拿不到时退化为纯关键词搜索 */
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void loadStatus()
    void loadFilters()
  }, [loadStatus, loadFilters])

  function submit() {
    setPage(1)
    setQuery(keyword.trim())
  }

  async function syncNow() {
    setSyncing(true)
    try {
      const report = await api<{ total: number; added: number; seconds: number }>("/ltx/sync", {})
      notify(`资源库已同步：库内 ${report.total} 条，用时 ${report.seconds}s`)
      await Promise.all([load(), loadStatus(), loadFilters()])
    } catch (error) {
      notify(errorText(error))
    } finally {
      setSyncing(false)
    }
  }

  async function openDetail(item: LtxItem) {
    try {
      setDetail(await apiGet<LtxDetail>("/ltx/detail", { code: item.code }))
    } catch (error) {
      notify(errorText(error))
    }
  }

  async function copy(text: string) {
    try {
      await copyText(text)
      notify("链接已复制到剪贴板")
    } catch {
      notify("复制失败，请手动选择链接文本")
    }
  }

  const intervalText = useMemo(() => {
    if (!status?.enabled) return "自动同步已关闭"
    const seconds = status.intervalSeconds || 21600
    const text =
      seconds % 86400 === 0
        ? `${seconds / 86400} 天`
        : seconds % 3600 === 0
          ? `${seconds / 3600} 小时`
          : `${Math.round(seconds / 60)} 分钟`
    return `每 ${text}自动同步`
  }, [status])

  const empty = data !== null && data.total === 0
  const neverSynced = status !== null && !status.ready

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 顶部：搜索 + 过滤 + 同步 */}
      <div className="shrink-0 border-b border-line bg-panel px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-fg">
              <Icon.search size={14} />
            </span>
            <TextInput
              value={keyword}
              placeholder="搜索番号、标题、演员、厂商或导演，回车搜索"
              ariaLabel="Jasna 资源库关键词"
              onChange={setKeyword}
              onEnter={submit}
              className="pl-8"
            />
          </div>
          <Button variant="accent" onClick={submit} disabled={loading}>
            <Icon.search size={14} />
            {loading ? "查询中…" : "搜索"}
          </Button>
          {query ? (
            <Button
              variant="ghost"
              onClick={() => {
                setKeyword("")
                setQuery("")
                setPage(1)
              }}
            >
              清空
            </Button>
          ) : null}
          <Button disabled={syncing} onClick={() => void syncNow()}>
            <Icon.refresh size={14} />
            {syncing ? "同步中…" : "立即同步"}
          </Button>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Select
            value={maker}
            options={[{ value: "", label: "全部厂商" }, ...makers.map((name) => ({ value: name, label: name }))]}
            ariaLabel="厂商筛选"
            onChange={(value) => {
              setMaker(value)
              setPage(1)
            }}
            className="w-[168px]"
          />
          <Select
            value={genre}
            options={[{ value: "", label: "全部分类" }, ...genres.map((name) => ({ value: name, label: name }))]}
            ariaLabel="分类筛选"
            onChange={(value) => {
              setGenre(value)
              setPage(1)
            }}
            className="w-[148px]"
          />
          <Select
            value={sort}
            options={SORTS.map((row) => ({ value: row.value, label: row.label }))}
            ariaLabel="排序方式"
            onChange={(value) => {
              setSort(value)
              setPage(1)
            }}
            className="w-[132px]"
          />
          <span className="ml-auto text-[11px] text-muted-fg">
            {data ? `共 ${data.total} 条` : "—"}
            {status?.ready ? ` · ${intervalText}` : ""}
            {status?.nextSync ? ` · 下次 ${timeText(status.nextSync)}` : ""}
            {status?.syncedAt ? ` · 上次 ${timeText(status.syncedAt)}` : ""}
          </span>
        </div>
      </div>

      {status?.lastError ? (
        <div className="shrink-0 border-b border-line bg-failed-soft px-4 py-2 text-[12px] text-failed">
          上次同步失败：{status.lastError}
        </div>
      ) : null}
      {error ? (
        <div className="shrink-0 border-b border-line bg-failed-soft px-4 py-2 text-[12px] text-failed">
          {error}
        </div>
      ) : null}

      {/* 列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {neverSynced ? (
          <Placeholder
            title="资源库还没有数据"
            detail={
              settings.ltxSyncEnabled
                ? `后台会在 ${intervalText.replace("自动同步", "")}内自动拉取一次；也可以点右上角「立即同步」马上开始。`
                : "自动同步已关闭，请点右上角「立即同步」手动拉取一次，或在设置 → 常规中开启自动同步。"
            }
            onSync={() => void syncNow()}
            syncing={syncing}
          />
        ) : empty ? (
          <Placeholder title="没有匹配的结果" detail="换个关键词，或清空厂商与分类筛选再试。" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
              {(data?.items ?? []).map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => void openDetail(item)}
                  className="group flex cursor-pointer flex-col overflow-hidden rounded-lg border border-line bg-card text-left transition-colors duration-150 hover:border-muted-fg/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  <span className="flex aspect-[3/2] items-center justify-center overflow-hidden bg-elevated text-muted-fg">
                    {item.cover ? (
                      <CoverImage src={`/api/ltx/cover?url=${encodeURIComponent(item.cover)}`} alt={`${item.code} 封面`} />
                    ) : (
                      <Icon.image size={22} />
                    )}
                  </span>
                  <span className="flex min-w-0 flex-col gap-1.5 px-3 py-2.5">
                    <span className="flex items-center gap-1.5">
                      <span className="font-mono text-[12px] font-semibold text-accent">{item.code}</span>
                      {item.pending ? (
                        <span className="rounded-full bg-pending-soft px-1.5 text-[10px] text-pending">待补</span>
                      ) : null}
                      {item.subtitle ? (
                        <span className="rounded-full bg-elevated px-1.5 text-[10px] text-muted-fg">字幕</span>
                      ) : null}
                    </span>
                    <span className="line-clamp-2 text-[13px] leading-snug text-fg">
                      {item.titleZh || item.title}
                    </span>
                    <span className="truncate text-[12px] text-muted-fg">
                      {[item.date, item.maker].filter(Boolean).join(" · ")}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            {data && data.pages > 1 ? (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Button disabled={page <= 1 || loading} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  上一页
                </Button>
                <span className="text-[12px] text-muted-fg">
                  第 {data.page} / {data.pages} 页
                </span>
                <Button
                  disabled={page >= data.pages || loading}
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                >
                  下一页
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>

      {detail ? <DetailDialog item={detail} onClose={() => setDetail(null)} onCopy={copy} /> : null}
    </div>
  )
}

/** 封面：上游偶尔 404（如已下架条目），失败时退化为占位图标而不是破图。 */
function CoverImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <Icon.image size={18} />
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-full w-full object-contain"
    />
  )
}

function Placeholder({
  title,
  detail,
  onSync,
  syncing,
}: {
  title: string
  detail: string
  onSync?: () => void
  syncing?: boolean
}) {
  return (
    <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-muted-fg">
        <Icon.database size={22} />
      </div>
      <p className="text-[14px] font-medium text-fg">{title}</p>
      <p className="max-w-[440px] text-[12px] leading-relaxed text-muted-fg">{detail}</p>
      {onSync ? (
        <Button disabled={syncing} onClick={onSync}>
          <Icon.refresh size={14} />
          {syncing ? "同步中…" : "立即同步"}
        </Button>
      ) : null}
    </div>
  )
}

function DetailDialog({
  item,
  onClose,
  onCopy,
}: {
  item: LtxDetail
  onClose: () => void
  onCopy: (text: string) => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="fade-in absolute inset-0 bg-[rgb(9_14_26/0.62)] backdrop-blur-[3px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${item.code} 详情`}
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose()
        }}
        className="rise-in relative flex max-h-[92vh] w-full max-w-[680px] flex-col overflow-hidden rounded-t-xl border border-line bg-card shadow-[var(--shadow-lg)] sm:rounded-xl"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="min-w-0 truncate font-mono text-[14px] font-semibold text-fg">{item.code}</h2>
          <Button variant="ghost" onClick={onClose}>
            <Icon.close size={14} />
            关闭
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="w-[168px] shrink-0 self-start overflow-hidden rounded-md border border-line bg-elevated">
              {item.cover ? (
                <img
                  src={`/api/ltx/cover?url=${encodeURIComponent(item.cover)}`}
                  alt={`${item.code} 封面`}
                  className="block h-auto w-full object-contain"
                />
              ) : (
                <div className="flex aspect-[3/2] items-center justify-center text-muted-fg">
                  <Icon.image size={20} />
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <p className="text-[13px] leading-relaxed font-medium text-fg">{item.titleZh || item.title}</p>
              {item.titleZh && item.title !== item.titleZh ? (
                <p className="text-[12px] leading-relaxed text-muted-fg">{item.title}</p>
              ) : null}
              <dl className="grid grid-cols-[76px_1fr] gap-x-2 gap-y-1 text-[12px]">
                <Row label="发行日期" value={item.date || "—"} />
                <Row label="厂商" value={item.maker || "—"} />
                <Row label="导演" value={item.director || "—"} />
                <Row label="演员" value={item.actors.length ? item.actors.join("、") : "—"} />
                <Row label="分类" value={item.genres.length ? item.genres.join("、") : "—"} />
                <Row
                  label="评分"
                  value={item.score ? `${item.score.toFixed(1)}（${item.votes} 人）` : "—"}
                />
              </dl>
            </div>
          </div>

          <Card title={`下载链接（${item.links.length}）`} className="mt-4">
            {item.links.length === 0 ? (
              <p className="py-2 text-[12px] text-muted-fg">这条记录还没有可用链接。</p>
            ) : (
              item.links.map((link, index) => (
                <div key={index} className="flex flex-col gap-1 border-b border-line py-2 last:border-0">
                  <div className="flex flex-wrap items-center gap-2 text-[12px]">
                    <span className="rounded-full bg-elevated px-2 text-[11px] text-muted-fg">
                      {link.kind === "ed2k" ? "ed2k" : link.kind === "magnet" ? "磁力" : link.kind}
                    </span>
                    {link.sizeText !== "-" ? <span className="text-muted-fg">{link.sizeText}</span> : null}
                    <span className="min-w-0 flex-1 truncate text-fg">{link.name || link.url}</span>
                    {link.kind !== "pending" ? (
                      <Button variant="ghost" onClick={() => onCopy(link.url)}>
                        复制
                      </Button>
                    ) : null}
                  </div>
                  <p className="font-mono text-[11px] break-all text-muted-fg">{link.url}</p>
                </div>
              ))
            )}
          </Card>

          {item.subtitleUrl ? (
            <Card title="字幕" className="mt-3">
              <div className="flex flex-col gap-1 py-2">
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="rounded-full bg-elevated px-2 text-[11px] text-muted-fg">srt</span>
                  <span className="min-w-0 flex-1 truncate text-fg">{fileNameOf(item.subtitleUrl)}</span>
                  <Button variant="ghost" onClick={() => onCopy(item.subtitleUrl)}>
                    复制
                  </Button>
                </div>
                <p className="font-mono text-[11px] break-all text-muted-fg">{item.subtitleUrl}</p>
              </div>
            </Card>
          ) : null}
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line bg-panel px-4 py-3">
          {item.url ? (
            <Button onClick={() => onCopy(item.url)}>
              <Icon.link size={14} />
              复制详情页链接
            </Button>
          ) : null}
        </footer>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-muted-fg">{label}</dt>
      <dd className="min-w-0 break-words text-fg">{value}</dd>
    </>
  )
}

/** 从字幕 URL 里取出可读文件名，取不到就退回整条链接。 */
function fileNameOf(url: string): string {
  const last = url.split("/").pop() || ""
  try {
    return decodeURIComponent(last) || url
  } catch {
    return last || url
  }
}
