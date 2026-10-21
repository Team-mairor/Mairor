import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function SelectPage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-xl font-semibold">영상 선택</h1>
      <Button asChild size="lg">
        <Link href="/preview">미리보기</Link>
      </Button>
    </main>
  );
}
