import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";
import { SectionHeading } from "@/components/SectionHeading";
import { SeverityTag } from "@/components/SeverityTag";
import { buildTracePath } from "@/components/Trace";
import { transition } from "@/lib/motion";

/**
 * The monitor band.
 *
 * The rest of the site is printed on chart paper; this section is the screen
 * the chart comes off. It inverts to ink, and a single trace is drawn across
 * it by your scroll position — each of the four pipeline stages acquires as
 * the signal reaches it. Stage 03 is where the triage colors appear for the
 * first time on the whole page, because that is the moment the product
 * assigns severity.
 */

interface Stage {
  n: string;
  title: string;
  body: string;
}

const STAGES: Stage[] = [
  {
    n: "01",
    title: "Crawl",
    body: "A headless browser opens your site and walks its internal links breadth-first, saving the HTML and a full-page screenshot of every page it reaches. You set how deep it goes and how many pages it may take.",
  },
  {
    n: "02",
    title: "Audit",
    body: "Three checks run across what was collected: Lighthouse for SEO, accessibility and performance; a vision model reading the screenshots for usability; HTTP security headers and TLS certificate validity, if you asked for those.",
  },
  {
    n: "03",
    title: "Triage",
    body: "Every raw finding is given a severity and rewritten as one plain paragraph explaining what it means for your site — for the person who has to decide whether it's worth anyone's afternoon.",
  },
  {
    n: "04",
    title: "Suggested fix",
    body: "Each triaged issue comes back with a specific, concrete fix rather than a link to documentation. The findings that matter most are checked against current sources, and cite them.",
  },
];

/** Scroll progress at which each stage acquires. */
const THRESHOLDS = [0.1, 0.32, 0.55, 0.78];

const TRACE_BEATS = 4;
const TRACE_HEIGHT = 96;

export function HowItWorks() {
  const reduce = useReducedMotion() ?? false;
  const railRef = useRef<HTMLDivElement>(null);
  const [litCount, setLitCount] = useState(reduce ? STAGES.length : 0);

  const { scrollYProgress } = useScroll({
    target: railRef,
    offset: ["start 0.92", "end 0.62"],
  });

  const pathLength = useTransform(scrollYProgress, [0, 0.88], [0, 1]);
  const railScale = useTransform(scrollYProgress, [0, 0.88], [0, 1]);

  useMotionValueEvent(scrollYProgress, "change", (value) => {
    if (reduce) return;
    const next = THRESHOLDS.filter((threshold) => value >= threshold).length;
    setLitCount((current) => (current === next ? current : next));
  });

  const tracePath = buildTracePath(TRACE_BEATS, TRACE_HEIGHT / 2, 30);

  return (
    <section id="how" className="relative scroll-mt-20 overflow-hidden bg-ink py-20 md:py-28">
      {/* Faint screen grid, so the band reads as a display rather than a
          block of dark background. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.045]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #F0F2EF 1px, transparent 1px), linear-gradient(to bottom, #F0F2EF 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
        aria-hidden="true"
      />

      <div className="container relative">
        <SectionHeading
          inverse
          eyebrow="How it works"
          title="One pass, four stages, one ranked list."
          lede="You give it a URL. It comes back with everything it found, sorted by how much each thing is actually costing you."
        />

        <div ref={railRef} className="mt-16 md:mt-20">
          {/* --- Desktop: the trace runs horizontally through the stages --- */}
          <div className="relative hidden md:block" style={{ height: TRACE_HEIGHT }}>
            <svg
              viewBox={`0 0 ${TRACE_BEATS * 120} ${TRACE_HEIGHT}`}
              preserveAspectRatio="none"
              className="absolute inset-0 h-full w-full text-paper"
              aria-hidden="true"
            >
              {/* Unread portion of the strip, so the line has somewhere to go. */}
              <path
                d={tracePath}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.25}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                opacity={0.14}
              />
              <motion.path
                d={tracePath}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
                style={reduce ? { pathLength: 1 } : { pathLength }}
              />
            </svg>

            <div className="absolute inset-0 grid grid-cols-4">
              {STAGES.map((stage, index) => (
                <div key={stage.n} className="flex items-center justify-center">
                  <StageNode lit={index < litCount} />
                </div>
              ))}
            </div>
          </div>

          {/* --- The stages themselves ------------------------------------
              On mobile there is no room to run the trace sideways, so the
              same signal runs down the left edge of the stack instead. */}
          <div className="relative md:mt-9">
            <div
              className="absolute bottom-3 left-[11px] top-3 w-px bg-paper/15 md:hidden"
              aria-hidden="true"
            />
            <motion.div
              className="absolute bottom-3 left-[11px] top-3 w-px origin-top bg-paper/70 md:hidden"
              style={reduce ? { scaleY: 1 } : { scaleY: railScale }}
              aria-hidden="true"
            />

            <ol className="grid gap-10 md:grid-cols-4 md:gap-6">
              {STAGES.map((stage, index) => (
                <StageCopy key={stage.n} stage={stage} lit={index < litCount} />
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}

function StageNode({ lit }: { lit: boolean }) {
  return (
    <span className="relative grid place-items-center">
      <motion.span
        className="absolute h-8 w-8 rounded-full bg-paper/12"
        initial={false}
        animate={{ scale: lit ? 1 : 0.4, opacity: lit ? 1 : 0 }}
        transition={transition(0.5)}
      />
      <motion.span
        className="relative block rounded-full bg-paper"
        initial={false}
        animate={{
          width: lit ? 11 : 6,
          height: lit ? 11 : 6,
          opacity: lit ? 1 : 0.35,
        }}
        transition={transition(0.45)}
      />
    </span>
  );
}

function StageCopy({ stage, lit }: { stage: Stage; lit: boolean }) {
  const isTriage = stage.n === "03";

  return (
    <motion.li
      className="relative pl-9 md:pl-0"
      initial={false}
      animate={{
        opacity: lit ? 1 : 0.28,
        y: lit ? 0 : 14,
        filter: lit ? "blur(0px)" : "blur(3px)",
      }}
      transition={transition(0.65)}
    >
      {/* Mobile node, sitting on the vertical rail. */}
      <span className="absolute left-0 top-1.5 grid h-[23px] w-[23px] place-items-center md:hidden">
        <motion.span
          className="block rounded-full bg-paper"
          initial={false}
          animate={{ width: lit ? 11 : 6, height: lit ? 11 : 6 }}
          transition={transition(0.45)}
        />
      </span>

      <div className="flex items-baseline gap-2.5">
        <span className="font-mono text-label font-semibold text-paper/60">{stage.n}</span>
        <h3 className="font-display text-lg font-bold tracking-tight text-paper">{stage.title}</h3>
      </div>

      <motion.div
        className="mt-3 h-px origin-left bg-paper"
        initial={false}
        animate={{ scaleX: lit ? 1 : 0, opacity: lit ? 0.45 : 0 }}
        transition={transition(0.6)}
      />

      <p className="mt-3 text-sm leading-relaxed text-paper/65">{stage.body}</p>

      {/* Colour arrives here and nowhere earlier — this is the stage that
          assigns it. */}
      {isTriage && (
        <motion.div
          className="mt-4 flex flex-wrap gap-1.5"
          initial={false}
          animate={{ opacity: lit ? 1 : 0, y: lit ? 0 : 6 }}
          transition={transition(0.5, 0.15)}
        >
          <SeverityTag severity="high" />
          <SeverityTag severity="medium" />
          <SeverityTag severity="low" />
        </motion.div>
      )}
    </motion.li>
  );
}
