import { Segmented, Select, SettingRow, TextInput } from "../../components/ui/primitives"
import { episodeRange, unitLabel } from "../../lib/format"
import { EpisodePicker } from "./shared"
import type { DramaDetail } from "../../lib/types"

export type Draft = {
  autoCheck: boolean
  intervalValue: number
  intervalUnit: string
  saveRoot: string
  autoDownload: boolean
  scope: "all" | "new" | "list"
  episodeList: number[]
}

const UNITS = [
  { value: "minute", label: "分钟" },
  { value: "hour", label: "小时" },
  { value: "day", label: "天" },
] as const

const SCOPES = [
  { value: "all", label: "全部下载" },
  { value: "new", label: "仅后续新增" },
  { value: "list", label: "指定集数" },
] as const

/** 订阅配置表单：新增订阅与编辑订阅共用。 */
export function ConfigForm({
  draft,
  patch,
  detail,
  pickEpisodes,
}: {
  draft: Draft
  patch: (value: Partial<Draft>) => void
  detail: DramaDetail | null
  pickEpisodes: boolean
}) {
  return (
    <div className="flex flex-col">
      <SettingRow title="自动检查更新" hint="关闭后仅可手动点击“检查”。">
        <Segmented
          label="自动检查更新"
          value={draft.autoCheck ? "on" : "off"}
          options={[
            { value: "on", label: "开启" },
            { value: "off", label: "关闭" },
          ]}
          onChange={(v) => patch({ autoCheck: v === "on" })}
        />
      </SettingRow>

      <SettingRow title="检查周期" hint="每条订阅独立计时，修改后按新周期生效。">
        <div className="flex items-center gap-2">
          <TextInput
            value={String(draft.intervalValue)}
            ariaLabel="检查周期数值"
            className="w-[72px]"
            onChange={(v) =>
              patch({ intervalValue: Math.max(1, Math.min(9999, Math.round(Number(v)) || 1)) })
            }
          />
          <Select
            value={draft.intervalUnit}
            options={UNITS}
            ariaLabel="检查周期单位"
            onChange={(v) => patch({ intervalUnit: v })}
            className="w-[92px]"
          />
          <span className="text-[12px] text-muted-fg">{unitLabel(draft.intervalUnit)}</span>
        </div>
      </SettingRow>

      <SettingRow title="保存路径" hint="Emby 剧集目录建在此路径下；相对路径按项目根目录解析。">
        <TextInput
          value={draft.saveRoot}
          mono
          ariaLabel="保存路径"
          placeholder="./media/AI短剧"
          onChange={(v) => patch({ saveRoot: v })}
          className="w-full min-w-[220px] sm:w-[340px]"
        />
      </SettingRow>

      <SettingRow title="自动下载" hint="开启后发现新集数自动下载；关闭后只提示更新。">
        <Segmented
          label="自动下载"
          value={draft.autoDownload ? "on" : "off"}
          options={[
            { value: "on", label: "开启" },
            { value: "off", label: "关闭" },
          ]}
          onChange={(v) => patch({ autoDownload: v === "on" })}
        />
      </SettingRow>

      <SettingRow title="下载范围">
        <Segmented
          label="下载范围"
          value={draft.scope}
          options={SCOPES}
          onChange={(v) => patch({ scope: v })}
        />
      </SettingRow>

      {draft.scope === "list" && detail ? (
        <div className="border-b border-line py-3 last:border-0">
          <div className="mb-2 text-[12px] text-muted-fg">
            选择要下载的集数（{episodeRange(detail.episodes)}）
          </div>
          <EpisodePicker
            options={detail.episodes}
            picked={draft.episodeList}
            onPick={(list) => patch({ episodeList: list })}
          />
        </div>
      ) : null}

      {pickEpisodes && !detail ? (
        <p className="py-2 text-[11px] text-muted-fg">指定集数需在订阅时选择；编辑时可留空。</p>
      ) : null}
    </div>
  )
}
