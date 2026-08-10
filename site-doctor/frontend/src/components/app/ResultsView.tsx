import { motion } from "motion/react";
import { Download, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CountUp } from "@/components/CountUp";
import { SeverityTag, SEVERITY_BAR, SEVERITY_MEANING } from "@/components/SeverityTag";
import { ScorePanel } from "@/components/app/ScorePanel";
import { STOCKS_ISSUES, stockFor } from "@/lib/stock";
import { IssueCard } from "@/components/app/IssueCard";
import { UxSuggestionCard } from "@/components/app/UxSuggestionCard";
import {
  averageScores,
  collectIssues,
  countBySeverity,
  reportUrl,
  SEVERITY_ORDER,
  type AuditResponse,
  type Issue,
  type Severity,
} from "@/lib/api";
import {
  containerVariants,
  containerVariantsSlow,
  itemVariants,
  inView,
  inViewTall,
  transition,
} from "@/lib/motion";

interface ResultsViewProps {
  result: AuditResponse;
  onReset: () => void;
}

export function ResultsView({ result, onReset }: ResultsViewProps) {
  const issues = collectIssues(result);
  const counts = countBySeverity(issues);
  const scores = averageScores(result.audit_before);
  const untriaged = issues.filter((issue) => !issue.severity);

  return (
    <div className="space-y-5">
      <SummaryStrip result={result} counts={counts} total={issues.length} />

      <ScorePanel scores={scores} pageCount={Math.max(result.pages_crawled, 1)} />

      {issues.length === 0 ? (
        <EmptyPanel
          title="No issues came back."
          body="The checks you selected ran and found nothing to flag. That's a real result — but it's worth widening the crawl limits or turning on another check before you take it as a clean bill of health."
        />
      ) : (
        SEVERITY_ORDER.map((severity) => {
          const group = issues.filter((issue) => issue.severity === severity);
          if (group.length === 0) return null;
          return <IssueGroup key={severity} severity={severity} issues={group} />;
        })
      )}

      {untriaged.length > 0 && (
        <section>
          <div className="mb-4 flex items-center gap-3">
            <span className="font-mono text-micro uppercase text-ink-3">Untriaged</span>
            <span className="h-px flex-1 bg-rule" aria-hidden="true" />
            <span className="font-mono text-micro text-ink-3">{untriaged.length}</span>
          </div>
          <motion.ul
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={inViewTall}
            className="space-y-4"
          >
            {untriaged.map((issue, index) => (
              <IssueCard
                key={issue.id}
                issue={issue}
                stock={stockFor(STOCKS_ISSUES, index)}
              />
            ))}
          </motion.ul>
        </section>
      )}

      {result.ux_suggestions.length > 0 && (
        <section className="pt-4">
          <motion.div
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={inView}
            className="mb-5"
          >
            <motion.h2 variants={itemVariants} className="font-display text-d3">
              How the pages read
            </motion.h2>
            <motion.p
              variants={itemVariants}
              className="mt-2 max-w-[62ch] text-[0.9375rem] leading-relaxed text-ink-2"
            >
              Judgement calls from the vision review. There's no mechanical check behind these, so
              they're suggestions — read them, decide, and change what you agree with.
            </motion.p>
          </motion.div>

          <motion.ul
            variants={containerVariantsSlow}
            initial="hidden"
            whileInView="visible"
            viewport={inViewTall}
            className="space-y-4"
          >
            {result.ux_suggestions.map((suggestion, index) => (
              <UxSuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                stock={stockFor(STOCKS_ISSUES, index + 1)}
              />
            ))}
          </motion.ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-4 border-t border-rule pt-8">
        <Button onClick={onReset} variant="outline" className="group">
          <RotateCcw className="h-3.5 w-3.5 transition-transform duration-300 group-hover:-rotate-90" />
          Audit another site
        </Button>
        <p className="font-mono text-xs text-ink-3">
          Nothing on your server was changed. Every fix above is a proposal.
        </p>
      </div>
    </div>
  );
}

function SummaryStrip({
  result,
  counts,
  total,
}: {
  result: AuditResponse;
  counts: Record<Severity, number>;
  total: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition(0.55)}
      className="card-chart overflow-hidden bg-stock-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-3 md:px-7">
        <span className="label-mono">Chart complete</span>
        <span className="font-mono text-micro uppercase text-ink-3">
          {result.pages_crawled} {result.pages_crawled === 1 ? "page" : "pages"} ·{" "}
          {result.selected_checks.join(" · ")}
        </span>
      </div>

      <div className="px-5 py-6 md:px-7">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div className="min-w-0">
            <div className="label-mono mb-1.5">Subject</div>
            <div className="truncate font-mono text-sm text-ink">{result.url}</div>
          </div>

          {result.report_available && result.report_download_url && (
            <Button asChild variant="outline" size="sm" className="group shrink-0">
              <a
                href={reportUrl(result.report_download_url)}
                target="_blank"
                rel="noreferrer noopener"
              >
                <Download className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-y-0.5" />
                Download the PDF report
              </a>
            </Button>
          )}
        </div>

        <div className="mt-7 grid grid-cols-3 gap-5 border-t border-rule pt-6">
          {SEVERITY_ORDER.map((severity, index) => (
            <div key={severity}>
              <motion.div
                className={`mb-2.5 h-[3px] origin-left rounded-full ${SEVERITY_BAR[severity]}`}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={transition(0.6, 0.25 + index * 0.08)}
              />
              <div className="font-display text-3xl font-bold leading-none text-ink">
                <CountUp to={counts[severity]} delay={250 + index * 80} />
              </div>
              <div className="mt-1.5 font-mono text-micro uppercase text-ink-3">{severity}</div>
            </div>
          ))}
        </div>

        <p className="mt-5 text-sm leading-relaxed text-ink-2">
          {total === 0
            ? "Nothing was flagged on this run."
            : `${total} ${total === 1 ? "finding" : "findings"} across ${result.pages_crawled} ${
                result.pages_crawled === 1 ? "page" : "pages"
              }, sorted so the ones costing you most come first.`}
        </p>
      </div>
    </motion.section>
  );
}

function IssueGroup({ severity, issues }: { severity: Severity; issues: Issue[] }) {
  return (
    <section className="pt-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SeverityTag severity={severity} />
        <span className="font-mono text-xs text-ink-3">{SEVERITY_MEANING[severity]}</span>
        <span className="h-px flex-1 bg-rule" aria-hidden="true" />
        <span className="font-mono text-xs text-ink-3">{issues.length}</span>
      </div>

      <motion.ul
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={inViewTall}
        className="space-y-4"
      >
        {issues.map((issue, index) => (
          <IssueCard key={issue.id} issue={issue} stock={stockFor(STOCKS_ISSUES, index)} />
        ))}
      </motion.ul>
    </section>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition(0.5, 0.1)}
      className="card-chart bg-stock-3 px-6 py-10 text-center md:px-10"
    >
      <h2 className="font-display text-d3">{title}</h2>
      <p className="mx-auto mt-3 max-w-[52ch] text-[0.9375rem] leading-relaxed text-ink-2">{body}</p>
    </motion.div>
  );
}
