import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Trace } from "@/components/Trace";
import { Skeleton } from "@/components/ui/skeleton";
import { transition } from "@/lib/motion";

/**
 * The waiting state.
 *
 * The backend runs the whole graph in one synchronous request and reports
 * nothing until it's finished, so there is no honest progress to show. What
 * this shows instead is elapsed time — which is true — and a trace that keeps
 * moving, which says the connection is alive without pretending to know how
 * far along it is.
 */

/** The placeholders sit on the same tints the real issue cards will, so the
 *  swap when results arrive doesn't change the texture of the page. */
const SKELETON_STOCKS = ["bg-stock-1", "bg-stock-3", "bg-stock-4"];

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export function RunningState({ url, checks }: { url: string; checks: string[] }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const interval = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    );
    return () => window.clearInterval(interval);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition(0.5)}
      aria-live="polite"
    >
      <div className="card-chart overflow-hidden bg-stock-2">
        <div className="flex items-center justify-between border-b border-rule px-5 py-3 md:px-7">
          <span className="flex items-center gap-2 label-mono">
            <span className="h-1.5 w-1.5 rounded-full bg-minor animate-blip" aria-hidden="true" />
            Reading
          </span>
          <span className="font-mono text-label text-ink-3" style={{ fontVariantNumeric: "tabular-nums" }}>
            {formatElapsed(elapsed)}
          </span>
        </div>

        <div className="px-5 py-6 md:px-7">
          <div className="font-mono text-sm text-ink">{url}</div>
          <div className="mt-1.5 font-mono text-xs uppercase tracking-[0.14em] text-ink-3">
            {checks.join(" · ")}
          </div>
        </div>

        {/* The live strip. It loops, because the run is still going. */}
        <div className="relative overflow-hidden bg-ink px-5 py-6 text-paper md:px-7">
          <Trace beats={5} amplitude={26} height={72} duration={2.4} strokeWidth={1.75} />
          <div
            className="pointer-events-none absolute inset-y-0 w-1/4 animate-sweep bg-gradient-to-r from-transparent via-paper/[0.12] to-transparent"
            aria-hidden="true"
          />
        </div>

        <p className="border-t border-rule px-5 py-4 text-sm leading-relaxed text-ink-2 md:px-7">
          Site Doctor is crawling the site, running each selected check over every page it reaches,
          and triaging what it finds. This runs in one pass, so there's nothing to report until it
          finishes — a ten-page site usually takes a few minutes. Leave this tab open.
        </p>
      </div>

      {/* Where the results will land. */}
      <div className="mt-5 space-y-4" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <div key={index} className={`card-chart p-6 ${SKELETON_STOCKS[index]}`}>
            <div className="flex items-center gap-3">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-24" />
            </div>
            <Skeleton className="mt-4 h-5 w-2/3" />
            <Skeleton className="mt-3 h-4 w-full" />
            <Skeleton className="mt-2 h-4 w-4/5" />
          </div>
        ))}
      </div>
    </motion.div>
  );
}
