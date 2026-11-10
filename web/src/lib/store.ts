export type Screen = "library" | "drama" | "jasna" | "settings"
export type Theme = "light" | "dark"

const SCREEN_KEY = "media-helper.screen"
const THEME_KEY = "media-helper.theme"

export function initialScreen(): Screen {
  // 刷新后停留在原分类；非法或缺失值回落到 hanime 媒体库
  try {
    const saved = window.localStorage.getItem(SCREEN_KEY)
    return saved === "library" || saved === "drama" || saved === "jasna" || saved === "settings"
      ? saved
      : "library"
  } catch {
    return "library"
  }
}

export function saveScreen(screen: Screen): void {
  try {
    window.localStorage.setItem(SCREEN_KEY, screen)
  } catch {
    /* 隐私模式下忽略，不影响本次使用 */
  }
}

export function initialTheme(): Theme {
  try {
    const saved = window.localStorage.getItem(THEME_KEY)
    if (saved === "light" || saved === "dark") return saved
  } catch {
    /* 同上 */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark"
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark")
  try {
    window.localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* 同上 */
  }
}
