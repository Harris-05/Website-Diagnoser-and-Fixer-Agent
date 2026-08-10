import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { BrandMark } from "@/components/BrandMark";
import { Trace } from "@/components/Trace";

const LINKS = [
  { to: "/#who", label: "Who it's for" },
  { to: "/#how", label: "How it works" },
  { to: "/#checks", label: "What it checks" },
  { to: "/app", label: "Run an audit" },
];

/**
 * Ink, like the header — the two of them bracket the chart paper the way a
 * machine holds the strip it's printing. The footer also closes the trace
 * that opens in the hero: it draws itself once, from the left, and ends.
 */
export function Footer() {
  return (
    <footer className="relative overflow-hidden bg-ink text-paper">
      {/* Faint screen grid, matching the pipeline band so all the dark
          surfaces on the site share one texture. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.045]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #F0F2EF 1px, transparent 1px), linear-gradient(to bottom, #F0F2EF 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
        aria-hidden="true"
      />

      {/* End of the strip. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 text-paper opacity-[0.16]">
        <Trace beats={8} amplitude={28} height={96} strokeWidth={1.5} onScroll duration={3} />
      </div>

      <div className="container relative py-14 md:py-16">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-col justify-between gap-10 sm:flex-row sm:items-end"
        >
          <div>
            <BrandMark inverse />
            <p className="mt-4 max-w-[42ch] text-[0.9375rem] leading-relaxed text-paper/60">
              Crawls a site, audits every page it reaches, and ranks what it finds by how much it's
              costing you. It proposes fixes and applies none of them without you.
            </p>
          </div>

          <nav className="flex flex-col gap-1" aria-label="Footer">
            {LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="group inline-flex items-center gap-1.5 py-1 font-display text-sm font-medium text-paper/65 transition-colors hover:text-paper"
              >
                {link.label}
                <ArrowUpRight
                  className="h-3.5 w-3.5 opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100"
                  aria-hidden="true"
                />
              </Link>
            ))}
          </nav>
        </motion.div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-paper/15 pt-6">
          <p className="font-mono text-micro uppercase text-paper/55">
            Crawl · Audit · Triage · Suggested fix
          </p>
          <p className="font-mono text-micro uppercase text-paper/55">
            Passive checks only · Nothing is changed on your server
          </p>
        </div>
      </div>
    </footer>
  );
}
