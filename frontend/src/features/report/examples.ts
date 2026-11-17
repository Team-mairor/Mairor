/** 리포트가 없을 때 흐리게 보여 주는 예시 룩 */
export type ExampleLook = {
  id: string;
  title: string;
  date: string;
  steps: number;
  photoUrl: string;
  /** 사진에서 보여 줄 부분(object-position 등) */
  photoClass: string;
};

/** 리포트가 빈 화면(홈·리포트)에 흐리게 보여 주는 예시 룩. 실제 기록으로 저장하지 않는다 */
export const EXAMPLE_LOOKS: ExampleLook[] = [
  {
    id: "example-1",
    title: "피부 좋아 보인다는 말 듣는 데일리 메이크업",
    date: "11월 12일",
    steps: 8,
    photoUrl: "/images/report-example-1.jpg",
    photoClass: "object-[50%_40%]",
  },
  {
    id: "example-2",
    title: "쿨톤의 물먹 코랄 봄 메이크업",
    date: "11월 8일",
    steps: 6,
    photoUrl: "/images/login-editorial.png",
    photoClass: "object-[50%_32%]",
  },
  {
    // 첫 사진의 입술·볼 부분을 확대해 다른 사진처럼 보이게 한다
    id: "example-3",
    title: "심플하고 세련된 10분 데일리 메이크업",
    date: "11월 3일",
    steps: 7,
    photoUrl: "/images/report-example-1.jpg",
    photoClass: "object-[50%_72%] scale-150",
  },
];
