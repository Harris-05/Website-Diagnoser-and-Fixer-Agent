import { cn } from "@/lib/utils";

interface BrandMarkProps {
  className?: string;
  /** Inverted for use on the dark monitor band. */
  inverse?: boolean;
}

export function BrandMark({ className, inverse = false }: BrandMarkProps) {
  return (
    <span className={cn("group inline-flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "grid h-8 w-8 place-items-center rounded-md transition-transform duration-300 group-hover:-rotate-3",
          inverse ? "bg-paper text-ink" : "bg-ink text-paper",
        )}
        aria-hidden="true"
      >
        <svg viewBox="0 0 32 32" className="h-[18px] w-[18px]">
          <path
            d="M3 17h5l2.5-7 4 13 3-9 2 3h7.5"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.4}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span
        className={cn(
          "font-display text-[0.9375rem] font-bold tracking-tight",
          inverse ? "text-paper" : "text-ink",
        )}
      >
        Site Doctor
      </span>
    </span>
  );
}
