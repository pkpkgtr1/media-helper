import type { SVGProps } from "react"

/**
 * 统一线性图标集：20×20 视框、1.6 描边、圆角端点。
 * 全部为内联 SVG，不依赖图标字体，可随 currentColor 变色。
 */
type IconProps = { size?: number; className?: string; title?: string }

function base(size: number): SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
  }
}

function Svg({ size = 18, className, title, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg {...base(size)} className={className} role={title ? "img" : undefined}>
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  )
}

export const Icon = {
  library: (p: IconProps) => (
    <Svg {...p}>
      <rect x="3" y="3" width="5.2" height="14" rx="1.2" />
      <rect x="11.8" y="3" width="5.2" height="14" rx="1.2" />
      <path d="M5.6 6.6h.01M14.4 6.6h.01" />
    </Svg>
  ),
  drama: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.6" y="4.4" width="14.8" height="11.2" rx="2" />
      <path d="M8.2 8.1v3.8l3.2-1.9z" />
    </Svg>
  ),
  settings: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="2.6" />
      <path d="M10 2.3v1.9M10 15.8v1.9M2.3 10h1.9M15.8 10h1.9M4.6 4.6l1.35 1.35M14.05 14.05l1.35 1.35M15.4 4.6l-1.35 1.35M5.95 14.05L4.6 15.4" />
    </Svg>
  ),
  logs: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 5.2h12M4 9h12M4 12.8h8.5" />
    </Svg>
  ),
  folder: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 5.6A1.6 1.6 0 0 1 4.6 4h3.1l1.5 1.9h6.2A1.6 1.6 0 0 1 17 7.5v6.9A1.6 1.6 0 0 1 15.4 16H4.6A1.6 1.6 0 0 1 3 14.4z" />
    </Svg>
  ),
  open: (p: IconProps) => (
    <Svg {...p}>
      <path d="M8.4 4H4.6A1.6 1.6 0 0 0 3 5.6v9.8A1.6 1.6 0 0 0 4.6 17h9.8a1.6 1.6 0 0 0 1.6-1.6V11.6M11.6 4H16v4.4M16 4l-6.6 6.6" />
    </Svg>
  ),
  refresh: (p: IconProps) => (
    <Svg {...p}>
      <path d="M15.6 6.6A6.1 6.1 0 1 0 16 10M15.6 3.6v3h-3" />
    </Svg>
  ),
  search: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="8.6" cy="8.6" r="4.9" />
      <path d="M12.3 12.3L16 16" />
    </Svg>
  ),
  image: (p: IconProps) => (
    <Svg {...p}>
      <rect x="3" y="4.2" width="14" height="11.6" rx="1.6" />
      <circle cx="7.4" cy="8" r="1.1" />
      <path d="M4 14l3.9-3.4 2.9 2.4 2.5-2L16 13.6" />
    </Svg>
  ),
  close: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5.2 5.2l9.6 9.6M14.8 5.2l-9.6 9.6" />
    </Svg>
  ),
  chevronRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M7.6 4.4l5.6 5.6-5.6 5.6" />
    </Svg>
  ),
  chevronDown: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4.4 7.6L10 13.2l5.6-5.6" />
    </Svg>
  ),
  retry: (p: IconProps) => (
    <Svg {...p}>
      <path d="M15.6 6.6A6.1 6.1 0 1 0 16 10M15.6 3.6v3h-3" />
    </Svg>
  ),
  warn: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 3.4L2.8 16h14.4z" />
      <path d="M10 7.9v3.3M10 13.8h.01" />
    </Svg>
  ),
  check: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="7" />
      <path d="M6.9 10.2l2.2 2.2 4.1-4.4" />
    </Svg>
  ),
  download: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 3.2v9.1m0 0l3.6-3.6M10 12.3L6.4 8.7M4 15.8h12" />
    </Svg>
  ),
  stop: (p: IconProps) => (
    <Svg {...p}>
      <rect x="5.6" y="5.6" width="8.8" height="8.8" rx="1.6" />
    </Svg>
  ),
  trash: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3.8 5.6h12.4M8 5.6V4.2h4v1.4M5.4 5.6l.7 10a1.4 1.4 0 0 0 1.4 1.3h5a1.4 1.4 0 0 0 1.4-1.3l.7-10" />
    </Svg>
  ),
  plus: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 4.4v11.2M4.4 10h11.2" />
    </Svg>
  ),
  edit: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12.9 3.9l3.2 3.2-8.4 8.4-3.9.7.7-3.9z" />
    </Svg>
  ),
  pause: (p: IconProps) => (
    <Svg {...p}>
      <path d="M7.6 4.6v10.8M12.4 4.6v10.8" />
    </Svg>
  ),
  play: (p: IconProps) => (
    <Svg {...p}>
      <path d="M6.8 4.4l8.4 5.6-8.4 5.6z" />
    </Svg>
  ),
  sun: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="3.4" />
      <path d="M10 2.4v1.8M10 15.8v1.8M2.4 10h1.8M15.8 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M15.3 4.7L14 6M6 14l-1.3 1.3" />
    </Svg>
  ),
  moon: (p: IconProps) => (
    <Svg {...p}>
      <path d="M16 12.6A6.9 6.9 0 0 1 7.4 4a7 7 0 1 0 8.6 8.6z" />
    </Svg>
  ),
  database: (p: IconProps) => (
    <Svg {...p}>
      <ellipse cx="10" cy="5.4" rx="6" ry="2.4" />
      <path d="M4 5.4v9.2c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4V5.4M4 10c0 1.3 2.7 2.4 6 2.4s6-1.1 6-2.4" />
    </Svg>
  ),
  film: (p: IconProps) => (
    <Svg {...p}>
      <rect x="3" y="4" width="14" height="12" rx="1.8" />
      <path d="M3 8h14M3 12h14M7 4v12M13 4v12" />
    </Svg>
  ),
  clock: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 6.2V10l2.6 1.7" />
    </Svg>
  ),
  link: (p: IconProps) => (
    <Svg {...p}>
      <path d="M8.4 11.6a3.4 3.4 0 0 0 4.8 0l2-2a3.4 3.4 0 0 0-4.8-4.8l-1 1" />
      <path d="M11.6 8.4a3.4 3.4 0 0 0-4.8 0l-2 2a3.4 3.4 0 0 0 4.8 4.8l1-1" />
    </Svg>
  ),
}

export type IconName = keyof typeof Icon
