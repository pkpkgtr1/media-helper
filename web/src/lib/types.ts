/** 与 Python 服务端 JSON 契约一一对应的类型定义。 */

export type FileState = "ready" | "missing" | "downloading" | "failed"

export type EntryStatus =
  | "pending"
  | "downloading"
  | "completed"
  | "failed"
  | "no-image"
  | "no-nfo"

export type TaskState = "waiting" | "downloading" | "completed" | "failed" | "cancelled"

export type TaskType = "视频" | "图片" | "NFO" | "画质"

export type TaskKind = "metadata" | "covers" | "video" | "repair" | "resolutions"

export interface Category {
  name: string
  checked: boolean
  group?: string
  aliases?: string[]
}

export interface AppSettings {
  outputRoot: string
  openAfter: boolean
  /** 网页截图已下线，后端统一归一为 download。 */
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
  /** FlareSolverr 会话 ID；填写后所有调用复用同一浏览器上下文。 */
  flaresolverrSession: string
  /** 自定义 User-Agent；留空表示各请求使用内置默认值。启用 FlareSolverr 时不生效。 */
  userAgent: string
  hgSaveRoot: string
  hgIntervalValue: number
  hgIntervalUnit: "minute" | "hour" | "day"
  hgConcurrent: number
  hgRetries: number
  hgRetryInterval: number
  /** Jasna 资源库是否按周期自动同步。 */
  ltxSyncEnabled: boolean
  ltxIntervalValue: number
  ltxIntervalUnit: "minute" | "hour" | "day"
  categories: Category[]
}

export interface LogLine {
  id: number
  t: string
  level: "info" | "warn" | "error"
  msg: string
  taskId?: string
}

export interface DownloadTask {
  currentCode?: string
  currentTitle?: string
  currentIndex?: number
  itemTotal?: number
  processed?: number
  phase?: string
  outputDir?: string
  entryId?: string
  id: string
  title: string
  code: string
  type: TaskType
  state: TaskState
  progress: number
  downloaded?: string
  total?: string
  speed?: string
  eta?: string
  indeterminate?: boolean
  error?: string
}

export interface MediaEntry {
  resolution?: string
  resolutionSource?: string
  isProcessingPlaceholder?: boolean
  originalCategoriesAvailable?: boolean
  id: string
  code: string
  title: string
  cover: string
  image: FileState
  nfo: FileState
  video: FileState
  videoProgress?: number
  status: EntryStatus
  description: string
  originalCategories: string[]
  exportedCategories: string[]
  paths: { video: string; nfo: string; cover: string }
  error?: string
}

export interface Snapshot {
  tasks: DownloadTask[]
  logs: LogLine[]
  revision: number
}

export interface LibraryResponse {
  entries: MediaEntry[]
  monthDir: string
  warnings: string[]
  categories: string[]
}

export interface SourceRef {
  key: string
  label: string
}

export interface DramaSearchItem {
  id: string
  source?: string
  sourceLabel?: string
  title: string
  url: string
  cover: string
  description: string
  episodeLabel: string
  score: string
  tags: string[]
}

export interface DramaDetail extends DramaSearchItem {
  total: number
  episodes: number[]
  premiered: string
  actors: string
}

export interface Subscription {
  id: string
  source?: string
  sourceLabel?: string
  videoId: string
  title: string
  url: string
  total: number
  knownEpisodes: number[]
  autoCheck: boolean
  intervalValue: number
  intervalUnit: string
  saveRoot: string
  autoDownload: boolean
  scope: "all" | "new" | "list"
  episodeList: number[]
  baseline: number[]
  lastCheckedIso: string | null
  nextCheckIso: string | null
  downloadedCount: number
  pendingCount: number
  activeTask: { id: string; kind: string; state: string; message: string } | null
}

export interface DramaTask {
  id: string
  source?: string
  sourceLabel?: string
  kind: string
  subscriptionId: string
  subscriptionTitle?: string
  state: string
  message: string
  progress: number
  error: string
  currentEpisode: number | null
  createdAt?: number
  finishedAt?: number | null
  detail: {
    episodes?: number[]
    ok?: number[]
    failed?: { episode: number; error: string }[]
  } | null
}

export interface DramaRecord {
  id?: string
  subscriptionId?: string
  title?: string
  source?: string
  episode: number
  path?: string
  size?: string
  at?: string
  [key: string]: unknown
}

export interface EnvironmentItem {
  name: string
  detail: string
  status: "ready" | "missing" | "optional"
}

export interface NfoPreview {
  affected: number
  unrecoverable: number
  preview: { id: string; title: string; before: string; after: string }[]
  token: string
}

export interface LtxItem {
  code: string
  title: string
  titleZh: string
  actors: string[]
  date: string
  maker: string
  cover: string
  url: string
  score: number
  votes: number
  linkCount: number
  pending: boolean
  missing: boolean
  waiting: boolean
  shot: string
  director: string
  genres: string[]
  subtitle: boolean
  addedAt: number | null
}

export interface LtxLink {
  kind: string
  name: string
  size: number
  sizeText: string
  url: string
}

export interface LtxDetail extends LtxItem {
  links: LtxLink[]
  subtitleUrl: string
  titleRaw: string
}

export interface LtxPage {
  items: LtxItem[]
  total: number
  page: number
  pages: number
  limit: number
}

export interface LtxStatus {
  total: number
  withLinks: number
  pending: number
  makers: number
  genres: number
  syncedAt: number | null
  nextSync: number | null
  updatedAt: number | null
  dateFrom: string
  dateTo: string
  lastError: string
  ready: boolean
  enabled: boolean
  intervalSeconds: number
  nyaa: { checked_at?: number; added?: number; ok?: boolean } | null
}
