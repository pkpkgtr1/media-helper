import { useApp } from "../../state"
import { Button, Card, Segmented, Select, SettingRow, TextInput } from "../../components/ui/primitives"
import { Icon } from "../../components/ui/icons"
import { unitLabel } from "../../lib/format"
import type { AppSettings } from "../../lib/types"

type Patch = (value: Partial<AppSettings>) => void

const COVER_SITES = [
  { value: "dmm", label: "DMM" },
  { value: "animap", label: "ani-map" },
  { value: "auto", label: "自动选择" },
] as const

export function GeneralPanel({ draft, patch }: { draft: AppSettings; patch: Patch }) {
  const { pickDirectory } = useApp()

  async function browse() {
    try {
      const path = await pickDirectory()
      if (path) patch({ outputRoot: path })
    } catch {
      /* pickDirectory 失败时由上层提示，这里不重复打扰 */
    }
  }

  return (
    <>
      <Card title="常规">
        <SettingRow title="默认输出目录" hint="后续任务使用的默认媒体库位置。">
          <div className="flex flex-wrap items-center gap-2">
            <TextInput
              value={draft.outputRoot}
              onChange={(outputRoot) => patch({ outputRoot })}
              mono
              ariaLabel="默认输出目录"
              className="w-[260px]"
            />
            <Button size="sm" onClick={() => void browse()}>
              <Icon.folder size={14} />
              选择
            </Button>
          </div>
        </SettingRow>
        <SettingRow title="启动月份" hint="从媒体库页面选择需要处理的月份。">
          <span className="text-[12px] text-muted-fg">上一个月</span>
        </SettingRow>
        <SettingRow title="完成后打开输出目录" hint="任务全部结束后自动在文件管理器中打开目录。">
          <Segmented
            label="完成后打开输出目录"
            value={draft.openAfter ? "on" : "off"}
            options={[
              { value: "on", label: "开启" },
              { value: "off", label: "关闭" },
            ]}
            onChange={(v) => patch({ openAfter: v === "on" })}
          />
        </SettingRow>
      </Card>

      <Card title="Jasna 资源库">
        <SettingRow
          title="自动同步"
          hint="开启后按下面设定的周期从 ltx.libray.workers.dev 拉取全量数据；关闭后只能在资源库页面手动同步。"
        >
          <Segmented
            label="Jasna 资源库自动同步"
            value={draft.ltxSyncEnabled ? "on" : "off"}
            options={[
              { value: "on", label: "开启" },
              { value: "off", label: "关闭" },
            ]}
            onChange={(v) => patch({ ltxSyncEnabled: v === "on" })}
          />
        </SettingRow>
        <SettingRow
          title="同步周期"
          hint={
            draft.ltxSyncEnabled
              ? `每 ${draft.ltxIntervalValue} ${unitLabel(draft.ltxIntervalUnit)}自动同步一次，数据用于 Jasna 资源库分类的展示与搜索。`
              : "自动同步已关闭，此处的周期暂不生效。"
          }
        >
          <div className="flex flex-wrap items-center gap-2">
            <TextInput
              value={Number.isNaN(draft.ltxIntervalValue) ? "" : String(draft.ltxIntervalValue)}
              onChange={(value) =>
                patch({ ltxIntervalValue: value.trim() ? Number(value) : Number.NaN })
              }
              mono
              ariaLabel="Jasna 同步周期数值"
              className="w-[80px]"
            />
            <Select
              value={draft.ltxIntervalUnit}
              options={[
                { value: "minute", label: "分钟" },
                { value: "hour", label: "小时" },
                { value: "day", label: "天" },
              ]}
              ariaLabel="Jasna 同步周期单位"
              onChange={(value) => patch({ ltxIntervalUnit: value as AppSettings["ltxIntervalUnit"] })}
              className="w-[100px]"
            />
          </div>
        </SettingRow>
      </Card>

      <Card title="图片与封面">
        <SettingRow title="海报模式" hint="网页截图需要浏览器渲染，已下线；封面与背景图统一从站点下载。">
          <span className="text-[12px] text-muted-fg">下载图片</span>
        </SettingRow>
        <SettingRow title="封面来源">
          <Select
            value={draft.coverSite}
            options={COVER_SITES}
            ariaLabel="封面来源"
            onChange={(coverSite) => patch({ coverSite })}
            className="w-[140px]"
          />
        </SettingRow>
        <SettingRow
          title="已有图片处理"
          hint={draft.redownloadCover ? "将替换 poster.jpg，原有图片会被覆盖。" : "已存在的封面与背景图将保留，不会重新下载。"}
        >
          <Segmented
            label="已有图片处理"
            value={draft.redownloadCover ? "redownload" : "skip"}
            options={[
              { value: "skip", label: "跳过" },
              { value: "redownload", label: "重新下载" },
            ]}
            onChange={(v) => patch({ redownloadCover: v === "redownload" })}
          />
        </SettingRow>
      </Card>
    </>
  )
}
