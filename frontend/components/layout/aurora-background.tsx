"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Premium animated backdrop: aurora gradient blobs over a subtle grid.
 * Used across auth and dashboard surfaces.
 */
export function AuroraBackground({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* Aurora blobs */}
      <div className="aurora-blob left-[-10%] top-[-15%] h-[42rem] w-[42rem] bg-violet-600/25 dark:bg-violet-600/20" />
      <div className="aurora-blob right-[-8%] top-[10%] h-[36rem] w-[36rem] bg-sky-500/20 dark:bg-sky-500/15" style={{ animationDelay: "-4s" }} />
      <div className="aurora-blob bottom-[-20%] left-[25%] h-[40rem] w-[40rem] bg-fuchsia-500/15 dark:bg-fuchsia-500/10" style={{ animationDelay: "-9s" }} />

      {/* Grid overlay */}
      <div className="pointer-events-none absolute inset-0 grid-pattern opacity-40 [mask-image:radial-gradient(ellipse_at_center,black_35%,transparent_75%)]" />

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8 }}
        className="relative z-10 flex min-h-screen flex-col"
      >
        {children}
      </motion.div>
    </div>
  );
}
