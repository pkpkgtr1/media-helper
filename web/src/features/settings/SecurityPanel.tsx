import { useEffect, useState } from "react"
import { changePassword, fetchAuthStatus, logout, setupPassword, type AuthStatus } from "../../lib/api"
import { errorText } from "../../lib/format"
import { useApp } from "../../state"
import { Button, Card, SettingRow, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"

/** 设置 · 安全：改密码、看登录状态、退出登录。 */
export function SecurityPanel() {
  const { notify } = useApp()
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [current, setCurrent] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const value = await fetchAuthStatus()
        if (!cancelled) setStatus(value)
      } catch {
        /* 未登录时由网关接管，这里不重复报错 */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function save() {
    setError("")
    if (password.length < 6) return setError("新密码至少 6 位")
    if (password !== confirm) return setError("两次输入的新密码不一致")
    if (enabled && !current) return setError("请输入当前密码")
    setBusy(true)
    try {
      // 还没设过密码时（首次使用点了「稍后设置」）走设置接口，不需要当前密码。
      if (enabled) await changePassword(current, password)
      else await setupPassword(password)
      setCurrent("")
      setPassword("")
      setConfirm("")
      setStatus(await fetchAuthStatus())
      notify(enabled ? "密码已更新，其他设备需要重新登录。" : "访问密码已设置，下次打开需要登录。")
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function signOut() {
    try {
      await logout()
      window.location.reload()
    } catch (err) {
      notify(errorText(err))
    }
  }

  const enabled = status?.hasPassword ?? false

  return (
    <>
      <Card
        title="访问密码"
        description="密码保存在 config/auth.json，与本机的设置文件分开存放。"
      >
        <SettingRow title="登录保护" hint={enabled ? "已启用：打开界面需要输入密码。" : "未设置：任何人都能直接打开界面。"}>
          <span className={`flex items-center gap-1.5 text-[12px] ${enabled ? "text-ready" : "text-pending"}`}>
            {enabled ? <Icon.check size={15} /> : <Icon.warn size={14} />}
            {enabled ? "已启用" : "未设置"}
          </span>
        </SettingRow>
        <SettingRow title="上次修改" hint="修改后所有已登录设备都需要重新登录。">
          <span className="text-[12px] text-muted-fg">{status?.updatedAt || "—"}</span>
        </SettingRow>
        <SettingRow title="退出登录" hint="清除当前浏览器的登录状态。">
          <Button size="sm" onClick={() => void signOut()} disabled={!enabled}>
            <Icon.logout size={14} />
            退出登录
          </Button>
        </SettingRow>
      </Card>

      <Card
        title={enabled ? "修改密码" : "设置密码"}
        description={enabled ? "需要先输入当前密码。" : "设置后打开界面就需要登录。"}
      >
        <div className="flex flex-col gap-3 py-3 sm:max-w-[360px]">
          {enabled ? (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">当前密码</span>
              <TextInput type="password" value={current} onChange={setCurrent} ariaLabel="当前密码" />
            </label>
          ) : null}
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">
              {enabled ? "新密码" : "密码"}
            </span>
            <TextInput
              type="password"
              value={password}
              onChange={setPassword}
              ariaLabel="新密码"
              placeholder="至少 6 位"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">
              {enabled ? "确认新密码" : "确认密码"}
            </span>
            <TextInput type="password" value={confirm} onChange={setConfirm} ariaLabel="确认新密码" />
          </label>
          {error ? (
            <p role="alert" className="text-[12px] text-failed">
              {error}
            </p>
          ) : null}
          <div>
            <Button size="sm" variant="accent" onClick={() => void save()} disabled={busy}>
              {busy ? "保存中…" : enabled ? "修改密码" : "设置密码"}
            </Button>
          </div>
        </div>
      </Card>

      <Card title="会话" description="登录状态保存在内存中，服务重启后需要重新登录。">
        <SettingRow title="会话有效期" hint="连续 30 天未使用后自动失效；使用中会自动续期。">
          <span className="text-[12px] text-muted-fg">30 天</span>
        </SettingRow>
        <SettingRow title="忘记密码" hint="删除 config/auth.json 后重启服务，即可重新设置。">
          <span className="font-mono text-[11px] text-muted-fg">config/auth.json</span>
        </SettingRow>
      </Card>
    </>
  )
}
