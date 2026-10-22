import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
      <h1 className="text-xl font-semibold">페이지를 찾을 수 없어요</h1>
      <p className="text-muted-foreground">주소가 바뀌었거나 없는 페이지예요.</p>
      <Button asChild size="lg">
        <Link href="/">처음으로</Link>
      </Button>
    </main>
  );
}
