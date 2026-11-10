import { useEffect, useState } from "react"
import { fetchAuthStatus, setUnauthorizedHandler, type AuthStatus } from "../lib/api"
import { errorText } from "../lib/format"
import { LoginScreen } from "../features/auth/LoginScreen"
import { Icon } from "../components/ui/icons"

/**
 * 登录闸门：没有密码时先引导设置，已设置则要求登录。
 * 只有通过之后才挂载 AppProvider，后台轮询不会在未登录状态下反复撞 401。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [error, setError] = useState("")
  // 「稍后设置」：本次打开先不设密码，直接进界面。
  const [skipped, setSkipped] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const value = await fetchAuthStatus()
        if (!cancelled) setStatus(value)
      } catch (err) {
        if (!cancelled) setError(errorText(err))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // 任何请求撞到 401 都把登录页重新推到前台。
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSkipped(false)
      setStatus({ hasPassword: true, authenticated: false, updatedAt: "" })
    })
    return () => setUnauthorizedHandler(undefined)
  }, [])

  if (error) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg px-4">
        <div className="max-w-[420px] rounded-lg border border-line bg-card p-5 text-center">
          <Icon.warn size={20} className="mx-auto mb-2 text-failed" />
          <p className="text-[13px] font-medium text-fg">无法连接本地服务</p>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-fg">{error}</p>
          <p className="mt-3 text-[11px] text-muted-fg">请确认启动脚本仍在运行，然后刷新页面。</p>
        </div>
      </div>
    )
  }

  if (!status) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-bg">
        <span className="text-[12px] text-muted-fg">正在检查登录状态…</span>
      </div>
    )
  }

  if (status.hasPassword && !status.authenticated) {
    return <LoginScreen status={status} onChange={setStatus} />
  }

  if (!status.hasPassword && !skipped) {
    return <LoginScreen status={status} onChange={setStatus} onSkip={() => setSkipped(true)} />
  }

  return <>{children}</>
}
