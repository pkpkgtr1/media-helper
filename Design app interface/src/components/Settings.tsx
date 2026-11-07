import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { api, DEFAULT_FLARESOLVERR_URL, type AppSettings } from "../api"
import { useApp } from "../state"
import {
  Button,
  Field,
  Segmented,
  Select,
  TextInput,
  Toggle,
} from "./ui"
import { Icon } from "./icons"
import { UpdateNfoDialog } from "./UpdateNfoDialog"

type Group = "常规" | "图片与封面" | "NFO 与标签" | "下载" | "高级"
const GROUPS: Group[] = ["常规", "图片与封面", "NFO 与标签", "下载", "高级"]
type SettingsProps = {
  draft: AppSettings
  patch: (value: Partial<AppSettings>) => void
}
const normalizeName = (name: string) =>
  name.normalize("NFKC").replace(/\s+/gu, " ").trim()
const categoryKey = (name: string) => normalizeName(name).toLowerCase()
const cloneSettings = (settings: AppSettings): AppSettings => ({
  ...settings,
  categories: settings.categories.map((category) => ({ ...category })),
})
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : String(error)
const numberInRange = (value: unknown, min: number, max: number, fallback: number): number => {
  const number = typeof value === "number" && Number.isFinite(value) ? Math.round(value) : NaN
  return Number.isInteger(number) && number >= min && number <= max ? number : fallback
}

function validateSettings(value: unknown): AppSettings {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("设置文件必须是 JSON 对象。")
  const data = value as Record<string, unknown>
  if (typeof data.outputRoot !== "string" || !data.outputRoot.trim())
    throw new Error("请填写默认输出目录。")
  for (const key of [
    "openAfter",
    "redownloadCover",
    "writeTags",
    "writeGenres",
  ]) {
    if (typeof data[key] !== "boolean")
      throw new Error(`设置项 ${key} 必须为布尔值。`)
  }
  const enums = {
    coverSite: ["dmm", "animap", "auto"],
    existingVideo: ["skip", "redownload"],
    unseenDefault: ["keep", "exclude"],
  }
  for (const [key, options] of Object.entries(enums)) {
    if (typeof data[key] !== "string" || !options.includes(data[key] as string))
      throw new Error(`设置项 ${key} 的取值无效。`)
  }
  for (const [key, min, max] of [
    ["retries", 0, 20],
    ["downloadInterval", 0, 600000],
    ["requestTimeout", 1, 3600],
  ] as const) {
    const number = data[key]
    if (
      typeof number !== "number" ||
      !Number.isFinite(number) ||
      number < min ||
      number > max ||
      !Number.isInteger(number)
    )
      throw new Error(
        `${key} 应为 ${min}–${max} 之间的整数。`,
      )
  }
  if (!Array.isArray(data.categories))
    throw new Error("设置文件缺少分类规则列表。")
  const flaresolverrEnabled = data.flaresolverrEnabled === true
  const flaresolverrUrl =
    typeof data.flaresolverrUrl === "string" && data.flaresolverrUrl.trim()
      ? data.flaresolverrUrl.trim()
      : DEFAULT_FLARESOLVERR_URL
  const seen = new Set<string>()
  const categories = data.categories.map((item: unknown) => {
    if (!item || typeof item !== "object") throw new Error("分类规则格式错误。")
    const category = item as Record<string, unknown>
    if (
      typeof category.name !== "string" ||
      typeof category.checked !== "boolean"
    )
      throw new Error("分类规则需要名称和勾选状态。")
    const name = normalizeName(category.name)
    if (!name || name.length > 200 || seen.has(categoryKey(name)))
      throw new Error(`分类名称为空、重复或超过 200 个字符：${name || "（空）"}`)
    seen.add(categoryKey(name))
    return {
      name,
      checked: category.checked,
      group: typeof category.group === "string" ? category.group : undefined,
      aliases: Array.isArray(category.aliases) ? category.aliases.filter((v): v is string => typeof v === "string") : [],
    }
  })
  return {
    outputRoot: data.outputRoot.trim(),
    openAfter: data.openAfter as boolean,
    posterMode: "download",
    coverSite: data.coverSite as AppSettings["coverSite"],
    redownloadCover: data.redownloadCover as boolean,
    existingVideo: data.existingVideo as AppSettings["existingVideo"],
    retries: data.retries as number,
    downloadInterval: data.downloadInterval as number,
    requestTimeout: data.requestTimeout as number,
    writeTags: true,
    writeGenres: true,
    unseenDefault: "exclude",
    proxyEnabled: data.proxyEnabled === true,
    proxyUrl: typeof data.proxyUrl === "string" ? data.proxyUrl.trim() : "",
    flaresolverrEnabled,
    flaresolverrUrl,
    hgSaveRoot: typeof data.hgSaveRoot === "string" ? data.hgSaveRoot : "",
    hgIntervalValue: numberInRange(data.hgIntervalValue, 1, 9999, 6),
    hgIntervalUnit: data.hgIntervalUnit === "minute" || data.hgIntervalUnit === "day" ? data.hgIntervalUnit : "hour",
    hgConcurrent: numberInRange(data.hgConcurrent, 1, 8, 4),
    hgRetries: numberInRange(data.hgRetries, 0, 5, 2),
    hgRetryInterval: numberInRange(data.hgRetryInterval, 0, 3600, 30),
    categories,
  }
}

