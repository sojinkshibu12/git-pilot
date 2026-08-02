import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-muted-foreground", className)} aria-label="Loading" />;
}

export function PageLoader() {
  return (
    <div className="flex min-h-[240px] items-center justify-center">
      <Spinner className="h-7 w-7" />
    </div>
  );
}
