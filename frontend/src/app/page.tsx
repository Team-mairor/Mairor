import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">mairor</h1>
      <Button asChild size="lg">
        <Link href="/select">영상 선택하기</Link>
      </Button>
    </main>
  );
}
