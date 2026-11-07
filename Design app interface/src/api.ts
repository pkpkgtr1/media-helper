import type { Category, DownloadTask, MediaEntry } from "./data"

export const DEFAULT_FLARESOLVERR_URL = "http://192.168.11.253:8191/v1"

export interface AppSettings {
  outputRoot: string
  openAfter: boolean
  /** 网页截图已下线，后端会统一归一为 download。 */
  posterMode: "download" | "screenshot" | "both"
  coverSite: "dmm" | "animap" | "auto"
  redownloadCover: boolean
  existingVideo: "skip" | "redownload"
  retries: number
  downloadInterval: number
  requestTimeout: number
  writeTags: boolean
  writeGenres: boolean
  unseenDefault: "keep" | "exclude"
  proxyEnabled: boolean
  proxyUrl: string
  flaresolverrEnabled: boolean
  flaresolverrUrl: string
  hgSaveRoot: string
  hgIntervalValue: number
  hgIntervalUnit: "minute" | "hour" | "day"
  hgConcurrent: number
  hgRetries: number
  hgRetryInterval: number
  categories: Category[]
}
export interface LogLine { id: number; t: string; level: "info" | "warn" | "error"; msg: string; taskId?: string }
export interface Snapshot { tasks: DownloadTask[]; logs: LogLine[]; revision: number }
export interface LibraryResponse { entries: MediaEntry[]; monthDir: string; warnings: string[]; categories: string[] }
export async function api<T = unknown>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json().catch(() => null)
  if (!response.ok) throw new Error(value?.error || `请求失败（${response.status}）`)
  if (value === null) throw new Error("本地服务响应异常，请通过启动脚本打开程序")
  return value as T
}
