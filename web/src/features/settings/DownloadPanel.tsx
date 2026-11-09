import { useState } from "react"
import { Button, Card, Segmented, SettingRow, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import type { AppSettings } from "../../lib/types"

type Patch = (value: Partial<AppSettings>) => void

export function DownloadPanel({ draft, patch }: { draft: AppSettings; patch: Patch }) {
  const [advanced, setAdvanced] = useState(false)

  return (
    <>
      <Card title="下载">
        <SettingRow title="已有视频处理">
          <Segmented
            label="已有视频处理"
            value={draft.existingVideo}
            options={[
              { value: "skip", label: "跳过" },
              { value: "redownload", label: "重新下载" },
            ]}
            onChange={(value) => patch({ existingVideo: value as AppSettings["existingVideo"] })}
          />
        </SettingRow>
        <SettingRow title="失败重试次数" hint="0–20 次；0 表示不重试。">
          <TextInput
            value={Number.isNaN(draft.retries) ? "" : String(draft.retries)}
            onChange={(value) => patch({ retries: value.trim() ? Number(value) : Number.NaN })}
            mono
            ariaLabel="失败重试次数"
            className="w-[80px]"
          />
        </SettingRow>
      </Card>

      <Button variant="ghost" onClick={() => setAdvanced(!advanced)}>
        <span className={`transition-transform duration-150 ${advanced ? "rotate-90" : ""}`}>
          <Icon.chevronRight size={13} />
        </span>
        高级性能选项
      </Button>

      {advanced ? (
        <Card title="性能">
          <SettingRow title="下载间隔" hint="每个请求之间的等待时间（毫秒）。">
            <TextInput
              value={Number.isNaN(draft.downloadInterval) ? "" : String(draft.downloadInterval)}
              onChange={(value) => patch({ downloadInterval: value.trim() ? Number(value) : Number.NaN })}
              mono
              ariaLabel="下载间隔毫秒"
              className="w-[100px]"
            />
          </SettingRow>
          <SettingRow title="请求超时" hint="单个请求的最长等待时间（秒）。">
            <TextInput
              value={Number.isNaN(draft.requestTimeout) ? "" : String(draft.requestTimeout)}
              onChange={(value) => patch({ requestTimeout: value.trim() ? Number(value) : Number.NaN })}
              mono
              ariaLabel="请求超时秒"
              className="w-[100px]"
            />
          </SettingRow>
        </Card>
      ) : null}
    </>
  )
}
