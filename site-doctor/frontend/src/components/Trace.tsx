import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * The signature element.
 *
 * A diagnostic strip — the same trace a monitor prints when it's reading a
 * patient. It appears in the hero as a quiet baseline, and returns full-width
 * and lit up in the pipeline section, where it becomes the spine the four
 * audit stages hang off. Nothing else on the site moves like this.
 *
 * The path is generated rather than hand-drawn so the same motif can be tiled
 * at any width and calmed down (`amplitude`) wherever it would shout.
 */

const BEAT_WIDTH = 120;

/** One cardiac complex: baseline, P wave, QRS spike, baseline, T wave. */
function beat(x: number, baseline: number, amplitude: number): string {
  const a = amplitude;
  return [
    `L ${x + 26} ${baseline}`,
    `Q ${x + 32} ${baseline - a * 0.18} ${x + 38} ${baseline}`,
    `L ${x + 48} ${baseline}`,
    `L ${x + 52} ${baseline + a * 0.13}`,
    `L ${x + 58} ${baseline - a}`,
    `L ${x + 64} ${baseline + a * 0.42}`,
    `L ${x + 68} ${baseline}`,
    `L ${x + 80} ${baseline}`,
    `Q ${x + 90} ${baseline - a * 0.3} ${x + 100} ${baseline}`,
    `L ${x + BEAT_WIDTH} ${baseline}`,
  ].join(" ");
}

export function buildTracePath(beats: number, baseline: number, amplitude: number): string {
  let d = `M 0 ${baseline}`;
  for (let i = 0; i < beats; i += 1) {
    // Vary amplitude slightly so it reads as a recording, not a loop.
    const jitter = [1, 0.82, 1.1, 0.9, 1.04][i % 5];
    d += " " + beat(i * BEAT_WIDTH, baseline, amplitude * jitter);
  }
  return d;
}

interface TraceProps {
  beats?: number;
  amplitude?: number;
  height?: number;
  strokeWidth?: number;
  className?: string;
  /** Play the draw when it scrolls into view rather than on mount. */
  onScroll?: boolean;
  duration?: number;
  delay?: number;
  /** Pulsing marker parked at the end of the strip, like a live cursor. */
  showCursor?: boolean;
}

export function Trace({
  beats = 5,
  amplitude = 30,
  height = 80,
  strokeWidth = 1.75,
  className,
  onScroll = false,
  duration = 2.4,
  delay = 0,
  showCursor = false,
}: TraceProps) {
  const reduce = useReducedMotion() ?? false;
  const width = beats * BEAT_WIDTH;
  const baseline = height / 2;
  const d = buildTracePath(beats, baseline, amplitude);

  const animation = reduce
    ? { pathLength: 1, opacity: 1 }
    : { pathLength: 1, opacity: 1, transition: { duration, delay, ease: "easeInOut" as const } };

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("w-full", className)}
      style={{ height }}
      aria-hidden="true"
      focusable="false"
    >
      <motion.path
        d={d}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        initial={{ pathLength: 0, opacity: 0.2 }}
        {...(onScroll
          ? { whileInView: animation, viewport: { once: true, amount: 0.4 } }
          : { animate: animation })}
      />
      {showCursor && (
        <circle
          cx={width - 2}
          cy={baseline}
          r={3.5}
          fill="currentColor"
          className="animate-blip"
          style={{ transformOrigin: `${width - 2}px ${baseline}px` }}
        />
      )}
    </svg>
  );
}
