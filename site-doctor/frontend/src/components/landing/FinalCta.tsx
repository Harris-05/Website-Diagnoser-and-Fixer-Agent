import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Trace } from "@/components/Trace";
import { containerVariants, itemVariants, inView } from "@/lib/motion";

export function FinalCta() {
  return (
    <section className="border-t border-rule py-20 md:py-28">
      <div className="container">
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={inView}
          className="card-chart relative overflow-hidden bg-stock-3 px-6 py-14 text-center md:px-16 md:py-20"
        >
          {/* The strip runs behind the copy, quietly — the loud version of
              this lives in the monitor band and shouldn't be repeated here. */}
          <div
            className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-ink opacity-[0.07]"
            aria-hidden="true"
          >
            <Trace beats={7} amplitude={40} height={160} strokeWidth={1.5} onScroll duration={2.8} />
          </div>

          <div className="relative">
            <motion.p variants={itemVariants} className="label-mono">
              Start a chart
            </motion.p>

            <motion.h2 variants={itemVariants} className="mx-auto mt-5 max-w-[18ch] text-d2">
              Give it a URL. See what comes back.
            </motion.h2>

            <motion.p
              variants={itemVariants}
              className="mx-auto mt-5 max-w-[52ch] text-lg leading-relaxed text-ink-2"
            >
              One pass over your site, every finding ranked by severity, and a written fix for each
              one. Nothing on your server is touched.
            </motion.p>

            <motion.div variants={itemVariants} className="mt-9">
              <Button asChild size="lg" className="group">
                <Link to="/app">
                  Run an audit
                  <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" />
                </Link>
              </Button>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
