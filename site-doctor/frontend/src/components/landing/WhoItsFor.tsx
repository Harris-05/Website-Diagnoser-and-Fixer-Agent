import { useRef } from "react";
import { motion } from "motion/react";
import { Store, Users, Terminal, type LucideIcon } from "lucide-react";
import { SectionHeading } from "@/components/SectionHeading";
import { cn } from "@/lib/utils";
import { STOCKS_AUDIENCE } from "@/lib/stock";
import {
  containerVariantsSlow,
  revealVariants,
  inViewTall,
  useParallax,
} from "@/lib/motion";

interface Audience {
  icon: LucideIcon;
  who: string;
  problem: string;
  why: string;
}

const AUDIENCES: Audience[] = [
  {
    icon: Store,
    who: "Business owners",
    problem: "The site looks fine to you.",
    why: "It looks fine because you know where everything is. Site Doctor reads it the way a search engine and a first-time visitor do, and tells you — without jargon — which problems are costing you customers and which ones can wait.",
  },
  {
    icon: Users,
    who: "Dev and QA teams",
    problem: "You audit one URL at a time.",
    why: "Point it at the root and it crawls the site, runs Lighthouse on every page it finds, checks security headers and TLS, and hands back one ranked list instead of thirty separate reports to reconcile.",
  },
  {
    icon: Terminal,
    who: "Solo developers",
    problem: "The redesign shipped on Friday.",
    why: "Run an audit before anyone else finds the broken heading order, the images with no alt text, or the certificate quietly expiring in nine days. Then fix the six things that actually matter.",
  },
];

/** Each column drifts at its own rate on the way past, so the row breathes
 *  instead of travelling as one slab. Middle column leads. */
const DRIFT = [18, 34, 22];

export function WhoItsFor() {
  const gridRef = useRef<HTMLDivElement>(null);

  return (
    <section id="who" className="scroll-mt-24 border-t border-rule py-20 md:py-28">
      <div className="container">
        <SectionHeading
          eyebrow="Who it's for"
          title="Three people keep asking the same question."
          lede="They ask it differently — is my site okay? is this release safe to ship? why is traffic down? — but the answer always starts with an honest inventory of what's broken."
        />

        <motion.div
          ref={gridRef}
          variants={containerVariantsSlow}
          initial="hidden"
          whileInView="visible"
          viewport={inViewTall}
          className="mt-14 grid gap-5 md:grid-cols-3"
          style={{ perspective: 1400 }}
        >
          {AUDIENCES.map((audience, index) => (
            <AudienceCard
              key={audience.who}
              audience={audience}
              stock={STOCKS_AUDIENCE[index]}
              drift={DRIFT[index]}
              gridRef={gridRef}
            />
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function AudienceCard({
  audience,
  stock,
  drift,
  gridRef,
}: {
  audience: Audience;
  stock: string;
  drift: number;
  gridRef: React.RefObject<HTMLDivElement>;
}) {
  const Icon = audience.icon;
  const y = useParallax(gridRef, drift);

  return (
    <motion.div variants={revealVariants} style={{ y }} className="group">
      <div
        className={cn(
          "card-chart flex h-full flex-col p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lift",
          stock,
        )}
      >
        <div className="flex items-center justify-between">
          <span className="grid h-9 w-9 place-items-center rounded-md border border-rule bg-paper-sunk text-ink transition-colors duration-300 group-hover:border-ink group-hover:bg-ink group-hover:text-paper">
            <Icon className="h-[17px] w-[17px]" strokeWidth={1.75} />
          </span>
          {/* The rule extends on hover — the card "acquires" the reader. */}
          <span className="h-px w-8 bg-rule transition-all duration-300 group-hover:w-16 group-hover:bg-ink" />
        </div>

        <h3 className="mt-5 font-display text-xl font-bold tracking-tight text-ink">
          {audience.who}
        </h3>
        <p className="mt-1 font-mono text-xs text-ink-3">{audience.problem}</p>
        <p className="mt-4 text-[0.9375rem] leading-relaxed text-ink-2">{audience.why}</p>
      </div>
    </motion.div>
  );
}
