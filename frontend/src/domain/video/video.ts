import type { VideoChapter, VideoSearchItem } from "@/lib/api";

import type { Chapter, VideoItem } from "./types";

/** 유튜브 영상 썸네일 주소 */
export function videoThumb(ytid: string) {
  return `https://i.ytimg.com/vi/${ytid}/hqdefault.jpg`;
}

/** 분석 진행 단계 (API progressStage) */
export const ANALYSIS_PHASES: [en: string, label: string, from: number][] = [
  ["QUEUED", "대기", 0],
  ["FETCH", "영상 불러오기", 3],
  ["SCENES", "구간 나누기", 12],
  ["DETECT", "제품 인식", 28],
  ["STEPS", "단계 추출", 52],
  ["GUIDE", "가이드 구성", 80],
];

/** 영상 길이. 12:40, 1:02:03 */
export function formatDuration(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const mm = String(Math.floor((s % 3600) / 60));
  const ss = String(s % 60).padStart(2, "0");
  return s >= 3600 ? `${Math.floor(s / 3600)}:${mm.padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
}

/** 조회수. 18만회, 3.2만회, 1.5억회, 950회 */
export function formatViews(n: number) {
  const unit = (v: number, u: string) =>
    `${v < 10 ? Math.floor(v * 10) / 10 : Math.floor(v)}${u}회`;
  if (n >= 1e8) return unit(n / 1e8, "억");
  if (n >= 1e4) return unit(n / 1e4, "만");
  return `${n}회`;
}

const RELATIVE = new Intl.RelativeTimeFormat("ko", { numeric: "auto" });
const SPANS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["week", 7 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** 게시 시각을 "2주 전"처럼. 1분 안이면 "방금" */
export function formatAgo(iso: string, now = Date.now()) {
  const sec = (now - Date.parse(iso)) / 1000;
  const span = SPANS.find(([, size]) => sec >= size);
  return span ? RELATIVE.format(-Math.floor(sec / span[1]), span[0]) : "방금";
}

/** 검색·선택 응답을 화면이 쓰는 영상 모양으로. id는 YouTube 영상 ID다 */
export function toVideoItem(v: VideoSearchItem): VideoItem {
  const meta = [
    v.viewCount === null ? null : `조회수 ${formatViews(v.viewCount)}`,
    v.publishedAt === null ? null : formatAgo(v.publishedAt),
  ];
  return {
    id: v.youtubeVideoId,
    ytid: v.youtubeVideoId,
    title: v.title,
    ch: v.channelTitle,
    meta: meta.filter(Boolean).join(" · "),
    dur: formatDuration(v.durationSeconds),
  };
}

/** 설명란 챕터를 화면 모양으로 */
export function toChapter(c: VideoChapter): Chapter {
  return { time: formatDuration(c.startSeconds), label: c.label };
}
