import type { AppSettings, LibraryResponse, Snapshot } from "./types"

export const DEFAULT_FLARESOLVERR_URL = "http://192.168.11.253:8191/v1"

export const APP_NAME = "媒体下载助手"
export const APP_VERSION = "V2.0"

/** 统一的后端调用入口：非 2xx 时抛出服务端 error 文本。 */
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

export type { LibraryResponse, Snapshot }
export type BootstrapPayload = { settings: AppSettings; defaults: AppSettings; error?: string }
