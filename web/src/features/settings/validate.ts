import { DEFAULT_FLARESOLVERR_URL } from "../../lib/api"
import { clampInt } from "../../lib/format"
import type { AppSettings } from "../../lib/types"

const normalizeName = (name: string): string => name.normalize("NFKC").replace(/\s+/gu, " ").trim()
const categoryKey = (name: string): string => normalizeName(name).toLowerCase()

/** 与后端一致的本地校验：先给用户可读的错误，再交给服务端二次确认。 */
export function validateSettings(value: unknown): AppSettings {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("设置文件必须是 JSON 对象。")
  }
  const data = value as Record<string, unknown>
  if (typeof data.outputRoot !== "string" || !data.outputRoot.trim()) {
    throw new Error("请填写默认输出目录。")
  }
  for (const key of ["openAfter", "redownloadCover", "writeTags", "writeGenres"]) {
    if (typeof data[key] !== "boolean") throw new Error(`设置项 ${key} 必须为布尔值。`)
  }
  const enums: Record<string, string[]> = {
    coverSite: ["dmm", "animap", "auto"],
    existingVideo: ["skip", "redownload"],
    unseenDefault: ["keep", "exclude"],
  }
  for (const [key, options] of Object.entries(enums)) {
    if (typeof data[key] !== "string" || !options.includes(data[key] as string)) {
      throw new Error(`设置项 ${key} 的取值无效。`)
    }
  }
  for (const [key, min, max] of [
    ["retries", 0, 20],
    ["downloadInterval", 0, 600000],
    ["requestTimeout", 1, 3600],
  ] as const) {
    const number = data[key]
    if (typeof number !== "number" || !Number.isFinite(number) || number < min || number > max || !Number.isInteger(number)) {
      throw new Error(`${key} 应为 ${min}–${max} 之间的整数。`)
    }
  }
  if (!Array.isArray(data.categories)) throw new Error("设置文件缺少分类规则列表。")

  const flaresolverrEnabled = data.flaresolverrEnabled === true
  const flaresolverrUrl =
    typeof data.flaresolverrUrl === "string" && data.flaresolverrUrl.trim()
      ? data.flaresolverrUrl.trim()
      : DEFAULT_FLARESOLVERR_URL
  const flaresolverrSession =
    typeof data.flaresolverrSession === "string" ? data.flaresolverrSession.replace(/\s+/gu, "") : ""
  const userAgent = typeof data.userAgent === "string" ? data.userAgent.trim() : ""

  if (data.proxyEnabled === true && !(typeof data.proxyUrl === "string" && data.proxyUrl.trim())) {
    throw new Error("已启用代理但未填写代理地址。")
  }

  const seen = new Set<string>()
  const categories = data.categories.map((item: unknown) => {
    if (!item || typeof item !== "object") throw new Error("分类规则格式错误。")
    const category = item as Record<string, unknown>
    if (typeof category.name !== "string" || typeof category.checked !== "boolean") {
      throw new Error("分类规则需要名称和勾选状态。")
    }
    const name = normalizeName(category.name)
    if (!name || name.length > 200 || seen.has(categoryKey(name))) {
      throw new Error(`分类名称为空、重复或超过 200 个字符：${name || "（空）"}`)
    }
    seen.add(categoryKey(name))
    return {
      name,
      checked: category.checked,
      group: typeof category.group === "string" ? category.group : undefined,
      aliases: Array.isArray(category.aliases)
        ? category.aliases.filter((v): v is string => typeof v === "string")
        : [],
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
    flaresolverrSession,
    userAgent,
    hgSaveRoot: typeof data.hgSaveRoot === "string" ? data.hgSaveRoot : "",
    hgIntervalValue: clampInt(data.hgIntervalValue, 1, 9999, 6),
    hgIntervalUnit: data.hgIntervalUnit === "minute" || data.hgIntervalUnit === "day" ? data.hgIntervalUnit : "hour",
    hgConcurrent: clampInt(data.hgConcurrent, 1, 8, 4),
    hgRetries: clampInt(data.hgRetries, 0, 5, 2),
    hgRetryInterval: clampInt(data.hgRetryInterval, 0, 3600, 30),
    ltxSyncEnabled: data.ltxSyncEnabled !== false,
    ltxIntervalValue: clampInt(data.ltxIntervalValue, 1, 9999, 6),
    ltxIntervalUnit: data.ltxIntervalUnit === "minute" || data.ltxIntervalUnit === "day" ? data.ltxIntervalUnit : "hour",
    categories,
  }
}

export function cloneSettings(settings: AppSettings): AppSettings {
  return { ...settings, categories: settings.categories.map((category) => ({ ...category })) }
}

export { categoryKey, normalizeName }
