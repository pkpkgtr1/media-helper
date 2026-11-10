import { useEffect, useState } from "react"
import { APP_NAME, APP_VERSION, changePassword, login, setupPassword, type AuthStatus } from "../../lib/api"
import { errorText } from "../../lib/format"
import { Button, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"

type Mode = "setup" | "login" | "change"

/**
 * 登录页：没有密码时引导首次设置，之后是普通登录。
 * 密码强度只做长度与一致性校验，规则跟后端保持一致（至少 6 位）。
 */
export function LoginScreen({
  status,
  onChange,
  onSkip,
}: {
  status: AuthStatus
  onChange: (next: AuthStatus) => void
  onSkip?: () => void
}) {
  const [mode, setMode] = useState<Mode>(status.hasPassword ? "login" : "setup")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [current, setCurrent] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setMode(status.hasPassword ? "login" : "setup")
  }, [status.hasPassword])

  const setup = mode === "setup"
  const change = mode === "change"

  async function submit() {
    setError("")
    if (!password) return setError("请输入密码")
    if (password.length < 6) return setError("密码至少 6 位")
    if ((setup || change) && password !== confirm) return setError("两次输入的密码不一致")
    if (change && !current) return setError("请输入当前密码")
    setBusy(true)
    try {
      if (setup) await setupPassword(password)
      else if (change) await changePassword(current, password)
      else await login(password)
      setPassword("")
      setConfirm("")
      setCurrent("")
      onChange({ hasPassword: true, authenticated: true, updatedAt: status.updatedAt })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const title = setup ? "设置访问密码" : change ? "修改访问密码" : "登录"
  const hint = setup
    ? "首次使用，请为这个媒体下载助手设置访问密码。密码只保存在本机的 config/auth.json。"
    : change
      ? "修改后其他已登录的设备需要重新登录。"
      : "请输入访问密码。忘记密码时可以删除 config/auth.json 后重启服务重新设置。"

  return (
    <div className="flex h-full w-full items-center justify-center overflow-y-auto bg-bg px-4 py-10">
      <div className="w-full max-w-[380px]">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-fg">
            <Icon.film size={18} />
          </span>
          <div>
            <div className="text-[15px] font-semibold tracking-tight text-fg">{APP_NAME}</div>
            <div className="font-mono text-[11px] text-muted-fg">{APP_VERSION}</div>
          </div>
        </div>

        <form
          className="rounded-lg border border-line bg-card p-5 shadow-[var(--shadow-md)]"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <div className="mb-4 flex items-center gap-2">
            <Icon.lock size={16} className="text-muted-fg" />
            <h1 className="text-[14px] font-semibold text-fg">{title}</h1>
          </div>
          <p className="mb-4 text-[12px] leading-relaxed text-muted-fg">{hint}</p>

          {change ? (
            <label className="mb-3 flex flex-col gap-1">
              <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">当前密码</span>
              <TextInput
                type="password"
                value={current}
                onChange={setCurrent}
                ariaLabel="当前密码"
                placeholder="当前密码"
              />
            </label>
          ) : null}

          <label className="mb-3 flex flex-col gap-1">
            <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">
              {change ? "新密码" : "密码"}
            </span>
            <TextInput
              type="password"
              value={password}
              onChange={setPassword}
              ariaLabel={change ? "新密码" : "密码"}
              placeholder={setup ? "至少 6 位" : "密码"}
              invalid={Boolean(error)}
            />
          </label>

          {setup || change ? (
            <label className="mb-3 flex flex-col gap-1">
              <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">确认密码</span>
              <TextInput
                type="password"
                value={confirm}
                onChange={setConfirm}
                onEnter={() => void submit()}
                ariaLabel="确认密码"
                placeholder="再输入一次"
                invalid={Boolean(error)}
              />
            </label>
          ) : null}

          {error ? (
            <p role="alert" className="mb-3 text-[12px] text-failed">
              {error}
            </p>
          ) : null}

          <Button type="submit" variant="accent" full disabled={busy}>
            {busy ? "请稍候…" : setup ? "设置并进入" : change ? "保存新密码" : "登录"}
          </Button>

          {change ? (
            <button
              type="button"
              onClick={() => {
                setMode("login")
                setError("")
                setPassword("")
                setConfirm("")
                setCurrent("")
              }}
              className="mt-3 w-full cursor-pointer text-center text-[12px] text-muted-fg hover:text-fg"
            >
              返回登录
            </button>
          ) : null}

          {setup && onSkip ? (
            <button
              type="button"
              onClick={onSkip}
              className="mt-3 w-full cursor-pointer text-center text-[12px] text-muted-fg hover:text-fg"
            >
              稍后设置，先进入
            </button>
          ) : null}
        </form>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-muted-fg">
          只在本机与已放行的局域网设备上可见 · 密码不会离开这台机器
        </p>
      </div>
    </div>
  )
}
