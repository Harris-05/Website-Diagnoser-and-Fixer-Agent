import { useId, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronDown, Gauge, Eye, ShieldCheck, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { containerVariants, itemVariants, transition } from "@/lib/motion";
import type { AuditRequest, CheckName } from "@/lib/api";

const CHECK_OPTIONS: {
  name: CheckName;
  label: string;
  icon: typeof Gauge;
  blurb: string;
  /** Unselected tint. Selected always resolves to the lightest stock, so
   *  "chosen" reads as a step up in brightness regardless of which one. */
  stock: string;
}[] = [
  {
    name: "seo",
    label: "SEO",
    icon: Gauge,
    blurb: "Lighthouse: SEO, accessibility, performance",
    stock: "bg-stock-2",
  },
  {
    name: "ux",
    label: "UX",
    icon: Eye,
    blurb: "Vision review of each page screenshot",
    stock: "bg-stock-5",
  },
  {
    name: "security",
    label: "Security",
    icon: ShieldCheck,
    blurb: "Passive headers and TLS only",
    stock: "bg-stock-4",
  },
];

interface AuditFormProps {
  onSubmit: (payload: AuditRequest) => void;
  disabled?: boolean;
}

export function AuditForm({ onSubmit, disabled = false }: AuditFormProps) {
  const urlId = useId();
  const depthId = useId();
  const pagesId = useId();
  const confirmId = useId();

  const [url, setUrl] = useState("");
  const [checks, setChecks] = useState<CheckName[]>(["seo", "ux"]);
  const [securityConfirmed, setSecurityConfirmed] = useState(false);
  const [maxDepth, setMaxDepth] = useState(2);
  const [maxPages, setMaxPages] = useState(10);
  const [generateReport, setGenerateReport] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const securitySelected = checks.includes("security");

  function toggleCheck(name: CheckName) {
    setChecks((current) =>
      current.includes(name) ? current.filter((c) => c !== name) : [...current, name],
    );
    if (name === "security") setSecurityConfirmed(false);
    setError(null);
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const trimmed = url.trim();
    if (!trimmed) {
      setError("Enter the address of the site you want audited.");
      return;
    }
    if (!/^https?:\/\//i.test(trimmed)) {
      setError("The address needs to start with http:// or https://");
      return;
    }
    if (checks.length === 0) {
      setError("Pick at least one check to run.");
      return;
    }
    if (securitySelected && !securityConfirmed) {
      setError("Confirm the security check before running it.");
      return;
    }

    setError(null);
    onSubmit({
      url: trimmed,
      checks,
      max_depth: maxDepth,
      max_pages: maxPages,
      security_confirmed: securityConfirmed,
      generate_report: generateReport,
    });
  }

  return (
    <motion.form
      onSubmit={handleSubmit}
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="card-chart overflow-hidden bg-stock-1"
      noValidate
    >
      {/* Slip header */}
      <motion.div
        variants={itemVariants}
        className="flex items-center justify-between border-b border-rule px-5 py-3 md:px-7"
      >
        <span className="label-mono">New audit</span>
        <Stethoscope className="h-4 w-4 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
      </motion.div>

      <div className="space-y-8 px-5 py-7 md:px-7">
        {/* --- Address ---------------------------------------------------- */}
        <motion.div variants={itemVariants}>
          <Label htmlFor={urlId}>Site address</Label>
          <Input
            id={urlId}
            className="mt-2.5"
            placeholder="https://example.com"
            value={url}
            onChange={(event) => {
              setUrl(event.target.value);
              setError(null);
            }}
            autoComplete="url"
            inputMode="url"
            spellCheck={false}
            disabled={disabled}
          />
          <p className="mt-2 font-mono text-xs text-ink-3">
            The crawler starts here and follows internal links only.
          </p>
        </motion.div>

        {/* --- Checks ----------------------------------------------------- */}
        <motion.fieldset variants={itemVariants}>
          <legend className="label-mono">Checks to run</legend>
          <div className="mt-2.5 grid gap-3 sm:grid-cols-3">
            {CHECK_OPTIONS.map((option) => (
              <CheckToggle
                key={option.name}
                option={option}
                selected={checks.includes(option.name)}
                disabled={disabled}
                onToggle={() => toggleCheck(option.name)}
              />
            ))}
          </div>

          {/* Security has to be confirmed on every run — the backend requires
              it and so does the interface. */}
          <AnimatePresence initial={false}>
            {securitySelected && (
              <motion.div
                key="security-confirm"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={transition(0.35)}
                className="overflow-hidden"
              >
                <div className="mt-3 flex gap-3 rounded-md border border-caution/40 bg-caution/[0.06] p-4">
                  <Checkbox
                    id={confirmId}
                    checked={securityConfirmed}
                    onCheckedChange={(value) => {
                      setSecurityConfirmed(value === true);
                      setError(null);
                    }}
                    disabled={disabled}
                    className="mt-0.5"
                  />
                  <label htmlFor={confirmId} className="cursor-pointer text-sm leading-relaxed">
                    <span className="font-display font-semibold text-ink">
                      I confirm this security check.
                    </span>{" "}
                    <span className="text-ink-2">
                      It reads HTTP security headers and TLS certificate validity — the same
                      information your server sends to every visitor. It sends no payloads and
                      probes nothing.
                    </span>
                  </label>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.fieldset>

        {/* --- Advanced --------------------------------------------------- */}
        <motion.div variants={itemVariants}>
          <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
            <CollapsibleTrigger className="group flex items-center gap-2 font-mono text-label font-medium uppercase tracking-[0.14em] text-ink-3 transition-colors hover:text-ink">
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 transition-transform duration-300",
                  advancedOpen && "rotate-180",
                )}
                aria-hidden="true"
              />
              Crawl limits
            </CollapsibleTrigger>

            <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
              <div className="grid gap-5 pt-5 sm:grid-cols-2">
                <div>
                  <Label htmlFor={depthId}>Link depth</Label>
                  <Input
                    id={depthId}
                    className="mt-2.5"
                    type="number"
                    min={0}
                    max={10}
                    value={maxDepth}
                    onChange={(event) => setMaxDepth(Number(event.target.value))}
                    disabled={disabled}
                  />
                  <p className="mt-2 font-mono text-xs text-ink-3">
                    How many clicks from the start page. 0–10.
                  </p>
                </div>
                <div>
                  <Label htmlFor={pagesId}>Page limit</Label>
                  <Input
                    id={pagesId}
                    className="mt-2.5"
                    type="number"
                    min={1}
                    max={200}
                    value={maxPages}
                    onChange={(event) => setMaxPages(Number(event.target.value))}
                    disabled={disabled}
                  />
                  <p className="mt-2 font-mono text-xs text-ink-3">
                    Stop after this many pages. 1–200.
                  </p>
                </div>
              </div>

              <div className="mt-6 flex items-center justify-between gap-4 rounded-md border border-rule bg-paper-sunk px-4 py-3">
                <div>
                  <div className="font-display text-sm font-semibold text-ink">
                    Generate a PDF report
                  </div>
                  <p className="mt-0.5 font-mono text-xs text-ink-3">
                    Downloadable when the run finishes.
                  </p>
                </div>
                <Switch
                  checked={generateReport}
                  onCheckedChange={setGenerateReport}
                  disabled={disabled}
                  aria-label="Generate a PDF report"
                />
              </div>
            </CollapsibleContent>
          </Collapsible>
        </motion.div>

        {/* --- Submit ----------------------------------------------------- */}
        <motion.div variants={itemVariants} className="flex flex-wrap items-center gap-4 pt-1">
          <Button type="submit" size="lg" disabled={disabled}>
            Run audit
          </Button>
          <p className="font-mono text-xs text-ink-3">
            A ten-page site usually takes a few minutes.
          </p>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.p
              key={error}
              role="alert"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={transition(0.3)}
              className="border-l-2 border-critical pl-3 text-sm text-[hsl(var(--critical-ink))]"
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </motion.form>
  );
}

function CheckToggle({
  option,
  selected,
  disabled,
  onToggle,
}: {
  option: (typeof CHECK_OPTIONS)[number];
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const Icon = option.icon;

  return (
    <button
      type="button"
      role="switch"
      aria-checked={selected}
      onClick={onToggle}
      disabled={disabled}
      className={cn(
        "group relative flex flex-col items-start rounded-md border p-4 text-left transition-all duration-200",
        "disabled:cursor-not-allowed disabled:opacity-50",
        selected
          ? "border-ink bg-paper-raised shadow-chart"
          : cn("border-rule hover:border-ink/35", option.stock),
      )}
    >
      <div className="flex w-full items-center justify-between">
        <Icon
          className={cn(
            "h-[18px] w-[18px] transition-colors",
            selected ? "text-ink" : "text-ink-3",
          )}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <motion.span
          className="grid h-[18px] w-[18px] place-items-center rounded-[3px] bg-ink text-paper"
          initial={false}
          animate={{ scale: selected ? 1 : 0, opacity: selected ? 1 : 0 }}
          transition={transition(0.25)}
        >
          <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
        </motion.span>
      </div>

      <span
        className={cn(
          "mt-3 font-display text-sm font-bold tracking-tight transition-colors",
          selected ? "text-ink" : "text-ink-2",
        )}
      >
        {option.label}
      </span>
      <span className="mt-1 font-mono text-[0.6875rem] leading-relaxed text-ink-3">
        {option.blurb}
      </span>
    </button>
  );
}
