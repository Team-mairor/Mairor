/* eslint-disable @next/next/no-img-element -- 메모리에 둔 data URL */
import type { StepPhoto } from "@/features/session";

/** 단계 사진. crop이면 그 단계 부위(box)만 칸에 꽉 차게, 아니면 얼굴 전체 */
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
  if (!crop || !box)
    return <img src={url} alt={alt} className="absolute inset-0 size-full object-cover" />;
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
