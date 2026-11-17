import type { VideoItem } from "@/domain/video";

/** 많이 고른 영상이 아직 없을 때 Top 4 자리에 흐리게 보여 주는 예시 영상. 누를 수 없다 */
export const EXAMPLE_VIDEOS: VideoItem[] = [
  {
    id: "example-y1",
    ytid: "sWQ8tCgvs0E",
    title: "피부 좋아 보인다는 말 듣는 데일리 메이크업",
    ch: "뷰티 크리에이터 A",
    meta: "",
    dur: "12:40",
  },
  {
    id: "example-y2",
    ytid: "3gPaqVnkTMs",
    title: "쿨톤의 물먹 코랄 봄 메이크업",
    ch: "뷰티 크리에이터 B",
    meta: "",
    dur: "18:05",
  },
  {
    id: "example-y3",
    ytid: "UNv-fUnGcKM",
    title: "심플하고 세련된 10분 데일리 메이크업",
    ch: "뷰티 크리에이터 C",
    meta: "",
    dur: "10:31",
  },
  {
    id: "example-y4",
    ytid: "VxAXD6PP76I",
    title: "완성도 up! 요즘 진짜 예뻐진 메이크업 · 사람들 잘 모르는 스킬 총집합",
    ch: "뷰티 크리에이터 D",
    meta: "",
    dur: "30:58",
  },
];
