import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { SiteNav } from "@/components/SiteNav";
import { Footer } from "@/components/Footer";
import { AuditForm } from "@/components/app/AuditForm";
import { RunningState } from "@/components/app/RunningState";
import { ResultsView } from "@/components/app/ResultsView";
import { ErrorState } from "@/components/app/ErrorState";
import { runAudit, type AuditRequest, type AuditResponse } from "@/lib/api";
import { transition } from "@/lib/motion";

type Phase =
  | { status: "idle" }
  | { status: "running"; request: AuditRequest }
  | { status: "done"; result: AuditResponse }
  | { status: "failed"; message: string };

export default function AuditApp() {
  const [phase, setPhase] = useState<Phase>({ status: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function start(request: AuditRequest) {
    setPhase({ status: "running", request });
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result = await runAudit(request, controller.signal);
      setPhase({ status: "done", result });
    } catch (error) {
      if (controller.signal.aborted) return;
      setPhase({
        status: "failed",
        message: error instanceof Error ? error.message : "The audit failed for an unknown reason.",
      });
    }
  }

  return (
    <>
      <SiteNav variant="app" />

      <main className="pb-24 pt-10 md:pt-14">
        <div className="container max-w-4xl">
          <motion.header
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={transition(0.6)}
            className="mb-9"
          >
            <p className="label-mono">Examination room</p>
            <h1 className="mt-3 text-d2">Audit a site.</h1>
            <p className="mt-4 max-w-[58ch] text-lg leading-relaxed text-ink-2">
              Give it an address and choose what to check. It crawls, audits, ranks what it finds by
              severity, and writes a fix for each one — without touching your site.
            </p>
          </motion.header>

          {/* One state visible at a time; each swap is a crossfade so the page
              never jumps while a long run finishes. */}
          <AnimatePresence mode="wait">
            {phase.status === "idle" && (
              <motion.div
                key="form"
                exit={{ opacity: 0, y: -12 }}
                transition={transition(0.3)}
              >
                <AuditForm onSubmit={start} />
              </motion.div>
            )}

            {phase.status === "running" && (
              <motion.div key="running" exit={{ opacity: 0 }} transition={transition(0.3)}>
                <RunningState url={phase.request.url} checks={phase.request.checks} />
              </motion.div>
            )}

            {phase.status === "done" && (
              <motion.div
                key="results"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={transition(0.4)}
              >
                <ResultsView
                  result={phase.result}
                  onReset={() => setPhase({ status: "idle" })}
                />
              </motion.div>
            )}

            {phase.status === "failed" && (
              <motion.div key="failed" exit={{ opacity: 0 }} transition={transition(0.3)}>
                <ErrorState
                  message={phase.message}
                  onRetry={() => setPhase({ status: "idle" })}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      <Footer />
    </>
  );
}
