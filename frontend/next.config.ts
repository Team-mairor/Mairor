import { join } from "node:path";

import type { NextConfig } from "next";

// 개발 서버에서만 /api를 BE로 넘긴다. 배포에서는 같은 Origin의 리버스 프록시가 맡는다.
// 정적 내보내기에서는 rewrites가 적용되지 않아, 값이 있을 때만 넣는다.
const apiProxyTarget = process.env.API_PROXY_TARGET?.replace(/\/$/, "");

// 운영 빌드에서는 클라이언트가 NEXT_PUBLIC_API_MOCK을 무시한다. 값이 남아 있으면 모르고 지나치지 않게 알린다.
if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_API_MOCK) {
  console.warn("NEXT_PUBLIC_API_MOCK은 운영 빌드에서 무시되어 실제 BE를 호출합니다.");
}

// cacheComponents·partialPrefetching은 정적 내보내기와 호환되지 않아 쓰지 않는다.
const nextConfig: NextConfig = {
  output: "export",
  ...(apiProxyTarget && {
    rewrites: async () => [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }],
  }),
  images: {
    unoptimized: true,
  },
  turbopack: {
    // 부위 점 번호처럼 AI와 같이 쓰는 파일(../shared)을 import할 수 있도록 저장소 루트를 기준으로 삼는다.
    root: join(__dirname, ".."),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
