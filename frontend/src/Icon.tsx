import type { CSSProperties } from "react";

const paths = {
  chat: "M4 4h16v12H9l-5 4V4Z M8 8h8 M8 12h5",
  library: "M4 4h4v16H4z M11 4h4v16h-4z M18 5l3 14",
  layers: "m12 3 9 5-9 5-9-5 9-5Z M3 12l9 5 9-5 M3 16l9 5 9-5",
  slides: "M3 4h18v13H3z M12 17v4 M8 21h8 M7 8h10 M7 12h6",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z m-4 9 3 3 5-6",
  info: "M12 11v6 M12 7h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  plus: "M12 5v14 M5 12h14",
  search: "M16 16l5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  trash: "M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7",
  attach: "m8 12 7-7a4 4 0 0 1 6 6L11 21a6 6 0 0 1-8-8L14 2 M6 15l9-9",
  pin: "m8 3 8 0-1 6 4 4H5l4-4-1-6Z M12 13v8",
  mic: "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0V5Z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3",
  arrow: "M12 19V5 m-6 6 6-6 6 6",
  diagonal: "M6 18 18 6 M6 6h12v12",
  download: "M12 3v12 m-5-5 5 5 5-5 M4 17v4h16v-4",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  panel: "M3 4h18v16H3z M9 4v16",
  close: "m6 6 12 12 M6 18 18 6",
  check: "m5 12 4 4L19 6",
  play: "m8 4 12 8-12 8V4Z",
  document: "M5 3h10l4 4v14H5V3Z M14 3v5h5 M9 12h6 M9 16h6",
  graph: "M8 7l8 3 M7 9l3 8 M16 12l-4 5 M8 5a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z M20 11a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z M13 19a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z",
} as const;
export type IconName = keyof typeof paths;

export default function Icon({ name, size = 18, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name]} /></svg>;
}
