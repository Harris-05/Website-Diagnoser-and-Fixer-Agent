import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Trace } from "@/components/Trace";
import { CountUp } from "@/components/CountUp";
import { containerVariants, itemVariants, transition } from "@/lib/motion";

/** The findings shown on the specimen chart. Real Lighthouse checks, worded
 *  the way the triage node words them. */
const SPECIMEN = {
  url: "https://example.com",
  counts: { high: 4, medium: 11, low: 23 },
  summary:
    "Your homepage has no meta description, so Google is writing its own preview text for your search result — and it's picking the first sentence it finds.",
};

export function Hero() {
  const reduce = useReducedMotion() ?? false;
  const [typed, setTyped] = useState(reduce ? SPECIMEN.url : "");
  const [readingDone, setReadingDone] = useState(reduce);

  // The URL types itself into the chart header, the way it would if someone
  // were entering it. Purely a page-load moment; it never repeats.
  useEffect(() => {
    if (reduce) return;
    let index = 0;
    const startDelay = window.setTimeout(() => {
      const interval = window.setInterval(() => {
        index += 1;
        setTyped(SPECIMEN.url.slice(0, index));
        if (index >= SPECIMEN.url.length) window.clearInterval(interval);
      }, 42);
    }, 700);
    const done = window.setTimeout(() => setReadingDone(true), 3200);
    return () => {
      window.clearTimeout(startDelay);
      window.clearTimeout(done);
    };
  }, [reduce]);

  return (
    <section className="relative overflow-hidden pb-20 pt-14 md:pb-28 md:pt-20">
      <div className="container">
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-16">
          {/* --- The claim ------------------------------------------------ */}
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="lg:col-span-7"
          >
            <motion.p variants={itemVariants} className="label-mono">
              Crawl · Audit · Triage · Fix
            </motion.p>

            <motion.h1 variants={itemVariants} className="mt-5 max-w-[15ch] text-d1">
              Find out what's actually wrong with your site.
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="mt-6 max-w-[54ch] text-lg leading-relaxed text-ink-2"
            >
              Site Doctor crawls your pages, runs SEO, accessibility, performance, UX and security
              checks on every one of them, then ranks what it finds by how much it's hurting you —
              and writes the fix in language you can act on.
            </motion.p>

            <motion.div variants={itemVariants} className="mt-9 flex flex-wrap items-center gap-3">
              <Button asChild size="lg" className="group">
                <Link to="/app">
                  Run an audit
                  <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#how">See how it works</a>
              </Button>
            </motion.div>

            <motion.p variants={itemVariants} className="mt-6 font-mono text-xs text-ink-3">
              No sign-up. Point it at a URL and it starts reading.
            </motion.p>
          </motion.div>

          {/* --- The evidence --------------------------------------------- */}
          <motion.div
            initial={{ opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transition(0.8, 0.25)}
            className="lg:col-span-5"
          >
            <SpecimenChart typed={typed} readingDone={readingDone} />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

function SpecimenChart({ typed, readingDone }: { typed: string; readingDone: boolean }) {
  const reduce = useReducedMotion() ?? false;

  return (
    <figure className="card-chart overflow-hidden">
      {/* Chart header — instrument identification. */}
      <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
        <span className="label-mono">Chart 002418</span>
        <span className="flex items-center gap-1.5 font-mono text-micro uppercase text-ink-3">
          <span className="h-1.5 w-1.5 rounded-full bg-minor animate-blip" />
          Reading
        </span>
      </div>

      {/* Subject under examination. */}
      <div className="border-b border-rule px-4 py-3">
        <div className="label-mono mb-1.5">Subject</div>
        <div className="font-mono text-sm text-ink">
          {typed}
          {!reduce && typed.length < 19 && (
            <span className="ml-px inline-block h-[1.05em] w-[1px] translate-y-[0.15em] bg-ink animate-blip" />
          )}
        </div>
      </div>

      {/* The trace. */}
      <div className="bg-paper-sunk px-4 py-5 text-ink">
        <Trace beats={4} amplitude={26} height={64} duration={2.6} delay={0.9} showCursor />
      </div>

      {/* Findings, tagged. This is where color enters the page. */}
      <div className="border-t border-rule px-4 py-4">
        <div className="label-mono mb-3">Findings by severity</div>
        <div className="grid grid-cols-3 gap-3">
          <Tally label="High" count={SPECIMEN.counts.high} bar="bg-critical" start={readingDone} />
          <Tally
            label="Medium"
            count={SPECIMEN.counts.medium}
            bar="bg-caution"
            start={readingDone}
          />
          <Tally label="Low" count={SPECIMEN.counts.low} bar="bg-minor" start={readingDone} />
        </div>
      </div>

      {/* What the product actually gives you back. */}
      <motion.figcaption
        initial={{ opacity: 0 }}
        animate={{ opacity: readingDone ? 1 : 0 }}
        transition={transition(0.7)}
        className="border-t border-rule bg-paper-raised px-4 py-4"
      >
        <div className="label-mono mb-2">Top finding, in plain language</div>
        <p className="text-[0.9375rem] leading-relaxed text-ink-2">{SPECIMEN.summary}</p>
      </motion.figcaption>
    </figure>
  );
}

function Tally({
  label,
  count,
  bar,
  start,
}: {
  label: string;
  count: number;
  bar: string;
  start: boolean;
}) {
  return (
    <div>
      <motion.div
        className={`mb-2 h-[3px] origin-left rounded-full ${bar}`}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: start ? 1 : 0 }}
        transition={transition(0.6, 0.1)}
      />
      <div className="font-display text-2xl font-bold leading-none text-ink">
        <CountUp to={count} start={start} duration={800} />
      </div>
      <div className="mt-1 font-mono text-micro uppercase text-ink-3">{label}</div>
    </div>
  );
}
