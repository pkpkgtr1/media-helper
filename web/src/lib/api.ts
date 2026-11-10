import type { AppSettings, LibraryResponse, Snapshot } from "./types"

export const DEFAULT_FLARESOLVERR_URL = "http://192.168.11.253:8191/v1"

export const APP_NAME = "媒体下载助手"
export const APP_VERSION = "V2.3"

/** 未登录时后端返回 401；前端据此切到登录页，而不是弹一堆报错。 */
export class UnauthorizedError extends Error {
  constructor() {
    super("请先登录")
    this.name = "UnauthorizedError"
  }
}

/** 全局的未登录回调：由 AppProvider 注册，避免每个调用点各写一遍。 */
let onUnauthorized: (() => void) | undefined

export function setUnauthorizedHandler(handler: (() => void) | undefined): void {
  onUnauthorized = handler
}

/** 统一的后端调用入口：非 2xx 时抛出服务端 error 文本。 */
export async function api<T = unknown>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    // 会话靠 HttpOnly Cookie，跨站请求一律不带。
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json().catch(() => null)
  if (response.status === 401) {
    onUnauthorized?.()
    throw new UnauthorizedError()
  }
  if (!response.ok) throw new Error(value?.error || `请求失败（${response.status}）`)
  if (value === null) throw new Error("本地服务响应异常，请通过启动脚本打开程序")
  return value as T
}

/** 带查询参数的 GET：`api()` 只接路径，这里把参数拼成 query string。 */
export function apiGet<T = unknown>(path: string, params?: Record<string, string | number>): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params ?? {})) {
    const text = String(value ?? "").trim()
    if (text) query.set(key, text)
  }
  const suffix = query.toString()
  return api<T>(suffix ? `${path}?${suffix}` : path)
}

export type { LibraryResponse, Snapshot }
export type BootstrapPayload = { settings: AppSettings; defaults: AppSettings; error?: string }

export type AuthStatus = {
  /** 已经设置过登录密码。 */
  hasPassword: boolean
  /** 当前这次请求是否已登录。 */
  authenticated: boolean
  updatedAt: string
}

export function fetchAuthStatus(): Promise<AuthStatus> {
  return api<AuthStatus>("/auth/status")
}

export function login(password: string): Promise<unknown> {
  return api("/auth/login", { password })
}

export function setupPassword(password: string): Promise<unknown> {
  return api("/auth/setup", { password })
}

export function logout(): Promise<unknown> {
  return api("/auth/logout", {})
}

export function changePassword(current: string, password: string): Promise<unknown> {
  return api("/auth/password", { current, password })
}
