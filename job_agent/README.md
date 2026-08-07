# Job Application Assistant

A small CLI that helps you apply to jobs faster — it drafts a tailored resume
summary and cover letter per posting using Claude, and tracks status. **It
never submits anything on your behalf**: you review every draft and click
"submit" yourself on the employer's site.

Kept deliberately non-autonomous on purpose — most job boards' terms of
service prohibit automated form-filling/submission, and fully-automated
"apply bots" are fragile (logins, CAPTCHAs) and risk submitting mistakes
under your name.

## Setup

```bash
cd job_agent
pip install -r requirements.txt
python apply.py init          # creates config.yaml and resume.md from templates
```

Edit `config.yaml` (target roles, locations, preferences) and `resume.md`
(paste your real resume as plain text/markdown). Both files are gitignored —
your personal info never gets committed to this repo.

`config.yaml` has two kinds of content:
- **Structured fields the code reads directly:** `target_roles` (a flat list, or
  tiers — `primary` / `stretch` / `adjacent`), `locations` (a flat list, or
  `{preferred: [...], country: ...}`), `avoid_roles`, and `adzuna`.
- **Everything else is free-form strategy/voice guidance** (e.g.
  `career_objective`, `candidate_positioning`, `job_fit_scoring`,
  `resume_strategy`, `cover_letter_strategy`, `truthfulness_rules`) that gets
  handed to Claude as context for both screening and drafting. Add, remove, or
  rewrite these sections however you like — see `config.example.yaml` for a
  starting structure.

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Auto-populate postings with Adzuna

Get free API credentials at https://developer.adzuna.com/ and set:

```bash
export ADZUNA_APP_ID=...
export ADZUNA_APP_KEY=...
```

Then, using the `target_roles`, `locations`, and `adzuna` settings in `config.yaml`:

```bash
python apply.py search                     # queries target_roles.primary x locations
python apply.py search --limit 5           # cap results per query
python apply.py search --include-stretch   # also search target_roles.stretch titles
python apply.py search --include-adjacent  # also search target_roles.adjacent titles
```

New postings are added to the tracker with status `new`; postings already tracked
(matched by Adzuna's listing id) are skipped so re-running `search` is safe. Any
posting whose title matches `avoid_roles` is filtered out automatically.

### Importing from Indeed / LinkedIn

Neither Indeed nor LinkedIn offers a public job-search API for individual
developers anymore (Indeed deprecated its Publisher API for new access;
LinkedIn's job APIs are partner-only), and this tool does **not** scrape
either site directly — LinkedIn in particular prohibits automated access in
its ToS and aggressively bans accounts for it.

Instead, `import` ingests job listings from a JSON file, so you can bring in
postings from any legitimate source (e.g. a Claude session with an Indeed
connector enabled, an official employer API, or postings you've manually
collected):

```bash
python apply.py import indeed_import.example.json --source indeed
```

Each file is a JSON array of objects (see `indeed_import.example.json`):

```json
[
  {
    "title": "Backend Engineer",
    "company": "Acme Corp",
    "location": "Remote",
    "url": "https://...",
    "description": "Full job description text...",
    "source": "indeed",
    "source_id": "unique-listing-id"
  }
]
```

`source` + `source_id` are used to dedupe re-imports (falls back to `url` if
`source_id` is omitted), so running `import` again on an updated file is safe.

For an individual LinkedIn posting, just copy its URL and use `add-job --url`
below — that's a single page fetch of a listing you're already choosing to
view, not automated scraping.

### Add a posting manually

Track a job posting (from a URL, or paste the description into a file):

```bash
python apply.py add-job --url "https://example.com/job/123" --company "Acme"
python apply.py add-job --file input/some_posting.txt --title "Backend Engineer" --company "Acme"
```

List tracked jobs:

```bash
python apply.py list
```

### Screen postings for fit

If `config.yaml` has a `job_fit_scoring` section, `screen` asks Claude to score a
posting (0-100) and recommend `PRIORITIZE` / `APPLY` / `MAYBE` / `SKIP`, following
your `job_fit_scoring`, `avoid_roles`, `application_priority`, `education_handling`,
`experience_strategy`, and `truthfulness_rules` guidance:

```bash
python apply.py screen <job_id>
python apply.py screen --all            # screen every job with status 'new'
python apply.py screen --all --force    # re-screen everything, including already-screened jobs
```

Screened jobs move to status `screened` and show their score/recommendation in
`python apply.py list`. This never applies or submits anything — it's purely
triage to help you decide where to spend drafting effort.

### Draft tailored materials

Generate a tailored resume-highlights section + cover letter draft for a job
(writes to `drafts/`):

```bash
python apply.py draft <job_id>
```

Review the drafts, edit as needed, and submit the application yourself.
Then update the tracker:

```bash
python apply.py status <job_id> applied
```

Valid statuses: `new`, `screened`, `drafted`, `applied`, `interviewing`, `rejected`, `offer`.

## Notes

- The tool only ever *reads* a job posting URL (a single page fetch) and
  *writes* local draft files — it doesn't log into any job site or click
  anything on your behalf.
- Claude is instructed not to invent experience/skills/metrics that aren't
  in your real resume — always double-check the drafts before sending.
- `screen` and `draft` both hand your entire `config.yaml` to Claude as context,
  so any `truthfulness_rules` or `application_guardrails` you define there (e.g.
  "never auto-answer salary/demographic/background-check questions without
  review") are guidance for how *you* review drafts — this tool still never
  fills out or submits an application form itself.
