import type { Metadata, Viewport } from "next";
import { Gowun_Dodum, Instrument_Sans, Instrument_Serif } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

import { Suspense } from "react";

import { DevNav } from "@/components/dev-nav";
import { SessionProvider } from "@/features/session";

// Pretendard (SIL OFL 1.1, fonts/Pretendard-LICENSE.txt)
const pretendard = localFont({
  src: "./fonts/PretendardVariable.woff2",
  variable: "--font-sans",
  weight: "45 920",
  display: "swap",
});

// 제목·안내 문구용 한글 디스플레이 서체
const gowun = Gowun_Dodum({
  variable: "--font-gowun",
  weight: "400",
  subsets: ["latin"],
  display: "swap",
});

// 워드마크·영문 장식용
const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  style: ["normal", "italic"],
  subsets: ["latin"],
  display: "swap",
});

// 영문 라벨(STEP 01, AI MAKEUP MIRROR 등)
const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "mairor",
  description: "내 얼굴에 맞춰 단계별로 따라 하는 메이크업 스마트 미러",
};

// 화면 확대 방지
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${pretendard.variable} ${gowun.variable} ${instrumentSerif.variable} ${instrumentSans.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        {/* 800px 세로 화면 칸. 폭 대응 규칙은 globals.css */}
        <div
          id="app"
          className="relative mx-auto flex min-h-dvh w-full max-w-[800px] flex-1 flex-col bg-white"
        >
          <SessionProvider>
            {/* useSearchParams(lib/use-query)의 Suspense 경계 */}
            <Suspense>
              {children}
              <DevNav />
            </Suspense>
          </SessionProvider>
        </div>
      </body>
    </html>
  );
}
