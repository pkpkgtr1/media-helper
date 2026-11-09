import { useRef, useState } from "react"
import { useApp } from "../../state"
import { api } from "../../lib/api"
import { errorText } from "../../lib/format"
import { Button, Card, SettingRow } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings, EnvironmentItem } from "../../lib/types"
import { validateSettings } from "./validate"

type Patch = (value: Partial<AppSettings>) => void

const STATUS_LABEL: Record<EnvironmentItem["status"], { text: string; cls: string; icon: React.ReactNode }> = {
  ready: { text: "正常", cls: "text-ready", icon: <Icon.check size={15} /> },
  missing: { text: "缺失", cls: "text-failed", icon: <Icon.warn size={14} /> },
  optional: { text: "未启用", cls: "text-muted-fg", icon: <Icon.warn size={14} /> },
}

/** 运行环境检查 + 设置导入导出。 */
export function MaintenancePanel({ draft, patch }: { draft: AppSettings; patch: Patch }) {
  const { exportLogs, notify } = useApp()
  const [env, setEnv] = useState<EnvironmentItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")
  const fileRef = useRef<HTMLInputElement>(null)

  async function checkEnvironment() {
    setLoading(true)
    setError("")
    try {
      const result = await api<{ items: EnvironmentItem[] }>("/environment")
      setEnv(result.items)
    } catch (error) {
      setError(errorText(error))
    } finally {
      setLoading(false)
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return
    setError("")
    setMessage("")
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error("设置文件超过 2 MB，无法导入。")
      const parsed = JSON.parse(await file.text()) as unknown
      const value =
        parsed && typeof parsed === "object" && "settings" in parsed
          ? (parsed as { settings: unknown }).settings
          : parsed
      patch(validateSettings(value))
      setMessage("设置已导入草稿，点击“保存设置”后生效。")
    } catch (error) {
      setError(errorText(error))
      notify(errorText(error))
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
      link.download = "media-helper-settings.json"
      link.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage("已导出当前设置草稿。")
    } catch (error) {
      setError(errorText(error))
    }
  }

  return (
    <>
      <Card title="运行环境" description="只报告检测结果，不会安装任何组件。">
        {env === null ? (
          <p className="py-4 text-[12px] text-muted-fg">尚未检查。点击下方按钮检测本机组件。</p>
        ) : (
          env.map((item) => {
            const status = STATUS_LABEL[item.status]
            return (
              <SettingRow key={item.name} title={item.name} hint={item.detail}>
                <span className={`flex items-center gap-1 text-[12px] ${status.cls}`}>
                  {status.icon}
                  {status.text}
                </span>
              </SettingRow>
            )
          })
        )}
        <div className="py-3">
          <Button size="sm" onClick={() => void checkEnvironment()} disabled={loading}>
            <Icon.refresh size={14} />
            {loading ? "检查中…" : "检查运行环境"}
          </Button>
        </div>
      </Card>

      <Card title="维护" description="数据目录固定为 config/，日志与配置都在其中。">
        <SettingRow title="日志与配置">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={exportLogs}>
              <Icon.logs size={14} />
              导出日志
            </Button>
            <Button size="sm" onClick={() => fileRef.current?.click()}>
              导入设置
            </Button>
            <Button size="sm" onClick={exportSettings}>
              导出设置
            </Button>
            <input
              ref={fileRef}
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

      {error ? (
        <p role="alert" className="text-[12px] text-failed">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="text-[12px] text-ready">
          {message}
        </p>
      ) : null}
    </>
  )
}
