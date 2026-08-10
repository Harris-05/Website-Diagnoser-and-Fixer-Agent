import { motion } from "motion/react";
import { ExternalLink } from "lucide-react";
import { SeverityTag } from "@/components/SeverityTag";
import { cn } from "@/lib/utils";
import { revealFlatVariants } from "@/lib/motion";
import type { UXSuggestion } from "@/lib/api";

/**
 * UX findings are judgement calls with no mechanical check behind them, so
 * their triage tags are outlined rather than filled. Filled means measured;
 * outlined means someone looked at it and formed a view. The distinction is
 * carried by the tag itself, not by a disclaimer nobody reads.
 */
export function UxSuggestionCard({
  suggestion,
  stock,
}: {
  suggestion: UXSuggestion;
  stock?: string;
}) {
  return (
    <motion.li variants={revealFlatVariants} className={cn("card-chart p-5 md:p-6", stock)}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityTag severity={suggestion.severity} variant="outline" />
        <span className="font-mono text-micro uppercase text-ink-3">{suggestion.category}</span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="label-mono mb-1.5">What it saw</div>
          <p className="text-[0.9375rem] leading-relaxed text-ink-2">{suggestion.observation}</p>
        </div>
        <div className="sm:border-l sm:border-rule sm:pl-4">
          <div className="label-mono mb-1.5">What to change</div>
          <p className="text-[0.9375rem] leading-relaxed text-ink">{suggestion.recommendation}</p>
        </div>
      </div>

      {suggestion.page_url && (
        <a
          href={suggestion.page_url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-4 inline-flex max-w-full items-center gap-1.5 border-t border-rule pt-3 font-mono text-xs text-ink-3 transition-colors hover:text-ink"
        >
          <span className="truncate">{suggestion.page_url}</span>
          <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
        </a>
      )}
    </motion.li>
  );
}
