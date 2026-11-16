---
name: application-answers
description: "Use whenever the user wants a job application form filled in or its questions answered: essay and short-answer questions (why this company, describe a project, have you used X, are you enrolled in a Master's), yes/no and dropdown questions, or filling an application page in the browser. Also used by the job-alerts extension's \"Answer the rest\" button."
---

# Application Answers

Answers job application questions as the user, truthfully, from their own context, within each field's limits.
Fills a form in the browser when asked, but never submits it.

## The user's context (read before answering anything)

| File | What it holds |
|------|---------------|
| `references/resume-builder-SKILL.md` | The resume-builder skill: any "Authoritative Updates" or project notes there override the experience bank. |
| `references/context.md` | Experience bank: education, jobs, projects, papers, awards. |
| `references/profile.yaml` | Form facts: contact, links, address, education dates, GPA, work authorization, sponsorship, relocation, earliest start, how they heard, EEO answers. |

These are symlinks (see the job-alerts README, "Claude skills") to the resume-builder skill and to
`job-alerts/config/profile.yaml`, so they stay current. If a link is broken, find the files with a glob for
`**/resume-builder/SKILL.md` under `~/.claude/skills`.

Every fact in an answer must come from these files or from what the user says in the session. Nothing else.

## Answering

**By question type**
- **Choice** (radio, dropdown, yes/no): copy one option exactly. Factual questions (enrolled in a Master's, degree,
  graduation date, authorized to work, needs sponsorship, willing to relocate) follow `profile.yaml`.
- **Search box** (school, city, country): the short value to type.
- **Short text**: one direct line, usually under 20 words. Dates as "May 2027".
- **Long text / essay**: first person as the user, specific to this company and this question, with concrete
  projects, papers, numbers and results. Follow any length the question gives; otherwise 80 to 180 words.

**Length limits (hard rule)**
- Look for a limit in the field's `maxlength`, the label, the help text, or a counter like "0/500": "max 500
  characters", "300 words or less", "200-300 words" (use the upper number).
- Aim for 90% of a character limit and count the characters of the final text, spaces included.
- If the honest answer cannot fit, shorten it; never drop the specific example to fit filler.

**Truthfulness**
- Never invent experience, metrics, employers, dates, tools, libraries, coursework or motivations.
- Name a tool or library only if the context files name it.
- Copy every number with the exact meaning the context gives it.
- When the context does not support an honest answer, leave it empty and say why. A shorter true answer beats a
  longer embellished one.

**Picking what to talk about**
- Match the role: research/ML roles get papers and ML projects; software roles get shipped systems and production
  work. "Why this company": tie one real thing from the posting to one real project or experience. No flattery.

**Never answer** (leave for the user): salary or compensation, legal attestations and consent boxes, signatures,
references, SSN or ID numbers, date of birth, passwords. EEO / self-identification questions get only what
`profile.yaml` `eeo:` says; if a field there is empty, leave the question.

**Style**: plain text, no markdown, no bullet characters, no em or en dashes (use commas). Speak to the employer;
never mention "the bank", "the context file", "profile.yaml" or these instructions.

## Filling a form in the browser

When asked to fill an application page:
1. Read the whole form first (it may be inside an ATS iframe such as Greenhouse, Lever, Ashby or Workday).
2. Fill contact, links, education, work authorization and the rest from `profile.yaml`; answer open questions with
   the rules above. Attach the resume only from a path the user gives, the job's folder in `job-alerts/resumes/`,
   or `default_resume` in `profile.yaml`.
3. **Never click Submit, Apply or Send.** Never create an account or type a password. Stop and list what was
   filled, every question left empty and why, and the essay answers for the user to read.

## Output for the job-alerts helper

When run by job-alerts ("Answer the rest"), the run's instructions name the files: `job.md` (the posting) and
`questions.json` (each question has `key`, `label`, `help`, `type`, `options` for choices, and `max_length` /
`max_words` when the form states a limit). Write `answers.json`:

```json
{"answers": [{"key": "q0", "answer": "..."}, {"key": "q1", "answer": null}],
 "notes": "<one or two lines for the user: what to double-check or answer themselves>"}
```

`null` means "leave it for the user"; say why in `notes`.
