import { useRef } from "react";
import { motion } from "motion/react";
import { Gauge, Eye, ShieldCheck, type LucideIcon } from "lucide-react";
import { SectionHeading } from "@/components/SectionHeading";
import { cn } from "@/lib/utils";
import { STOCKS_CHECKS } from "@/lib/stock";
import {
  containerVariantsSlow,
  revealVariants,
  inViewTall,
  transition,
  useParallax,
} from "@/lib/motion";

interface Check {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  lede: string;
  items: string[];
  /** The honest limit of this check — stated, not buried. */
  bound: string;
}

const CHECKS: Check[] = [
  {
    icon: Gauge,
    eyebrow: "Mechanical",
    title: "SEO, accessibility and performance",
    lede: "Google Lighthouse runs against every page the crawler reached, and you get a score per category plus the individual audits that failed.",
    items: [
      "Missing or duplicate titles and meta descriptions",
      "Heading order and document structure",
      "Images with no alternative text",
      "Link text a screen reader can't use",
      "Colour contrast below the readable threshold",
      "Render-blocking resources and layout shift",
    ],
    bound: "Every one of these has a real pass/fail check behind it.",
  },
  {
    icon: Eye,
    eyebrow: "Judgement",
    title: "How the page actually reads",
    lede: "A vision model looks at full-page screenshots the way a first-time visitor does, and reports what makes the page hard to use.",
    items: [
      "Visual clutter competing for the same attention",
      "Hierarchy that doesn't match what matters",
      "Several calls to action fighting each other",
      "Trust signals missing where a decision happens",
    ],
    bound:
      "These are opinions, not measurements — so they arrive as suggestions and are never applied for you.",
  },
  {
    icon: ShieldCheck,
    eyebrow: "Passive, opt-in",
    title: "Security posture",
    lede: "Off by default. Turn it on and confirm it, and Site Doctor reads what your server already tells every visitor.",
    items: [
      "HSTS, Content-Security-Policy, X-Frame-Options",
      "X-Content-Type-Options and referrer policy",
      "TLS certificate validity and days to expiry",
    ],
    bound:
      "No scanning, no probing, no payloads — nothing your server wasn't already going to send to anyone who loaded the page.",
  },
];

/** Outer columns lead here, so this row drifts differently from the one in
 *  "Who it's for" rather than repeating the same gesture down the page. */
const DRIFT = [30, 16, 26];

export function WhatItChecks() {
  const gridRef = useRef<HTMLDivElement>(null);

  return (
    <section id="checks" className="scroll-mt-24 border-t border-rule py-20 md:py-28">
      <div className="container">
        <SectionHeading
          eyebrow="What it checks"
          title="Three kinds of problem, kept apart on purpose."
          lede="Some findings are facts, some are opinions, and one set needs your permission before it runs. Mixing them together is how audit tools end up untrustworthy, so this one keeps them labelled."
        />

        <motion.div
          ref={gridRef}
          variants={containerVariantsSlow}
          initial="hidden"
          whileInView="visible"
          viewport={inViewTall}
          className="mt-14 grid gap-5 lg:grid-cols-3"
          style={{ perspective: 1400 }}
        >
          {CHECKS.map((check, index) => (
            <CheckCard
              key={check.title}
              check={check}
              stock={STOCKS_CHECKS[index]}
              drift={DRIFT[index]}
              gridRef={gridRef}
            />
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function CheckCard({
  check,
  stock,
  drift,
  gridRef,
}: {
  check: Check;
  stock: string;
  drift: number;
  gridRef: React.RefObject<HTMLDivElement>;
}) {
  const Icon = check.icon;
  const y = useParallax(gridRef, drift);

  return (
    <motion.div variants={revealVariants} style={{ y }} className="group h-full">
      <article
        className={cn(
          "card-chart flex h-full flex-col p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lift",
          stock,
        )}
      >
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-md border border-rule bg-paper-sunk text-ink transition-colors duration-300 group-hover:border-ink group-hover:bg-ink group-hover:text-paper">
            <Icon className="h-[17px] w-[17px]" strokeWidth={1.75} />
          </span>
          <span className="label-mono">{check.eyebrow}</span>
        </div>

        <h3 className="mt-5 font-display text-xl font-bold leading-snug tracking-tight text-ink">
          {check.title}
        </h3>
        <p className="mt-3 text-[0.9375rem] leading-relaxed text-ink-2">{check.lede}</p>

        {/* The list wipes in item by item once the card itself has landed —
            the card arrives, then it fills. */}
        <motion.ul
          className="mt-5 space-y-2 border-t border-rule pt-5"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.055, delayChildren: 0.28 } },
          }}
        >
          {check.items.map((item) => (
            <motion.li
              key={item}
              variants={{
                hidden: { opacity: 0, x: -10 },
                visible: { opacity: 1, x: 0, transition: transition(0.5) },
              }}
              className="flex gap-2.5 font-mono text-xs leading-relaxed text-ink-2"
            >
              <span className="mt-[7px] h-px w-2.5 shrink-0 bg-ink-3" aria-hidden="true" />
              {item}
            </motion.li>
          ))}
        </motion.ul>

        <p className="mt-auto pt-5 text-xs italic leading-relaxed text-ink-3">{check.bound}</p>
      </article>
    </motion.div>
  );
}
