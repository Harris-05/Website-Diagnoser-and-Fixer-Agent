import { useState } from "react";
import { motion } from "motion/react";
import { ChevronDown, ExternalLink, Wrench } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { SeverityTag, SEVERITY_BAR } from "@/components/SeverityTag";
import { cn } from "@/lib/utils";
import { revealFlatVariants } from "@/lib/motion";
import type { Issue } from "@/lib/api";

const SOURCE_LABEL: Record<Issue["source"], string> = {
  lighthouse: "Lighthouse",
  security: "Security",
  ux: "UX review",
};

export function IssueCard({ issue, stock }: { issue: Issue; stock?: string }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(issue.description || issue.affected_selector);

  return (
    <motion.li
      variants={revealFlatVariants}
      className={cn("card-chart group relative overflow-hidden", stock)}
    >
      {/* Severity reads down the edge of the card, so a column of these can be
          scanned by colour alone before anything is read. */}
      {issue.severity && (
        <span
          className={cn("absolute inset-y-0 left-0 w-[3px]", SEVERITY_BAR[issue.severity])}
          aria-hidden="true"
        />
      )}

      <div className="p-5 pl-6 md:p-6 md:pl-7">
        <div className="flex flex-wrap items-center gap-2">
          {issue.severity && <SeverityTag severity={issue.severity} />}
          <span className="font-mono text-micro uppercase text-ink-3">
            {SOURCE_LABEL[issue.source]} · {issue.category}
          </span>
          {typeof issue.fix_confidence === "number" && (
            <span className="font-mono text-micro uppercase text-ink-3">
              Fix confidence {Math.round(issue.fix_confidence * 100)}%
            </span>
          )}
        </div>

        <h3 className="mt-3 font-display text-base font-bold leading-snug tracking-tight text-ink">
          {issue.title}
        </h3>

        {issue.plain_language_summary && (
          <p className="mt-2.5 text-[0.9375rem] leading-relaxed text-ink-2">
            {issue.plain_language_summary}
          </p>
        )}

        {issue.suggested_solution && (
          <div className="mt-4 rounded-md border border-rule bg-paper-sunk p-4">
            <div className="flex items-center gap-2">
              <Wrench className="h-3.5 w-3.5 text-ink-3" strokeWidth={2} aria-hidden="true" />
              <span className="label-mono">Suggested fix</span>
            </div>
            <p className="mt-2.5 whitespace-pre-line text-[0.9375rem] leading-relaxed text-ink-2">
              {issue.suggested_solution}
            </p>

            {issue.solution_sources.length > 0 && (
              <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-rule pt-3">
                {issue.solution_sources.map((source) => (
                  <li key={source}>
                    <a
                      href={source}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 font-mono text-xs text-ink-3 underline decoration-rule underline-offset-2 transition-colors hover:text-ink hover:decoration-ink"
                    >
                      {hostOf(source)}
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {hasDetail && (
          <Collapsible open={open} onOpenChange={setOpen} className="mt-4">
            <CollapsibleTrigger className="flex items-center gap-1.5 font-mono text-label uppercase tracking-[0.14em] text-ink-3 transition-colors hover:text-ink">
              <ChevronDown
                className={cn("h-3.5 w-3.5 transition-transform duration-300", open && "rotate-180")}
                aria-hidden="true"
              />
              {open ? "Hide detail" : "Show detail"}
            </CollapsibleTrigger>

            <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
              <div className="space-y-3 pt-4">
                {issue.description && (
                  <p className="text-sm leading-relaxed text-ink-2">{issue.description}</p>
                )}
                {issue.affected_selector && (
                  <div>
                    <div className="label-mono mb-1.5">Element</div>
                    <code className="block overflow-x-auto rounded-sm border border-rule bg-paper-sunk px-3 py-2 font-mono text-xs text-ink">
                      {issue.affected_selector}
                    </code>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}

        {issue.source_url && (
          <a
            href={issue.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-4 inline-flex max-w-full items-center gap-1.5 truncate border-t border-rule pt-3 font-mono text-xs text-ink-3 transition-colors hover:text-ink"
          >
            <span className="truncate">{issue.source_url}</span>
            <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
          </a>
        )}
      </div>
    </motion.li>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
