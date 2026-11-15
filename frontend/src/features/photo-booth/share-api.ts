import { api } from "@/lib/api";

export type PhotoShare = {
  shareId: string;
  expiresAt: string;
};

/** POST /v1/photo-shares. 로그인 없이 JPEG를 올리고 만료되는 공유 ID를 발급받는다. */
export function createPhotoShare(image: Blob) {
  const form = new FormData();
  form.append("image", image, "mairor-4cut.jpg");
  return api.post<PhotoShare>("/v1/photo-shares", { body: form });
}
