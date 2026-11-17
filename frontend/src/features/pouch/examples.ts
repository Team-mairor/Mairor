import type { PouchItem } from "@/domain/pouch";

/** 파우치가 빈 화면(온보딩·홈·내 파우치)에 흐리게 보여 주는 예시 스티커. 파우치에 넣지 않는다 */
export const EXAMPLE_POUCH: PouchItem[] = [
  {
    id: "example-p1",
    cat: "베이스",
    type: "파운데이션",
    brand: "바닐라코",
    name: "커버리셔스 파워 핏 파운데이션",
    color: "#E9D2C2",
  },
  {
    id: "example-p2",
    cat: "치크",
    type: "블러셔",
    brand: "하밍",
    name: "젤리 에어 치크",
    color: "#EF8E8A",
  },
  {
    id: "example-p3",
    cat: "립",
    type: "립틴트",
    brand: "잉가",
    name: "벨벳 쥬 틴트",
    color: "#B5706B",
  },
  {
    id: "example-p4",
    cat: "아이",
    type: "섀도우 팔레트",
    brand: "에뛰드",
    name: "Play Color Eyes",
    color: "#C9A98B",
  },
  {
    id: "example-p5",
    cat: "아이",
    type: "아이라이너",
    brand: "페리페라",
    name: "Ink V Shadow 딥브라운",
    color: "#6B4E3D",
  },
];
