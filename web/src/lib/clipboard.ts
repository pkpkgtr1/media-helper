/**
 * 复制文本到剪贴板。
 *
 * navigator.clipboard 只在「安全上下文」可用：HTTPS 或 localhost。本程序常见用法是
 * 通过 http://192.168.x.x:8766 从局域网访问，此时 navigator.clipboard 直接是
 * undefined，调用必然抛错，于是所有「复制」按钮都会提示失败。
 *
 * 所以这里按能力降级：
 *   1. navigator.clipboard.writeText（安全上下文，首选）
 *   2. 隐藏 textarea + document.execCommand("copy")（http 下仍可用）
 *   3. 抛错，由调用方提示用户手动选择文本
 */
export async function copyText(text: string): Promise<void> {
  if (!text) throw new Error("没有可复制的内容")

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // 可能是用户拒绝授权或页面失焦，继续走降级方案。
    }
  }

  if (execCommandCopy(text)) return
  throw new Error("当前浏览器不允许自动复制")
}

/** 老的 execCommand 通道：在 http 页面里是唯一可行的自动复制方式。 */
function execCommandCopy(text: string): boolean {
  const area = document.createElement("textarea")
  area.value = text
  // 必须留在文档里且可聚焦，否则 iOS/部分浏览器不生效；用离屏定位避免页面跳动。
  area.setAttribute("readonly", "")
  area.style.position = "fixed"
  area.style.top = "0"
  area.style.left = "-9999px"
  area.style.opacity = "0"
  document.body.appendChild(area)

  const active = document.activeElement as HTMLElement | null
  let ok = false
  try {
    area.select()
    area.setSelectionRange(0, text.length)
    ok = document.execCommand("copy")
  } catch {
    ok = false
  } finally {
    document.body.removeChild(area)
    active?.focus?.()
  }
  return ok
}
