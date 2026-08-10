import { motion } from "motion/react";
import { cn } from "@/lib/utils";
import {
  containerVariants,
  itemVariants,
  ruleVariants,
  wordContainerVariants,
  wordVariants,
  inView,
} from "@/lib/motion";

interface SectionHeadingProps {
  eyebrow: string;
  title: string;
  lede?: string;
  inverse?: boolean;
  className?: string;
}

export function SectionHeading({
  eyebrow,
  title,
  lede,
  inverse = false,
  className,
}: SectionHeadingProps) {
  const words = title.split(" ");

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={inView}
      className={cn("max-w-3xl", className)}
    >
      <motion.p variants={itemVariants} className={cn("label-mono", inverse && "text-paper/65")}>
        {eyebrow}
      </motion.p>

      <motion.div
        variants={ruleVariants}
        className={cn("my-4 h-px origin-left", inverse ? "bg-paper/25" : "bg-rule")}
      />

      {/* The title reads itself into place a word at a time. Each word gets
          its own clipping wrapper so it rises out of the line rather than
          sliding across whatever sits above it. */}
      <motion.h2
        variants={wordContainerVariants}
        className={cn("text-d2", inverse && "text-paper")}
      >
        {words.map((word, index) => (
          <span
            key={`${word}-${index}`}
            className="inline-block overflow-hidden pb-[0.08em] align-bottom"
          >
            <motion.span variants={wordVariants} className="inline-block">
              {word}
              {index < words.length - 1 && "\u00A0"}
            </motion.span>
          </span>
        ))}
      </motion.h2>

      {lede && (
        <motion.p
          variants={itemVariants}
          className={cn(
            "mt-5 max-w-[62ch] text-lg leading-relaxed",
            inverse ? "text-paper/70" : "text-ink-2",
          )}
        >
          {lede}
        </motion.p>
      )}
    </motion.div>
  );
}
