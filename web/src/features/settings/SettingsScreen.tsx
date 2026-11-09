import { useEffect, useMemo, useRef, useState } from "react"
import { useApp } from "../../state"
import { Button } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings } from "../../lib/types"
import { cloneSettings, validateSettings } from "./validate"
import { GeneralPanel } from "./GeneralPanel"
import { DownloadPanel } from "./DownloadPanel"
import { NetworkPanel } from "./NetworkPanel"
import { TagsPanel } from "./TagsPanel"
import { MaintenancePanel } from "./MaintenancePanel"
import { errorText } from "../../lib/format"

type Group = "常规" | "下载" | "网络" | "分类与标签" | "维护"

const GROUPS: { key: Group; icon: (p: { size?: number }) => React.ReactNode }[] = [
  { key: "常规", icon: Icon.settings },
  { key: "下载", icon: Icon.download },
  { key: "网络", icon: Icon.link },
  { key: "分类与标签", icon: Icon.database },
  { key: "维护", icon: Icon.warn },
]

export function SettingsScreen() {
  const { settings, defaults, saveSettings, notify } = useApp()
  const [group, setGroup] = useState<Group>("常规")
  const [draft, setDraft] = useState<AppSettings>(() => cloneSettings(settings))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const savedKey = useMemo(() => JSON.stringify(settings), [settings])
  const previousKey = useRef(savedKey)
  const dirty = useMemo(() => JSON.stringify(draft) !== savedKey, [draft, savedKey])

  useEffect(() => {
    const previous = previousKey.current
    previousKey.current = savedKey
    setDraft((current) =>
      JSON.stringify(current) === previous ? cloneSettings(JSON.parse(savedKey) as AppSettings) : current,
    )
  }, [savedKey])

  function patch(value: Partial<AppSettings>) {
    setDraft((current) => ({ ...current, ...value }))
    setError("")
  }

  async function save() {
    setError("")
    setSaving(true)
    try {
      const saved = await saveSettings(validateSettings(draft))
      setDraft(cloneSettings(saved))
      notify("设置已保存，将对后续操作生效。")
    } catch (error) {
      setError(errorText(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden md:flex-row">
      <nav
        aria-label="设置分组"
        className="flex w-full shrink-0 overflow-x-auto border-b border-line bg-panel px-2 py-1.5 md:w-[186px] md:flex-col md:border-r md:border-b-0 md:px-2 md:py-3"
      >
        {GROUPS.map((item) => {
          const active = group === item.key
          const Glyph = item.icon
          return (
            <button
              key={item.key}
              type="button"
              aria-current={active ? "true" : undefined}
              onClick={() => setGroup(item.key)}
              className={`flex shrink-0 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] whitespace-nowrap transition-colors duration-150 md:w-full ${
                active
                  ? "bg-card font-medium text-fg shadow-[var(--shadow-sm)]"
                  : "text-muted-fg hover:bg-elevated hover:text-fg"
              }`}
            >
              <Glyph size={15} />
              {item.key}
            </button>
          )
        })}
      </nav>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5">
          <div className="mx-auto max-w-[840px] space-y-4">
            {group === "常规" ? <GeneralPanel draft={draft} patch={patch} /> : null}
            {group === "下载" ? <DownloadPanel draft={draft} patch={patch} /> : null}
            {group === "网络" ? <NetworkPanel draft={draft} patch={patch} /> : null}
            {group === "分类与标签" ? <TagsPanel draft={draft} patch={patch} /> : null}
            {group === "维护" ? <MaintenancePanel draft={draft} patch={patch} /> : null}
          </div>
        </div>

        {error ? (
          <div
            role="alert"
            className="border-t border-line bg-failed-soft px-4 py-2 text-[12px] text-failed"
          >
            {error}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-card px-4 py-3">
          {dirty ? (
            <span className="flex items-center gap-1.5 text-[12px] text-pending">
              <span className="h-1.5 w-1.5 rounded-full bg-pending" />
              有未保存的更改
            </span>
          ) : (
            <span className="text-[12px] text-muted-fg">
              设置将在保存后对后续操作生效，不会更改正在运行的任务。
            </span>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              disabled={saving}
              onClick={() => {
                setDraft(cloneSettings(defaults))
                setError("")
              }}
            >
              恢复默认设置
            </Button>
            <Button
              disabled={!dirty || saving}
              onClick={() => {
                setDraft(cloneSettings(settings))
                setError("")
              }}
            >
              取消
            </Button>
            <Button variant="accent" onClick={() => void save()} disabled={!dirty || saving}>
              {saving ? "保存中…" : "保存设置"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