function SettingRow({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col items-stretch justify-between gap-3 border-b border-border py-3.5 last:border-0 sm:flex-row sm:items-center sm:gap-6">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-foreground">{title}</div>
        {hint && (
          <div className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            {hint}
          </div>
        )}
      </div>
      <div className="max-w-full shrink-0 [&>div]:max-w-full [&>div]:flex-wrap [&_input]:max-w-full">{children}</div>
    </div>
  )
}

function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-[8px] border border-border bg-card px-3 sm:px-5 py-1">
      {title && (
        <h3 className="border-b border-border py-3 text-[13px] font-semibold text-foreground">
          {title}
        </h3>
      )}
      {children}
    </section>
  )
}

export function Settings() {
  const { settings, defaults, saveSettings, notify } = useApp()
  const [group, setGroup] = useState<Group>("NFO 与标签")
  const [draft, setDraft] = useState(() => cloneSettings(settings))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const savedKey = JSON.stringify(settings)
  const previousSavedKey = useRef(savedKey)
  const dirty = JSON.stringify(draft) !== savedKey

  useEffect(() => {
    const previousKey = previousSavedKey.current
    previousSavedKey.current = savedKey
    setDraft((current) =>
      JSON.stringify(current) === previousKey
        ? cloneSettings(JSON.parse(savedKey) as AppSettings)
        : current,
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
      const validated = validateSettings(draft)
      const saved = await saveSettings(validated)
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
        className="flex w-full shrink-0 overflow-x-auto border-b border-border bg-panel py-2 md:block md:w-[176px] md:border-b-0 md:border-r md:py-3"
      >
        {GROUPS.map((g) => (
          <button
            key={g}
            onClick={() => setGroup(g)}
            className={`flex w-auto shrink-0 items-center whitespace-nowrap px-4 py-2 text-left text-[13px] transition-colors md:w-full ${
              group === g
                ? "border-l-2 border-primary bg-accent font-medium text-accent-foreground"
                : "border-l-2 border-transparent text-muted-foreground hover:bg-secondary hover:text-foreground"
            }`}
          >
            {g}
          </button>
        ))}
      </nav>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <fieldset
          disabled={saving}
          className="min-h-0 min-w-0 flex-1 overflow-y-auto border-0 px-3 sm:px-6 py-5"
        >
          <div className="mx-auto max-w-[820px] space-y-4">
            {group === "常规" && (
              <GeneralSettings draft={draft} patch={patch} />
            )}
            {group === "图片与封面" && (
              <ImageSettings draft={draft} patch={patch} />
            )}
            {group === "NFO 与标签" && (
              <NfoSettings draft={draft} patch={patch} />
            )}
            {group === "下载" && (
              <DownloadSettings draft={draft} patch={patch} />
            )}
            {group === "高级" && (
              <AdvancedSettings draft={draft} patch={patch} />
            )}
          </div>
        </fieldset>
        {error && (
          <div
            role="alert"
            className="border-t border-border bg-[color:var(--status-failed-bg)] px-3 sm:px-6 py-2 text-[12px] text-[color:var(--status-failed)]"
          >
            {error}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2 border-t border-border bg-card px-3 sm:px-6 py-3">
          {dirty ? (
            <span className="flex items-center gap-1.5 text-[12px] text-[color:var(--status-pending)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--status-pending)]" />
              有未保存的更改
            </span>
          ) : (
            <span className="text-[12px] text-muted-foreground">
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
            <Button
              variant="primary"
              onClick={() => void save()}
              disabled={!dirty || saving}
            >
              {saving ? "保存中…" : "保存设置"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function GeneralSettings({ draft, patch }: SettingsProps) {
  const { pickDirectory, notify } = useApp()
  async function browse() {
    try {
      const path = await pickDirectory()
      if (path) patch({ outputRoot: path })
    } catch (error) {
      notify(errorText(error))
    }
  }
  return (
    <Card title="常规">
      <SettingRow title="默认输出目录" hint="后续任务使用的默认媒体库位置。">
        <div className="flex items-center gap-2">
          <TextInput
            value={draft.outputRoot}
            onChange={(outputRoot) => patch({ outputRoot })}
            mono
            className="w-[260px]"
          />
          <Button size="sm" onClick={() => void browse()}>
            <Icon.folder />
            选择
          </Button>
        </div>
      </SettingRow>
      <SettingRow title="启动月份" hint="从媒体库页面选择需要处理的月份。">
        <span className="text-[12px] text-muted-foreground">上一个月</span>
      </SettingRow>
      <SettingRow title="完成后打开输出目录">
        <Toggle
          checked={draft.openAfter}
          onChange={(openAfter) => patch({ openAfter })}
        />
      </SettingRow>
    </Card>
  )
}

function ImageSettings({ draft, patch }: SettingsProps) {
  const sites = { dmm: "DMM", animap: "ani-map", auto: "自动选择" }
  return (
    <Card title="图片与封面">
      <SettingRow title="海报模式" hint="网页截图需要浏览器渲染，已下线；封面与背景图统一从站点下载。">
        <span className="text-[12px] text-muted-foreground">下载图片</span>
      </SettingRow>
      <SettingRow title="封面来源">
        <Select
          value={sites[draft.coverSite]}
          options={Object.values(sites)}
          onChange={(value) =>
            patch({
              coverSite:
                value === "DMM"
                  ? "dmm"
                  : value === "ani-map"
                    ? "animap"
                    : "auto",
            })
          }
          className="w-[140px]"
        />
      </SettingRow>
      <SettingRow
        title="已有图片处理"
        hint={
          draft.redownloadCover
            ? "将替换 poster.jpg，原有图片会被覆盖。"
            : "已存在的封面与背景图将保留，不会重新下载。"
        }
      >
        <Segmented
          value={draft.redownloadCover ? "redownload" : "skip"}
          onChange={(value) =>
            patch({ redownloadCover: value === "redownload" })
          }
          options={[
            { value: "skip", label: "跳过" },
            { value: "redownload", label: "重新下载" },
          ]}
        />
      </SettingRow>
    </Card>
  )
}

function DownloadSettings({ draft, patch }: SettingsProps) {
  const [advanced, setAdvanced] = useState(false)
  return (
    <>
      <Card title="下载">
        <SettingRow title="已有视频处理">
          <Segmented
            value={draft.existingVideo}
            onChange={(value) =>
              patch({ existingVideo: value as AppSettings["existingVideo"] })
            }
            options={[
              { value: "skip", label: "跳过" },
              { value: "redownload", label: "重新下载" },
            ]}
          />
        </SettingRow>
        <SettingRow title="失败重试次数" hint="0–20 次；0 表示不重试。">
          <TextInput
            value={Number.isNaN(draft.retries) ? "" : String(draft.retries)}
            onChange={(value) =>
              patch({ retries: value.trim() ? Number(value) : NaN })
            }
            mono
            className="w-[80px]"
          />
        </SettingRow>
      </Card>
      <button
        onClick={() => setAdvanced(!advanced)}
        className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground"
      >
        <span className={`transition-transform ${advanced ? "rotate-90" : ""}`}>
          <Icon.chevron size={14} />
        </span>
        高级性能选项
      </button>
      {advanced && (
        <Card>
          <SettingRow title="下载间隔" hint="每个请求之间的等待时间（毫秒）。">
            <TextInput
              value={
                Number.isNaN(draft.downloadInterval)
                  ? ""
                  : String(draft.downloadInterval)
              }
              onChange={(value) =>
                patch({ downloadInterval: value.trim() ? Number(value) : NaN })
              }
              mono
              className="w-[100px]"
            />
          </SettingRow>
          <SettingRow title="请求超时" hint="单个请求的最长等待时间（秒）。">
            <TextInput
              value={
                Number.isNaN(draft.requestTimeout)
                  ? ""
                  : String(draft.requestTimeout)
              }
              onChange={(value) =>
                patch({ requestTimeout: value.trim() ? Number(value) : NaN })
              }
              mono
              className="w-[100px]"
            />
          </SettingRow>
        </Card>
      )}
    </>
  )
}

function AdvancedSettings({ draft, patch }: SettingsProps) {
  const { exportLogs } = useApp()
  const input = useRef<HTMLInputElement>(null)
  const [env, setEnv] = useState<{
    name: string
    status: "ready" | "missing"
    detail: string
  }[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const [proxyTesting, setProxyTesting] = useState(false)
  const [proxyResult, setProxyResult] = useState<{
    ok: boolean
    proxy: string
    detail?: string
    error?: string
  } | null>(null)
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])
  async function checkEnvironment() {
    setLoading(true)
    setError("")
    try {
      const result = await api<{ items: NonNullable<typeof env> }>(
        "/environment",
      )
      if (alive.current) setEnv(result.items)
    } catch (error) {
      if (alive.current) setError(errorText(error))
    } finally {
      if (alive.current) setLoading(false)
    }
  }
  async function importFile(file: File | undefined) {
    if (!file) return
    setError("")
    setMessage("")
    try {
      if (file.size > 2 * 1024 * 1024)
        throw new Error("设置文件超过 2 MB，无法导入。")
      const parsed = JSON.parse(await file.text()) as unknown
      const value =
        parsed && typeof parsed === "object" && "settings" in parsed
          ? (parsed as { settings: unknown }).settings
          : parsed
      const imported = validateSettings(value)
      if (alive.current) {
        patch(imported)
        setMessage("设置已导入草稿，点击“保存设置”后生效。")
      }
    } catch (error) {
      if (alive.current) setError(errorText(error))
    }
  }
  function exportSettings() {
    setError("")
    try {
      const settings = validateSettings(draft)
      const url = URL.createObjectURL(
        new Blob([JSON.stringify({ version: 1, settings }, null, 2)], {
          type: "application/json;charset=utf-8",
        }),
      )
      const link = document.createElement("a")
      link.href = url
      link.download = "hinet-settings.json"
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage("已导出当前设置草稿。")
    } catch (error) {
      setError(errorText(error))
    }
  }
  async function testProxy() {
    setProxyTesting(true)
    setProxyResult(null)
    setError("")
    try {
      const result = await api<{
        ok: boolean
        proxy: string
        detail?: string
        error?: string
      }>("/proxy/test", { proxyUrl: draft.proxyUrl.trim() })
      if (alive.current) setProxyResult(result)
    } catch (error) {
      if (alive.current)
        setProxyResult({ ok: false, proxy: "", error: errorText(error) })
    } finally {
      if (alive.current) setProxyTesting(false)
    }
  }
  return (
    <>
      <Card title="网络代理">
        <SettingRow
          title="启用代理"
          hint="爬虫、封面下载与视频下载全部经由代理；本机 API 与局域网地址始终直连。保存后对后续任务生效。"
        >
          <Toggle
            checked={draft.proxyEnabled}
            onChange={(value) => patch({ proxyEnabled: value })}
          />
        </SettingRow>
        <SettingRow
          title="代理地址"
          hint="支持 http / socks5，含认证形如 http://用户:密码@主机:端口"
        >
          <TextInput
            value={draft.proxyUrl}
            mono
            placeholder="http://192.168.11.2:7893"
            onChange={(value) => patch({ proxyUrl: value })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
        <div className="flex flex-wrap items-center gap-3 py-3">
          <Button
            size="sm"
            onClick={() => void testProxy()}
            disabled={proxyTesting || !draft.proxyUrl.trim()}
          >
            <Icon.refresh />
            {proxyTesting ? "测试中…" : "测试代理连通"}
          </Button>
          {proxyResult &&
            (proxyResult.ok ? (
              <span className="flex items-center gap-1 text-[12px] text-[color:var(--status-ready)]">
                <Icon.check size={15} />
                可用（{proxyResult.proxy}）{proxyResult.detail}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[12px] text-[color:var(--status-failed)]">
                <Icon.warn size={14} />
                {proxyResult.error}
              </span>
            ))}
        </div>
        {draft.proxyEnabled && !draft.proxyUrl.trim() && (
          <p className="pb-3 text-[12px] text-[color:var(--status-failed)]">
            已开启代理但未填写地址，保存会被拒绝。
          </p>
        )}
      </Card>
      <Card title="FlareSolverr">
        <SettingRow
          title="启用 FlareSolverr"
          hint="hanime 页面被 Cloudflare 拦截时，交由 FlareSolverr 解析后再继续；关闭则只用普通 HTTP 请求。保存后对后续任务生效。"
        >
          <Toggle
            checked={draft.flaresolverrEnabled}
            onChange={(value) => patch({ flaresolverrEnabled: value })}
          />
        </SettingRow>
        <SettingRow
          title="FlareSolverr 地址"
          hint="支持 http://主机:端口 ，也可直接填完整的 /v1 接口地址；留空则使用默认值。"
        >
          <TextInput
            value={draft.flaresolverrUrl}
            mono
            placeholder={DEFAULT_FLARESOLVERR_URL}
            onChange={(value) => patch({ flaresolverrUrl: value })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
      </Card>
      <Card title="运行环境">
        {env === null && (
          <p className="py-4 text-[12px] text-muted-foreground">
            尚未检查。点击下方按钮检测本机组件。
          </p>
        )}
        {env?.map((item) => (
          <SettingRow key={item.name} title={item.name} hint={item.detail}>
            {item.status === "ready" ? (
              <span className="flex items-center gap-1 text-[12px] text-[color:var(--status-ready)]">
                <Icon.check size={15} />
                正常
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[12px] text-[color:var(--status-pending)]">
                <Icon.warn size={14} />
                缺失
              </span>
            )}
          </SettingRow>
        ))}
        <div className="py-3">
          <Button
            size="sm"
            onClick={() => void checkEnvironment()}
            disabled={loading}
          >
            <Icon.refresh />
            {loading ? "检查中…" : "检查运行环境"}
          </Button>
        </div>
      </Card>
      <Card title="维护">
        <SettingRow title="日志与配置">
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={exportLogs}>
              导出日志
            </Button>
            <Button size="sm" onClick={() => input.current?.click()}>
              导入设置
            </Button>
            <Button size="sm" onClick={exportSettings}>
              导出设置
            </Button>
            <input
              ref={input}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(event) => {
                void importFile(event.target.files?.[0])
                event.target.value = ""
              }}
            />
          </div>
        </SettingRow>
      </Card>
      {error && (
        <p
          role="alert"
          className="text-[12px] text-[color:var(--status-failed)]"
        >
          {error}
        </p>
      )}
      {message && (
        <p
          role="status"
          className="text-[12px] text-[color:var(--status-ready)]"
        >
          {message}
        </p>
      )}
    </>
  )
}

function NfoSettings({ draft, patch }: SettingsProps) {
  const { defaults } = useApp()
  const [q, setQ] = useState("")
  const [filter, setFilter] = useState("全部")
  const [dialog, setDialog] = useState(false)
  // The server catalog is authoritative, including when importing old settings.
  const cats = useMemo(() => {
    const rules = new Map(draft.categories.map(c => [categoryKey(c.name), c.checked]))
    return defaults.categories.map(c => {
      const values = [c.name, ...(c.aliases ?? [])].map(categoryKey)
        .filter(key => rules.has(key)).map(key => rules.get(key)!)
      return { ...c, checked: values.length > 0 && values.every(Boolean) }
    })
  }, [defaults.categories, draft.categories])
  const visible = cats.filter(c => (filter === "全部" || (filter === "已勾选") === c.checked)
    && [c.name, ...(c.aliases ?? [])].some(name => categoryKey(name).includes(categoryKey(q))))
  const groups = [...new Set(visible.map(c => c.group))]
  const checkedCount = cats.filter(c => c.checked).length
  function choose(names: Set<string>, checked?: boolean) {
    patch({ writeTags: true, writeGenres: true, unseenDefault: "exclude",
      categories: cats.map(c => names.has(c.name) ? { ...c, checked: checked ?? !c.checked } : c) })
  }
  if (defaults.categories.length > 0 && defaults.categories.some(c => !c.group)) {
    return <Card title="需要重启本地服务"><p className="py-4 text-[13px] text-muted-foreground">界面已更新。请关闭当前运行的媒体下载助手服务，再双击“启动新界面.bat”，载入完整的网站标签目录。</p></Card>
  }
  return (
    <>
      <section className="rounded-[8px] border border-border bg-card">
        <div className="border-b border-border px-3 sm:px-5 py-4">
          <h3 className="text-[14px] font-semibold text-foreground">选择要保留的分类和标签</h3>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            以下是 Hanime1「内容标签」的全部选项。资源本身包含且已勾选的标签，会同时写入 NFO 的分类和标签；未勾选的不保留。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 sm:px-5 py-3">
          <TextInput value={q} onChange={setQ} placeholder="搜索标签" className="w-[190px]" />
          <Segmented value={filter} onChange={setFilter} options={[
            { value: "全部", label: `全部 ${cats.length}` },
            { value: "已勾选", label: `已勾选 ${checkedCount}` },
            { value: "未勾选", label: `未勾选 ${cats.length - checkedCount}` },
          ]} />
          <div className="ml-auto flex gap-3 text-[12px] text-primary">
            <button onClick={() => choose(new Set(visible.map(c => c.name)), true)} className="hover:underline">全选当前结果</button>
            <button onClick={() => choose(new Set(visible.map(c => c.name)), false)} className="hover:underline">取消选择当前结果</button>
          </div>
        </div>
        <div className="space-y-6 px-3 sm:px-5 py-5">
          {groups.map(group => (
            <fieldset key={group}>
              <legend className="mb-3 text-[13px] font-semibold text-foreground">{group}</legend>
              <div className="flex flex-wrap gap-2">
                {visible.filter(c => c.group === group).map(c => (
                  <label key={c.name} className={`inline-flex cursor-pointer items-center gap-2 rounded-full border px-3 py-2 text-[13px] transition-colors ${c.checked ? "border-primary bg-accent text-accent-foreground" : "border-border bg-card text-foreground hover:bg-secondary"}`}>
                    <input type="checkbox" checked={c.checked} onChange={() => choose(new Set([c.name]))} className="h-3.5 w-3.5 accent-[var(--primary)]" />
                    {c.name}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          {visible.length === 0 && <p className="py-6 text-center text-[13px] text-muted-foreground">没有匹配的标签</p>}
        </div>
        <div className="border-t border-border px-3 sm:px-5 py-3 text-[12px] text-muted-foreground">
          共 {cats.length} 个 · 已勾选 {checkedCount} 个。未勾选任何标签时，NFO 不写入分类和标签。
        </div>
      </section>
      <Card title="应用到已有资源">
        <SettingRow title="更新已有 NFO" hint="保存设置后对后续获取生效。已有文件需单独应用，可先预览并备份。">
          <Button size="sm" onClick={() => setDialog(true)}>应用到已有 NFO…</Button>
        </SettingRow>
      </Card>
      {dialog && <UpdateNfoDialog settings={{ ...draft, categories: cats }} onClose={() => setDialog(false)} />}
    </>
  )
}

export default Settings
