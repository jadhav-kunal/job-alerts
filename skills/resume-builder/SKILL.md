---
name: "resume-builder"
description: "Use whenever the user wants to create, tailor, optimize, or rewrite a resume for a specific job, internship, or research lab, including partial tasks like rewriting bullets or matching a resume to a job description. Also used by job-alerts' Create resume and Cover letter buttons."
---

# Resume Builder

Tailors the user's one-page LaTeX resume to one job description, truthfully, by selecting and lightly editing
lines they have already written.

## Files this skill needs (fill these in yourself; they are yours, not part of job-alerts)

| File | What it holds |
|------|---------------|
| `references/base-resume.tex` | Your default one-page resume, compiling with `pdflatex`. job-alerts copies it to `resume.tex` for every job. |
| `references/bullet-library.tex` | Every resume line you might use (experience bullets, project blocks, publications, the full skills list), already written and true. More than fits on one page. |
| `references/context.md` | Your experience bank in prose: education, every job, projects, papers, awards, numbers and what they mean. Start from `references/context-template.md`. The cover-letter and application-answer runs read this too. |
| `references/action-verbs.md` | Approved verbs (shipped). |

## Tailor, don't rewrite (the default way to make every resume)

1. Start from a copy of `base-resume.tex` as `resume.tex` (the job-alerts runner has already copied it).
2. Read the job description, `bullet-library.tex` and this file. Read `context.md` only if the JD needs a fact the
   library lacks.
3. Use the Edit tool for each change; never rewrite the whole file:
   - **Projects**: swap in the 1 to 3 library project blocks that best fit the JD.
   - **Experience**: swap library bullets in or out to match the JD, keeping 2 to 4 per role.
   - **Keywords**: in a library bullet, swap up to about 5 words for the JD's own terms when the meaning stays true.
     Numbers, employers and dates never change.
   - **Technical Skills**: reorder by JD relevance; use only skills listed in the library.
4. Compile with `pdflatex -interaction=nonstopmode -halt-on-error resume.tex`, check it is one page with
   `pdfinfo resume.pdf`, and tighten if not. The base is already full: anything added must replace something.
5. Write `changes.md`: blocks swapped, words changed, anything to double-check.

Only if the JD needs something the library cannot express may a new bullet be written (Action verb + task + result,
true metrics only); flag it in `changes.md`.

## Rules

- Never invent experience, metrics, employers, dates, tools or coursework.
- No em dashes or en dashes anywhere.
- No placeholders left in the final file.
- One page, always.
