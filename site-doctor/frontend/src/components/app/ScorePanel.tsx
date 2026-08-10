import { motion, useReducedMotion } from "motion/react";
import { CountUp } from "@/components/CountUp";
import { containerVariants, itemVariants, inView, EASE } from "@/lib/motion";
import type { Category } from "@/lib/api";

const CATEGORY_LABEL: Record<Category, string> = {
  seo: "SEO",
  accessibility: "Accessibility",
  performance: "Performance",
  security: "Security",
  ux: "UX",
};

const ORDER: Category[] = ["performance", "accessibility", "seo", "security", "ux"];

/**
 * Lighthouse's own banding: below 50 is failing, 50–89 needs work, 90 and up
 * is fine. That is a severity judgement, which is why the dials are allowed
 * to use the triage colors — they mean the same thing here as on a tag.
 */
function band(score: number): { stroke: string; text: string } {
  if (score < 50) return { stroke: "hsl(var(--critical))", text: "text-[hsl(var(--critical-ink))]" };
  if (score < 90) return { stroke: "hsl(var(--caution))", text: "text-[hsl(var(--caution-ink))]" };
  return { stroke: "hsl(var(--minor))", text: "text-[hsl(var(--minor-ink))]" };
}

interface ScorePanelProps {
  scores: Partial<Record<Category, number>>;
  pageCount: number;
}

export function ScorePanel({ scores, pageCount }: ScorePanelProps) {
  const entries = ORDER.filter((category) => typeof scores[category] === "number").map(
    (category) => [category, scores[category] as number] as const,
  );

  if (entries.length === 0) return null;

  return (
    <section className="card-chart overflow-hidden bg-stock-5">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-5 py-3 md:px-7">
        <h2 className="label-mono">Scores</h2>
        <span className="font-mono text-micro uppercase text-ink-3">
          Averaged across {pageCount} {pageCount === 1 ? "page" : "pages"}
        </span>
      </div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={inView}
        className="grid grid-cols-2 gap-6 px-5 py-7 sm:grid-cols-3 md:px-7 lg:grid-cols-5"
      >
        {entries.map(([category, score]) => (
          <motion.div key={category} variants={itemVariants} className="flex flex-col items-center">
            <ScoreDial score={score} />
            <div className="mt-3 text-center font-mono text-micro uppercase text-ink-3">
              {CATEGORY_LABEL[category]}
            </div>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}

function ScoreDial({ score }: { score: number }) {
  const reduce = useReducedMotion() ?? false;
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const { stroke, text } = band(clamped);

  return (
    <div className="relative grid h-[86px] w-[86px] place-items-center">
      <svg viewBox="0 0 80 80" className="absolute inset-0 h-full w-full -rotate-90">
        <circle
          cx="40"
          cy="40"
          r="34"
          fill="none"
          stroke="hsl(var(--rule))"
          strokeWidth="5"
        />
        <motion.circle
          cx="40"
          cy="40"
          r="34"
          fill="none"
          stroke={stroke}
          strokeWidth="5"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          whileInView={{ pathLength: clamped / 100 }}
          viewport={{ once: true, amount: 0.6 }}
          transition={reduce ? { duration: 0 } : { duration: 1.1, ease: EASE }}
        />
      </svg>
      <span className={`relative font-display text-2xl font-bold leading-none ${text}`}>
        <CountUp to={clamped} duration={1100} />
      </span>
    </div>
  );
}
