/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1.25rem", sm: "2rem", lg: "2.5rem" },
      screens: { "2xl": "1200px" },
    },
    extend: {
      colors: {
        // --- Chart stock ---------------------------------------------
        paper: {
          DEFAULT: "hsl(var(--paper))", // the page itself
          raised: "hsl(var(--paper-raised))", // cards lifted off the page
          sunk: "hsl(var(--paper-sunk))", // inset wells, inputs
        },
        // Card stocks — see the note in index.css. Use via `bg-stock-2` etc.
        // on a `.card-chart`; the utility layer wins over the component class.
        stock: {
          1: "hsl(var(--stock-1))",
          2: "hsl(var(--stock-2))",
          3: "hsl(var(--stock-3))",
          4: "hsl(var(--stock-4))",
          5: "hsl(var(--stock-5))",
        },
        // --- Ink ------------------------------------------------------
        ink: {
          DEFAULT: "hsl(var(--ink))", // headlines, primary text
          2: "hsl(var(--ink-2))", // body prose
          3: "hsl(var(--ink-3))", // mono labels, captions
        },
        rule: "hsl(var(--rule))", // hairlines, borders
        // --- Triage tags ---------------------------------------------
        // The ONLY saturated colors in the system. They mean severity and
        // nothing else, which is why they are never used decoratively.
        critical: "hsl(var(--critical))",
        caution: "hsl(var(--caution))",
        minor: "hsl(var(--minor))",
        // shadcn/ui compatibility aliases
        border: "hsl(var(--rule))",
        input: "hsl(var(--rule))",
        ring: "hsl(var(--ink))",
        background: "hsl(var(--paper))",
        foreground: "hsl(var(--ink))",
        primary: {
          DEFAULT: "hsl(var(--ink))",
          foreground: "hsl(var(--paper-raised))",
        },
        secondary: {
          DEFAULT: "hsl(var(--paper-sunk))",
          foreground: "hsl(var(--ink))",
        },
        muted: {
          DEFAULT: "hsl(var(--paper-sunk))",
          foreground: "hsl(var(--ink-3))",
        },
        destructive: {
          DEFAULT: "hsl(var(--critical))",
          foreground: "hsl(var(--paper-raised))",
        },
      },
      fontFamily: {
        // Display: an industrial grotesque, used tight and heavy.
        display: ["Archivo", "ui-sans-serif", "system-ui", "sans-serif"],
        // Body: a journal serif — this is a clinical report, and it reads like one.
        body: ["'Source Serif 4'", "Georgia", "ui-serif", "serif"],
        // Utility: instrument labels, URLs, scores, severity tags.
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        // Mono eyebrows / instrument labels
        label: ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.14em" }],
        micro: ["0.625rem", { lineHeight: "0.875rem", letterSpacing: "0.16em" }],
        // Display scale
        d1: ["clamp(2.75rem, 7vw, 5.25rem)", { lineHeight: "0.94", letterSpacing: "-0.035em" }],
        d2: ["clamp(2rem, 4.4vw, 3.25rem)", { lineHeight: "1.02", letterSpacing: "-0.028em" }],
        d3: ["clamp(1.375rem, 2.2vw, 1.75rem)", { lineHeight: "1.15", letterSpacing: "-0.018em" }],
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
      boxShadow: {
        chart: "0 1px 0 0 hsl(var(--rule)), 0 12px 32px -24px hsl(var(--ink) / 0.5)",
        lift: "0 1px 0 0 hsl(var(--rule)), 0 20px 44px -28px hsl(var(--ink) / 0.55)",
      },
      keyframes: {
        // The indeterminate scan used while an audit is in flight. It
        // reports "something is happening", never a fake percentage.
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        blip: {
          "0%, 100%": { opacity: "0.35", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.35)" },
        },
        "collapsible-down": {
          from: { height: "0" },
          to: { height: "var(--radix-collapsible-content-height)" },
        },
        "collapsible-up": {
          from: { height: "var(--radix-collapsible-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        sweep: "sweep 1.6s cubic-bezier(0.4, 0, 0.2, 1) infinite",
        blip: "blip 1.4s ease-in-out infinite",
        "collapsible-down": "collapsible-down 220ms cubic-bezier(0.2, 0, 0, 1)",
        "collapsible-up": "collapsible-up 180ms cubic-bezier(0.2, 0, 0, 1)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
