import { Button, Segmented, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { DramaSearchItem, SourceRef } from "../../lib/types"
import { Cover, SourceBadge, coverSrc, itemKey } from "./shared"

/** 搜索页：关键词 + 源过滤 + 结果卡片。 */
export function SearchTab({
  keyword,
  onKeyword,
  onSearch,
  searching,
  results,
  sources,
  sourceFilter,
  onSourceFilter,
  subscribedKeys,
  onDetail,
  onSubscribe,
}: {
  keyword: string
  onKeyword: (value: string) => void
  onSearch: () => void
  searching: boolean
  results: DramaSearchItem[] | null
  sources: SourceRef[]
  sourceFilter: string
  onSourceFilter: (value: string) => void
  subscribedKeys: string[]
  onDetail: (item: DramaSearchItem) => void
  onSubscribe: (item: DramaSearchItem) => void
}) {
  const visible = (results ?? []).filter(
    (item) => sourceFilter === "all" || item.source === sourceFilter,
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-4 py-2.5">
        <div className="flex min-w-[240px] flex-1 items-center gap-2">
          <div className="relative flex-1">
            <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-fg">
              <Icon.search size={14} />
            </span>
            <TextInput
              value={keyword}
              placeholder="输入短剧关键词，回车搜索"
              ariaLabel="短剧关键词"
              onChange={onKeyword}
              onEnter={onSearch}
              className="pl-8"
            />
          </div>
          <Button variant="accent" onClick={onSearch} disabled={searching}>
            <Icon.search size={14} />
            {searching ? "搜索中…" : "搜索"}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-muted-fg">搜索源</span>
          <Segmented
            label="搜索源"
            size="sm"
            value={sourceFilter}
            options={[{ value: "all", label: "全部源" }, ...sources.map((s) => ({ value: s.key, label: s.label }))]}
            onChange={onSourceFilter}
          />
          {results !== null ? <span className="text-[11px] text-muted-fg">{visible.length} 个结果</span> : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {results === null ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-muted-fg">
              <Icon.search size={22} />
            </div>
            <p className="text-[14px] font-medium text-fg">还没有搜索</p>
            <p className="max-w-[420px] text-[12px] leading-relaxed text-muted-fg">
              输入关键词开始搜索，将同时查询 {sources.map((s) => s.label).join(" 与 ")}。
            </p>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 text-center">
            <p className="text-[14px] font-medium text-fg">没有匹配的短剧</p>
            <p className="max-w-[420px] text-[12px] text-muted-fg">
              {results.length > 0 ? "该搜索源下没有结果，切换“全部源”看看。" : "换个关键词再试一次。"}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visible.map((item, index) => {
              const subscribed = subscribedKeys.includes(itemKey(item))
              return (
                <article
                  key={itemKey(item)}
                  style={{ animationDelay: `${Math.min(index, 12) * 22}ms` }}
                  className="rise-in flex gap-3 rounded-lg border border-line bg-card p-3 shadow-[var(--shadow-sm)] transition-colors duration-150 hover:border-line-strong"
                >
                  <Cover src={coverSrc(item.cover, item.source)} title={item.title} className="h-[120px] w-[84px] shrink-0" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-[13px] font-semibold text-fg">{item.title}</h3>
                      <SourceBadge item={item} />
                      {subscribed ? (
                        <span className="inline-flex h-4 shrink-0 items-center rounded-full bg-ready-soft px-2 text-[11px] leading-none font-medium text-ready">
                          已订阅
                        </span>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-fg">
                      {item.episodeLabel ? <span>{item.episodeLabel}</span> : null}
                      {item.score ? <span>· {item.score}</span> : null}
                      {item.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="rounded bg-elevated px-1">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <p className="line-clamp-2 text-[11px] leading-relaxed text-muted-fg">
                      {item.description || "暂无简介"}
                    </p>
                    <div className="mt-auto flex gap-2 pt-1">
                      <Button size="sm" onClick={() => onDetail(item)}>
                        详情
                      </Button>
                      <Button size="sm" variant="accent" disabled={subscribed} onClick={() => onSubscribe(item)}>
                        <Icon.plus size={13} />
                        {subscribed ? "已订阅" : "添加订阅"}
                      </Button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
