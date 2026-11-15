import type { Metadata } from "next";
import { Suspense } from "react";

import SharedPhotoView from "./shared-photo-view";

export const metadata: Metadata = {
  title: "네 컷 사진 | mairor",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function SharedPhotoPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-(--screen-h) items-center justify-center px-6 text-mute">
          사진을 불러오고 있어요.
        </main>
      }
    >
      <SharedPhotoView />
    </Suspense>
  );
}
