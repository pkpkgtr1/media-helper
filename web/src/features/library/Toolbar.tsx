import { useApp } from "../../state"
import { Button, Field, Select, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { pad2 } from "../../lib/format"

const thisYear = new Date().getFullYear()
const YEARS = Array.from({ length: thisYear - 1999 }, (_, i) => String(thisYear - i))
const MONTHS = Array.from({ length: 12 }, (_, i) => `${pad2(i + 1)} 月`)

/** 顶部工具条：月份选择、输出目录、刷新。 */
export function Toolbar({ onPickDirectory }: { onPickDirectory: () => void }) {
  const { year, month, monthDir, setPeriod, openPath, refresh, loading, settings } = useApp()

  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-line bg-card px-4 py-3">
      <Field label="年份">
        <Select
          value={String(year)}
          options={YEARS}
          onChange={(v) => setPeriod(Number(v), month)}
          className="w-[92px]"
          ariaLabel="选择年份"
        />
      </Field>
      <Field label="月份">
        <Select
          value={`${pad2(month)} 月`}
          options={MONTHS}
          onChange={(v) => setPeriod(year, Number.parseInt(v, 10))}
          className="w-[92px]"
          ariaLabel="选择月份"
        />
      </Field>
      <Field label="输出目录">
        <div
          title={monthDir || settings.outputRoot}
          className="flex h-8 w-[min(280px,calc(100vw-7rem))] items-center rounded-md border border-line-strong bg-panel px-2.5 font-mono text-[12px] text-muted-fg"
        >
          <span className="truncate">{monthDir || settings.outputRoot || "尚未选择目录"}</span>
        </div>
      </Field>
      <Button onClick={onPickDirectory}>
        <Icon.folder size={15} />
        选择目录
      </Button>
      <Button disabled={!monthDir} onClick={() => void openPath(monthDir)}>
        <Icon.open size={15} />
        打开目录
      </Button>
      <div className="ml-auto">
        <Button disabled={loading} onClick={() => void refresh()}>
          <Icon.refresh size={15} />
          {loading ? "刷新中…" : "刷新"}
        </Button>
      </div>
    </div>
  )
}

/** 过滤 + 搜索行。 */
export function FilterBar({
  filter,
  onFilter,
  query,
  onQuery,
  counts,
}: {
  filter: string
  onFilter: (next: string) => void
  query: string
  onQuery: (next: string) => void
  counts: Record<string, number>
}) {
  const filters = ["全部", "待下载", "下载中", "已完成", "失败", "缺少图片", "缺少 NFO"]
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-card px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-1" role="group" aria-label="状态筛选">
        {filters.map((name) => {
          const active = filter === name
          return (
            <button
              key={name}
              type="button"
              aria-pressed={active}
              onClick={() => onFilter(name)}
              className={`cursor-pointer rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors duration-150 ${
                active
                  ? "bg-accent text-accent-fg"
                  : "text-muted-fg hover:bg-elevated hover:text-fg"
              }`}
            >
              {name}
              <span className={`ml-1 font-mono text-[11px] ${active ? "text-accent-fg/70" : "text-muted-fg/70"}`}>
                {counts[name] ?? 0}
              </span>
            </button>
          )
        })}
      </div>
      <div className="relative ml-auto w-[240px] max-w-full">
        <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-fg">
          <Icon.search size={14} />
        </span>
        <TextInput
          value={query}
          onChange={onQuery}
          placeholder="搜索标题或编号"
          ariaLabel="搜索媒体库"
          className="pl-8"
        />
      </div>
    </div>
  )
}
