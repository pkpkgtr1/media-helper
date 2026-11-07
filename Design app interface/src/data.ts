export type FileState = "ready" | "missing" | "downloading" | "failed"
export type EntryStatus =
  | "pending"
  | "downloading"
  | "completed"
  | "failed"
  | "no-image"
  | "no-nfo"

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

export type TaskState = "waiting" | "downloading" | "completed" | "failed" | "cancelled"
export type TaskType = "视频" | "图片" | "NFO" | "画质"

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

export interface Category {
  name: string
  checked: boolean
  group?: string
  aliases?: string[]
}

