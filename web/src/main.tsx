import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import { AppProvider } from "./state"
import "./index.css"
import { applyTheme, initialTheme } from "./lib/store"

// 在首帧之前套用主题，避免深色模式闪白。
applyTheme(initialTheme())

const container = document.getElementById("root")
if (!container) throw new Error("缺少 #root 挂载节点")

createRoot(container).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
)
