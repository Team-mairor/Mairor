import type { MetadataRoute } from "next";

// 정적 내보내기(out/)에서 manifest.webmanifest 파일로 나오게 한다
export const dynamic = "force-static";

/**
 * 시연 태블릿(갤럭시탭 S6) 키오스크용. 크롬 「설치」로 홈 화면에 올리면 주소창·상태바·내비 바 없이 800×1280 전체 화면으로 열린다.
 * 아이콘은 브랜드 색으로 만든 임시 이미지다
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "mairor",
    short_name: "mairor",
    description: "내 얼굴에 맞춰 단계별로 따라 하는 메이크업 스마트 미러",
    start_url: "/",
    display: "fullscreen",
    orientation: "portrait",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
