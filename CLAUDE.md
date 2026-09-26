# CLAUDE.md

Roketsan Hackathon Aşama 2: üs koruma karar destek agent'ı. Alan dili için `CONTEXT.md`, mimari kararlar için `docs/adr/`, backend ayrıntıları için `backend/CLAUDE.md`.

## Agent skills

### Issue tracker

Issues and specs are local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix), recorded as a `Status:` line. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
