import { join } from "node:path";

import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

// 개발 서버에서만 /api를 BE로 넘긴다. 배포에서는 같은 Origin의 리버스 프록시가 맡는다.
// 정적 내보내기에서는 rewrites가 적용되지 않아, 값이 있을 때만 넣는다.
const apiProxyTarget = process.env.API_PROXY_TARGET?.replace(/\/$/, "");

// 운영 빌드에서는 클라이언트가 NEXT_PUBLIC_API_MOCK을 무시한다. 값이 남아 있으면 모르고 지나치지 않게 알린다.
if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_API_MOCK) {
  console.warn("NEXT_PUBLIC_API_MOCK은 운영 빌드에서 무시되어 실제 BE를 호출합니다.");
}

// 개발 도구(debug 화면·DevNav). 개발 서버에서는 켜지고 빌드에서는 빠진다. DEV_TOOLS=1|0으로 바꾼다.
// DevNav는 개발 서버에서만 켜진다.
const devToolsEnabled = (phase: string) => {
  if (process.env.DEV_TOOLS === "1") return true;
  if (process.env.DEV_TOOLS === "0") return false;
  return phase === PHASE_DEVELOPMENT_SERVER;
};

// cacheComponents·partialPrefetching은 정적 내보내기와 호환되지 않아 쓰지 않는다.
const nextConfig = (phase: string): NextConfig => {
  const devTools = devToolsEnabled(phase);
  return {
    output: "export",
    // 왼쪽 아래는 개발용 바로가기(DevNav) 열기 버튼 자리라, 개발 표시가 덮어 버튼이 눌리지 않는다
    devIndicators: { position: "bottom-right" },
    env: { DEV_TOOLS: devTools ? "1" : "" },
    // debug 화면은 *.dev.tsx로 두어 개발 도구가 꺼지면 라우트에서 빠진다.
    pageExtensions: devTools ? ["dev.tsx", "tsx", "ts", "jsx", "js"] : ["tsx", "ts", "jsx", "js"],
    // 같은 와이파이의 폰·태블릿(https://<PC의 IP>:3000)에서 개발 서버 화면이 동작하게 사설 IP 대역을 허용한다.
    // 없으면 Next 16이 /_next 개발 요청을 막아 화면은 보여도 버튼이 눌리지 않는다.
    // 172는 사설 대역(172.16~31)만 연다. 70.12는 교육장 와이파이가 PC에 주는 대역이다
    allowedDevOrigins: [
      "10.*.*.*",
      "70.12.*.*",
      ...Array.from({ length: 16 }, (_, i) => `172.${16 + i}.*.*`),
      "192.168.*.*",
    ],
    ...(apiProxyTarget && {
      rewrites: async () => [
        { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
      ],
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
};

export default nextConfig;
