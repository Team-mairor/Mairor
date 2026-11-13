/* eslint-disable @next/next/no-img-element -- 메모리에 둔 data URL */
import type { StepPhoto } from "@/features/session";

/** 단계 사진. crop이면 그 단계 부위(box)만 칸에 꽉 차게, 아니면 사진 전체 */
export function StepPhotoImg({
  photo,
  crop = false,
  alt = "",
}: {
  photo: StepPhoto;
  crop?: boolean;
  alt?: string;
}) {
  const { url, box } = photo;
  // 사진 전체를 잘라 내지 않고 보여 주고, 칸과 비율이 달라 남는 곳은 같은 사진을 흐리게 깔아 채운다
  if (!crop)
    return (
      <>
        <img
          src={url}
          alt=""
          aria-hidden
          className="absolute inset-0 size-full scale-110 object-cover opacity-60 blur-2xl"
        />
        <img src={url} alt={alt} className="absolute inset-0 size-full object-contain" />
      </>
    );
  if (!box) return <img src={url} alt={alt} className="absolute inset-0 size-full object-cover" />;
  return (
    <img
      src={url}
      alt={alt}
      className="absolute h-auto max-w-none"
      style={{
        width: `${100 / box.w}%`,
        left: `${(-box.x / box.w) * 100}%`,
        top: `${(-box.y / box.h) * 100}%`,
      }}
    />
  );
}
