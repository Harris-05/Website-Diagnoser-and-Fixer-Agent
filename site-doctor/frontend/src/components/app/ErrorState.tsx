import { motion } from "motion/react";
import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { transition } from "@/lib/motion";

/**
 * The 500 path. The pipeline shells out to Lighthouse and Playwright and
 * calls a model, so failures are usually environmental — say what happened
 * and what to check, rather than apologising.
 */
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <motion.div
      role="alert"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition(0.45)}
      className="card-chart overflow-hidden bg-stock-1"
    >
      <div className="flex items-center gap-2 border-b border-rule bg-critical/[0.07] px-5 py-3 md:px-7">
        <span className="h-1.5 w-1.5 rounded-full bg-critical" aria-hidden="true" />
        <span className="font-mono text-label font-medium uppercase tracking-[0.14em] text-[hsl(var(--critical-ink))]">
          The audit stopped
        </span>
      </div>

      <div className="px-5 py-6 md:px-7">
        <p className="text-[0.9375rem] leading-relaxed text-ink-2">{message}</p>

        <div className="mt-5 rounded-md border border-rule bg-paper-sunk p-4">
          <div className="label-mono mb-2.5">Worth checking</div>
          <ul className="space-y-1.5 font-mono text-xs leading-relaxed text-ink-2">
            <li>The backend is running: <span className="text-ink">uvicorn main:app --reload</span></li>
            <li>Lighthouse is installed: <span className="text-ink">npm install -g lighthouse</span></li>
            <li>Chromium is installed: <span className="text-ink">playwright install chromium</span></li>
            <li>An API key is set for the triage and fix steps</li>
            <li>The address is reachable and doesn't block automated browsers</li>
          </ul>
        </div>

        <Button onClick={onRetry} variant="outline" className="mt-5 group">
          <RotateCcw className="h-3.5 w-3.5 transition-transform duration-300 group-hover:-rotate-90" />
          Start another audit
        </Button>
      </div>
    </motion.div>
  );
}
