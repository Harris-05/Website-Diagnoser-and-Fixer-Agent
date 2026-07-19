# Site Doctor

<div align="center">

### AI-Powered Website Auditor & Self-Healing Agent

*Analyze • Explain • Fix • Verify*

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20Workflow-1C3C3C?style=for-the-badge)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--5-412991?style=for-the-badge&logo=openai&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Lighthouse](https://img.shields.io/badge/Google-Lighthouse-F44B21?style=for-the-badge&logo=lighthouse&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge)

</div>

---

## Overview

**Site Doctor** is an AI-powered website auditing and repair system that automatically crawls websites, detects SEO, accessibility, and performance issues, generates intelligent fixes, verifies those fixes using Lighthouse, and produces measurable before-and-after improvements.

Unlike traditional website auditing tools that only report problems, Site Doctor acts as an **AI engineer** that proposes safe fixes while keeping a **human in the loop** before any changes are applied.

---

#  Why Site Doctor?

Website optimization often requires hiring SEO agencies or manually inspecting Lighthouse reports.

Site Doctor automates that workflow.

Instead of telling you:

>  "Your website has 27 issues."

It tells you:

>  "I found 27 issues, generated fixes, verified them, and improved your Lighthouse score."

---

#  Use Cases

##  Business Owners

- Improve SEO without hiring an external agency
- Detect accessibility issues automatically
- Improve website performance
- Receive AI-generated fixes in plain English
- Apply fixes with one approval

---

##  Development Teams

- Test websites before deployment
- Integrate into CI/CD pipelines
- Detect regressions automatically
- Verify Lighthouse improvements after every release
- Ensure accessibility compliance

---

##  Students & Researchers

- Learn Agentic AI workflows
- Explore LangGraph orchestration
- Study automated software repair
- Experiment with AI-assisted code modifications

---

#  How It Works

```
Website URL
      │
      ▼
🌐 Crawl Website
(Playwright)
      │
      ▼
📊 Lighthouse Audit
      │
      ▼
🤖 AI Triage
(Rank & Explain Issues)
      │
      ▼
📋 Report
      │
      ▼
🛠 AI Fix Generation
      │
      ▼
👤 Human Approval
      │
      ▼
✏ Apply Patch
(Local Copy)
      │
      ▼
🔄 Re-Audit
      │
      ▼
✅ Final Report
```

---

#  Agent Architecture

Site Doctor consists of several specialized AI agents working together.

##  Crawl Agent

**Responsibilities**

- Visit website
- Render JavaScript
- Extract HTML
- Save local copy
- Capture metadata

---

##  Audit Agent

Uses **Google Lighthouse** to inspect

- SEO
- Accessibility
- Performance

Returns structured issue reports.

---

##  Triage Agent (GPT)

Responsible for

- Ranking issue severity
- Explaining issues in plain English
- Prioritizing fixes
- Creating developer-friendly reports

---

##  Fix Agent (GPT)

Responsible for generating fixes for issues such as

- Missing titles
- Meta descriptions
- Image alt text
- Heading hierarchy
- Canonical tags
- Structured data
- Accessibility improvements

---

##  Human Review Agent

Before modifying anything,

the system displays

- HTML diff
- Explanation
- Expected improvement

The user can

- ✅ Approve
- ❌ Reject

every proposed fix.

---

##  Verification Agent

Re-runs Lighthouse after every applied fix.

If the issue still exists,

the workflow retries until

- Issue resolved
- Maximum retries reached

This ensures fixes are **measurable**, not merely generated.

---

# ⚙ Tech Stack

| Layer | Technology |
|---------|------------|
| Language | Python |
| Agent Framework | LangGraph |
| LLM | OpenAI GPT |
| Browser Automation | Playwright |
| Website Audit | Google Lighthouse |
| Backend | FastAPI |
| Frontend | Streamlit |
| State Management | Pydantic |
| Image Processing | Pillow |

---

#  Project Workflow

```
URL
 │
 ▼
Crawler
 │
 ▼
Audit
 │
 ▼
Issue List
 │
 ▼
AI Analysis
 │
 ▼
Generate Fix
 │
 ▼
Human Approval
 │
 ▼
Apply Fix
 │
 ▼
Re-Audit
 │
 ▼
Final Report
```

---

#  Planned Features

- Website crawling
- AI issue explanation
- SEO optimization
- Accessibility improvements
- Performance optimization
- Automatic HTML patch generation
- Human-in-the-loop approval
- Lighthouse verification
- Before/After score comparison
- Structured reports
- Multi-page crawling (v2)
- WordPress integration (v2)
- CI/CD integration (v2)

---

# Expected Output

```
SEO Score

Before: 72

After: 96

Accessibility

Before: 81

After: 98

Performance

Before: 74

After: 89

Issues Found:
18

Automatically Fixed:
15

Verified:
15

Rejected:
2

Manual Fix Required:
1
```

---

#  What Makes Site Doctor Different?

Most AI website tools stop after identifying problems.

Site Doctor goes further.

- ✅ Detects issues
- ✅ Explains them
- ✅ Generates fixes
- ✅ Waits for human approval
- ✅ Applies changes safely
- ✅ Re-runs Lighthouse
- ✅ Confirms the issue is actually resolved

The goal is not just to generate code—but to produce **verified, measurable improvements** to real websites.

---

# Current Status

🚧 Under Active Development

Current milestone:

- [x] Project Architecture
- [ ] Crawl Agent
- [ ] Lighthouse Integration
- [ ] GPT Triage Agent
- [ ] GPT Fix Agent
- [ ] Human Approval Workflow
- [ ] Verification Loop
- [ ] Streamlit Dashboard

---

# Contributing

Contributions, suggestions, and feature requests are always welcome.

If you'd like to improve Site Doctor, feel free to fork the repository and submit a pull request.
