import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function PreviewPage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-xl font-semibold">미리보기</h1>
      <Button asChild size="lg">
        <Link href="/tutorial">튜토리얼 시작</Link>
      </Button>
    </main>
  );
}
