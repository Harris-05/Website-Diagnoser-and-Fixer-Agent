# Site Doctor — frontend

Vite + React + TypeScript + Tailwind + shadcn/ui + motion + lucide-react.
Two routes: `/` (landing) and `/app` (the tool).

## Running it

The frontend needs the FastAPI backend running alongside it.

```bash
# Terminal 1 — backend, from site-doctor/
uvicorn main:app --reload          # serves on http://127.0.0.1:8000

# Terminal 2 — frontend, from site-doctor/frontend/
npm install
npm run dev                        # serves on http://localhost:5173
```

### How the frontend finds the API

Two options, either works:

1. **Dev proxy (default, no config).** `vite.config.ts` proxies `/api/*` to
   `http://127.0.0.1:8000`. Leave `VITE_API_BASE_URL` unset and everything
   works, same-origin, no CORS involved.
2. **Direct.** Copy `.env.example` to `.env` and set
   `VITE_API_BASE_URL=http://127.0.0.1:8000`. This is cross-origin, which is
   why `main.py` now installs `CORSMiddleware` — see the comment there. The
   allowed origins are listed explicitly rather than `*`, because the API runs
   a real crawler against arbitrary URLs and has no auth in front of it.

### Scripts

| Command           | What it does                              |
| ----------------- | ----------------------------------------- |
| `npm run dev`     | Dev server with HMR                       |
| `npm run build`   | Type-check, then production build to `dist/` |
| `npm run preview` | Serve the production build locally        |
| `npm run lint`    | Type-check only                           |

## Structure

```
src/
  lib/
    api.ts          Typed client — mirrors models/schemas.py exactly
    motion.ts       Shared animation variants and the one easing curve
    utils.ts        cn() class merge
  components/
    ui/             shadcn/ui primitives, restyled to the tokens
    Trace.tsx       The signature diagnostic strip
    SeverityTag.tsx Triage tags + severity colour map
    ...
    landing/        Hero, WhoItsFor, HowItWorks, WhatItChecks, FinalCta
    app/            AuditForm, RunningState, ResultsView, IssueCard, ...
  pages/            Landing.tsx, AuditApp.tsx
```

`lib/api.ts` is the single point of contact with the backend. If a Pydantic
model in `models/schemas.py` changes, change the matching interface there and
TypeScript will point at everything that needs updating.

The `ui/` primitives were hand-written in the shape the shadcn CLI generates
rather than pulled via `npx shadcn add`, so they're yours to edit directly.
`components.json` is present if you'd rather add further components with the
CLI later.

## Design system, in short

The product takes a site's vitals and triages what it finds, so the interface
is printed on **diagnostic chart stock**: pale cool paper with the faint salmon
grid of a real ECG strip, fixed in place so the page slides over it.

- **Type.** Archivo (display) / Source Serif 4 (prose) / IBM Plex Mono
  (every URL, score, and instrument label) — the three voices of a lab report.
- **Colour means severity and nothing else.** The site is monochrome ink-on-paper
  until triage assigns a tag. The three triage colours map to `Severity` in
  `models/schemas.py` and are the only saturated colours in the system. Filled
  tags mean mechanically measured; outlined tags mean judgement call (the vision
  UX review). Lighthouse score dials are allowed the same colours because
  Lighthouse's own <50 / 50–89 / 90+ banding is itself a severity judgement.
- **The signature** is the vitals trace: a quiet baseline in the hero, then a
  full-width scroll-driven strip on the inverted "How it works" band, where each
  pipeline stage acquires as the signal reaches it. Stage 03 (Triage) is where
  colour first appears on the page, because that is the moment severity is
  assigned.

All tokens live in `src/index.css` (`:root`) and `tailwind.config.js`. Change a
value in one place and it propagates.

### Motion

One easing curve for everything (`EASE` in `lib/motion.ts`) — machine parts
settling into place, no bounce. Shared `containerVariants` / `itemVariants` drive
every staggered reveal. `prefers-reduced-motion` is honoured throughout: content
still arrives, it just arrives without travel.

### The waiting state is honest

`POST /audit` runs the whole LangGraph pipeline in one synchronous request and
reports nothing until it finishes, so there is no real progress to show.
`RunningState` shows **elapsed time** — which is true — plus a looping trace,
rather than a progress bar that would be making its numbers up.

## Swapping in your own hero

`Hero2` wasn't in the backend zip, so `components/landing/Hero.tsx` was built to
the pattern it was described as using (nav + hero, staggered
`containerVariants` / `itemVariants`). Those variants now live in
`lib/motion.ts` and are shared by every section. To use the real component,
import it into `pages/Landing.tsx` in place of `<Hero />`.

## Notes

- The security check mirrors the backend's `security_confirmed` field: selecting
  it reveals a confirmation the user must tick on every run, and the form blocks
  submission without it.
- Nothing in this UI applies a fix. `fix_node` is a propose-only step, and the
  results view says so where the user can see it.
