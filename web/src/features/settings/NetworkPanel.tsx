import { useState } from "react"
import { useApp } from "../../state"
import { DEFAULT_FLARESOLVERR_URL, api } from "../../lib/api"
import { errorText } from "../../lib/format"
import { Button, Card, Segmented, SettingRow, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings } from "../../lib/types"

type Patch = (value: Partial<AppSettings>) => void

const PLACEHOLDER_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

type ProxyResult = { ok: boolean; proxy: string; detail?: string; error?: string }

export function NetworkPanel({ draft, patch }: { draft: AppSettings; patch: Patch }) {
  const { notify } = useApp()
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<ProxyResult | null>(null)

  async function testProxy() {
    setTesting(true)
    setResult(null)
    try {
      const value = await api<ProxyResult>("/proxy/test", { proxyUrl: draft.proxyUrl.trim() })
      setResult(value)
    } catch (error) {
      setResult({ ok: false, proxy: "", error: errorText(error) })
      notify(errorText(error))
    } finally {
      setTesting(false)
    }
  }

  return (
    <>
      <Card title="网络代理">
        <SettingRow
          title="启用代理"
          hint="爬虫、封面下载与视频下载全部经由代理；本机 API 与局域网地址始终直连。保存后对后续任务生效。"
        >
          <Segmented
            label="启用代理"
            value={draft.proxyEnabled ? "on" : "off"}
            options={[
              { value: "on", label: "启用" },
              { value: "off", label: "关闭" },
            ]}
            onChange={(v) => patch({ proxyEnabled: v === "on" })}
          />
        </SettingRow>
        <SettingRow title="代理地址" hint="支持 http / socks5，含认证形如 http://用户:密码@主机:端口">
          <TextInput
            value={draft.proxyUrl}
            mono
            placeholder="http://192.168.11.2:7893"
            ariaLabel="代理地址"
            onChange={(proxyUrl) => patch({ proxyUrl })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
        <div className="flex flex-wrap items-center gap-3 border-b border-line py-3 last:border-0">
          <Button size="sm" onClick={() => void testProxy()} disabled={testing || !draft.proxyUrl.trim()}>
            <Icon.refresh size={14} />
            {testing ? "测试中…" : "测试代理连通"}
          </Button>
          {result ? (
            result.ok ? (
              <span className="flex items-center gap-1 text-[12px] text-ready">
                <Icon.check size={15} />
                可用（{result.proxy}）{result.detail}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-[12px] text-failed">
                <Icon.warn size={14} />
                {result.error}
              </span>
            )
          ) : null}
        </div>
        {draft.proxyEnabled && !draft.proxyUrl.trim() ? (
          <p className="pb-3 text-[12px] text-failed">已开启代理但未填写地址，保存会被拒绝。</p>
        ) : null}
      </Card>

      <Card title="User-Agent">
        <SettingRow
          title="自定义 User-Agent"
          hint="普通请求（hanime、AI短剧、封面与视频下载）统一使用该值；留空则各模块使用内置默认值。"
        >
          <TextInput
            value={draft.userAgent}
            mono
            placeholder={PLACEHOLDER_USER_AGENT}
            ariaLabel="自定义 User-Agent"
            onChange={(userAgent) => patch({ userAgent })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
        {draft.flaresolverrEnabled ? (
          <p className="pb-3 text-[12px] leading-relaxed text-pending">
            已启用 FlareSolverr：该值暂不生效，页面请求使用 FlareSolverr 解析出的 User-Agent，以保证与其 Cookie 一致。
          </p>
        ) : draft.userAgent.trim() !== "" ? (
          <p className="pb-3 text-[12px] leading-relaxed text-muted-fg">
            该值将对保存后的新任务生效，正在运行的任务不受影响。
          </p>
        ) : null}
      </Card>

      <Card title="FlareSolverr">
        <SettingRow
          title="启用 FlareSolverr"
          hint="hanime 页面被 Cloudflare 拦截时，交由 FlareSolverr 解析后再继续；关闭则只用普通 HTTP 请求。保存后对后续任务生效。"
        >
          <Segmented
            label="启用 FlareSolverr"
            value={draft.flaresolverrEnabled ? "on" : "off"}
            options={[
              { value: "on", label: "启用" },
              { value: "off", label: "关闭" },
            ]}
            onChange={(v) => patch({ flaresolverrEnabled: v === "on" })}
          />
        </SettingRow>
        <SettingRow title="FlareSolverr 地址" hint="支持 http://主机:端口 ，也可直接填完整的 /v1 接口地址；留空则使用默认值。">
          <TextInput
            value={draft.flaresolverrUrl}
            mono
            placeholder={DEFAULT_FLARESOLVERR_URL}
            ariaLabel="FlareSolverr 地址"
            onChange={(flaresolverrUrl) => patch({ flaresolverrUrl })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
        <SettingRow
          title="会话 ID"
          hint="填写后所有 FlareSolverr 调用都复用该会话（同一浏览器上下文，解析结果可延续）；留空则每次调用各自独立。会话不存在时会自动创建。"
        >
          <TextInput
            value={draft.flaresolverrSession}
            mono
            placeholder="例如 hanime-session"
            ariaLabel="FlareSolverr 会话 ID"
            onChange={(flaresolverrSession) => patch({ flaresolverrSession })}
            className="w-full min-w-[220px] sm:w-[320px]"
          />
        </SettingRow>
        {!draft.flaresolverrEnabled && draft.flaresolverrSession.trim() !== "" ? (
          <p className="pb-3 text-[12px] leading-relaxed text-muted-fg">
            当前未启用 FlareSolverr，该会话 ID 会在启用后生效。
          </p>
        ) : null}
      </Card>
    </>
  )
}
