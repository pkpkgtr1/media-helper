import { useState } from "react"
import { Shell } from "./components/Shell"
import { LogDrawer } from "./components/LogDrawer"
import { LibraryScreen } from "./features/library/LibraryScreen"
import { DramaScreen } from "./features/drama/DramaScreen"
import { SettingsScreen } from "./features/settings/SettingsScreen"
import { initialScreen, saveScreen, type Screen } from "./lib/store"

export default function App() {
  const [screen, setScreen] = useState<Screen>(initialScreen)

  function go(next: Screen) {
    setScreen(next)
    saveScreen(next)
  }

  return (
    <Shell screen={screen} onScreen={go}>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1">
          {screen === "library" ? <LibraryScreen /> : null}
          {screen === "drama" ? <DramaScreen /> : null}
          {/* 设置页常驻挂载：切换分类时草稿不会丢失 */}
          <div className={screen === "settings" ? "h-full" : "hidden"}>
            <SettingsScreen />
          </div>
        </div>
        <LogDrawer />
      </div>
    </Shell>
  )
}
