import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function TutorialPage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-xl font-semibold">튜토리얼</h1>
      <Button asChild size="lg" variant="outline">
        <Link href="/">처음으로</Link>
      </Button>
    </main>
  );
}
