# Agent instructions (BabelDOC / TopCircle)

## Pre-commit quality gate

**Always run a strict code-quality review (same bar as `/code-review`) before `git commit` and before `git push`.**

- Do not ship “it works” diffs that grow spaghetti, inflate god files without need, or leave dead/fake APIs.
- Prefer fixing review findings in the same change set over “merge then clean up.”
- If the user explicitly asks to push immediately despite open review issues, call that out and still list residual risks.
- One PR / one concern when possible (do not bundle design docs, unrelated hygiene, and quality fixes in one commit unless asked).

## Dual / operator context

- Primary consumer: PDFMathTranslate-next + DeepLX (non-LLM) dual PDFs.
- Prefer dual visual quality and reproducible midend behavior over large refactors.
- Follow `docs/architecture-optimization-plan.md` MVP order when doing roadmap work.
