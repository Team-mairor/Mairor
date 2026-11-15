"use client";

import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { apiUrl } from "@/lib/api";

export default function SharedPhotoView() {
  const shareId = useSearchParams().get("id");
  const [expired, setExpired] = useState(false);
  const imageUrl = shareId ? apiUrl(`/v1/photo-shares/${encodeURIComponent(shareId)}`) : null;

  return (
    <main className="mx-auto flex min-h-(--screen-h) w-full max-w-[680px] flex-col items-center justify-center gap-5 px-6 py-8">
      <h1 className="font-display text-[26px] text-ink">네 컷 사진</h1>
      {!imageUrl || expired ? (
        <p role="alert" className="text-center text-[16px] text-mute">
          공유 시간이 끝났거나 사진을 찾을 수 없어요. 사진을 만든 사람에게 새 QR 코드를 요청해
          주세요.
        </p>
      ) : (
        <Image
          src={imageUrl}
          alt="완성된 네 컷 사진"
          width={1200}
          height={1800}
          unoptimized
          referrerPolicy="no-referrer"
          onError={() => setExpired(true)}
          className="h-auto w-[min(100%,calc(var(--screen-h)*0.56),640px)] max-w-full rounded-2xl object-contain md:w-[min(100%,calc(var(--screen-h)*0.6),640px)]"
        />
      )}
      {imageUrl && !expired && (
        <a
          href={imageUrl}
          download="mairor-4cut.jpg"
          referrerPolicy="no-referrer"
          className="flex h-14 w-full items-center justify-center rounded-full bg-navy text-[17px] font-bold text-white"
        >
          사진 저장
        </a>
      )}
    </main>
  );
}
