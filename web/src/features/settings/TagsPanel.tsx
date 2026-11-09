import { useMemo, useState } from "react"
import { useApp } from "../../state"
import { Button, Card, Segmented, SettingRow, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings, Category } from "../../lib/types"
import { categoryKey } from "./validate"
import { NfoDialog } from "./NfoDialog"

type Patch = (value: Partial<AppSettings>) => void
type Filter = "全部" | "已勾选" | "未勾选"

const FILTERS = [
  { value: "全部", label: "全部" },
  { value: "已勾选", label: "已勾选" },
  { value: "未勾选", label: "未勾选" },
] as const

/** 分类与标签：服务端目录为准，本地设置只决定勾选状态。 */
export function TagsPanel({ draft, patch }: { draft: AppSettings; patch: Patch }) {
  const { defaults } = useApp()
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<Filter>("全部")
  const [dialog, setDialog] = useState(false)

  const cats = useMemo<Category[]>(() => {
    const rules = new Map(draft.categories.map((c) => [categoryKey(c.name), c.checked]))
    if (defaults.categories.length === 0) return draft.categories
    return defaults.categories.map((category) => {
      const values = [category.name, ...(category.aliases ?? [])]
        .map(categoryKey)
        .filter((key) => rules.has(key))
        .map((key) => rules.get(key)!)
      return { ...category, checked: values.length > 0 && values.every(Boolean) }
    })
  }, [defaults.categories, draft.categories])

  const visible = useMemo(() => {
    const keyword = categoryKey(query)
    return cats.filter(
      (category) =>
        (filter === "全部" || (filter === "已勾选") === category.checked) &&
        (keyword === "" ||
          [category.name, ...(category.aliases ?? [])].some((name) => categoryKey(name).includes(keyword))),
    )
  }, [cats, filter, query])

  const groups = useMemo(() => [...new Set(visible.map((c) => c.group ?? "未分组"))], [visible])
  const checkedCount = cats.filter((c) => c.checked).length

  function choose(names: Set<string>, checked?: boolean) {
    patch({
      writeTags: true,
      writeGenres: true,
      unseenDefault: "exclude",
      categories: cats.map((c) =>
        names.has(c.name) ? { ...c, checked: checked ?? !c.checked } : c,
      ),
    })
  }

  if (defaults.categories.length > 0 && defaults.categories.some((c) => !c.group)) {
    return (
      <Card title="需要重启本地服务">
        <p className="py-4 text-[13px] text-muted-fg">
          界面已更新。请关闭当前运行的媒体下载助手服务，再重新启动，以载入完整的网站标签目录。
        </p>
      </Card>
    )
  }

  return (
    <>
      <section className="rounded-lg border border-line bg-card shadow-[var(--shadow-sm)]">
        <header className="border-b border-line px-4 py-4">
          <h2 className="text-[14px] font-semibold text-fg">选择要保留的分类和标签</h2>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-fg">
            以下是 Hanime1「内容标签」的全部选项。资源本身包含且已勾选的标签，会同时写入 NFO 的分类和标签；未勾选的不保留。
          </p>
        </header>

        <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
          <div className="relative">
            <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-fg">
              <Icon.search size={14} />
            </span>
            <TextInput
              value={query}
              onChange={setQuery}
              placeholder="搜索标签"
              ariaLabel="搜索标签"
              className="w-[190px] pl-8"
            />
          </div>
          <Segmented
            label="标签筛选"
            size="sm"
            value={filter}
            options={FILTERS.map((f) => ({
              value: f.value,
              label:
                f.value === "全部"
                  ? `全部 ${cats.length}`
                  : f.value === "已勾选"
                    ? `已勾选 ${checkedCount}`
                    : `未勾选 ${cats.length - checkedCount}`,
            }))}
            onChange={setFilter}
          />
          <div className="ml-auto flex gap-3 text-[12px]">
            <button
              type="button"
              onClick={() => choose(new Set(visible.map((c) => c.name)), true)}
              className="cursor-pointer text-accent transition-opacity hover:underline"
            >
              全选当前结果
            </button>
            <button
              type="button"
              onClick={() => choose(new Set(visible.map((c) => c.name)), false)}
              className="cursor-pointer text-muted-fg transition-colors hover:text-fg hover:underline"
            >
              取消选择当前结果
            </button>
          </div>
        </div>

        <div className="space-y-6 px-4 py-5">
          {groups.map((group) => (
            <fieldset key={group}>
              <legend className="mb-2.5 text-[13px] font-semibold text-fg">{group}</legend>
              <div className="flex flex-wrap gap-2">
                {visible
                  .filter((category) => (category.group ?? "未分组") === group)
                  .map((category) => (
                    <label
                      key={category.name}
                      className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-3 py-2 text-[13px] transition-colors duration-150 ${
                        category.checked
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-line bg-card text-fg hover:bg-elevated"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={category.checked}
                        onChange={() => choose(new Set([category.name]))}
                        className="h-3.5 w-3.5 cursor-pointer accent-[var(--accent)]"
                      />
                      {category.name}
                    </label>
                  ))}
              </div>
            </fieldset>
          ))}
          {visible.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-muted-fg">没有匹配的标签</p>
          ) : null}
        </div>

        <footer className="border-t border-line px-4 py-3 text-[12px] text-muted-fg">
          共 {cats.length} 个 · 已勾选 {checkedCount} 个。未勾选任何标签时，NFO 不写入分类和标签。
        </footer>
      </section>

      <Card title="应用到已有资源">
        <SettingRow title="更新已有 NFO" hint="保存设置后对后续获取生效。已有文件需单独应用，可先预览并备份。">
          <Button size="sm" onClick={() => setDialog(true)}>
            应用到已有 NFO…
          </Button>
        </SettingRow>
      </Card>

      {dialog ? (
        <NfoDialog settings={{ ...draft, categories: cats }} onClose={() => setDialog(false)} />
      ) : null}
    </>
  )
}
