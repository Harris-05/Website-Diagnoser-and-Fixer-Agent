import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/api";

/**
 * A triage tag. In an emergency department these are physical tags clipped to
 * a patient at the point of triage, and they are the reason this site is
 * otherwise monochrome: color enters the design at exactly the moment the
 * product assigns a severity, and never for decoration.
 */

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

/** What the severity actually means to the person reading it. */
export const SEVERITY_MEANING: Record<Severity, string> = {
  high: "Fix first — this is costing you now",
  medium: "Worth fixing this cycle",
  low: "Tidy up when you have time",
};

const FILL: Record<Severity, string> = {
  high: "bg-critical text-paper-raised",
  medium: "bg-caution text-paper-raised",
  low: "bg-minor text-paper-raised",
};

const OUTLINE: Record<Severity, string> = {
  high: "border-critical/45 text-[hsl(var(--critical-ink))]",
  medium: "border-caution/45 text-[hsl(var(--caution-ink))]",
  low: "border-minor/45 text-[hsl(var(--minor-ink))]",
};

export const SEVERITY_BAR: Record<Severity, string> = {
  high: "bg-critical",
  medium: "bg-caution",
  low: "bg-minor",
};

interface SeverityTagProps {
  severity: Severity;
  variant?: "fill" | "outline";
  className?: string;
}

export function SeverityTag({ severity, variant = "fill", className }: SeverityTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-2 py-[3px] font-mono text-micro font-semibold uppercase",
        variant === "fill" ? FILL[severity] : cn("border bg-transparent", OUTLINE[severity]),
        className,
      )}
    >
      {SEVERITY_LABEL[severity]}
    </span>
  );
}
