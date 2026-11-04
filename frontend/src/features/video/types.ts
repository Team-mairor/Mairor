// 영상 입력·분석 화면이 주고받는 영상 모양. API가 붙으면 lib/api/types와 맞춘다

export interface VideoItem {
  id: string;
  ytid: string;
  title: string;
  ch: string;
  meta: string;
  dur: string;
}

/** 영상 상태 (API-VIDEO-001) */
export type VideoState = "new" | "guide" | "running" | "blocked" | "quota";

export interface Chapter {
  time: string;
  label: string;
}
