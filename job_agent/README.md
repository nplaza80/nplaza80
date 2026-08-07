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
python apply.py search               # queries every role x location combination
python apply.py search --limit 5     # cap results per query
```

New postings are added to the tracker with status `new`; postings already tracked
(matched by Adzuna's listing id) are skipped so re-running `search` is safe.

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

Valid statuses: `new`, `drafted`, `applied`, `interviewing`, `rejected`, `offer`.

## Notes

- The tool only ever *reads* a job posting URL (a single page fetch) and
  *writes* local draft files — it doesn't log into any job site or click
  anything on your behalf.
- Claude is instructed not to invent experience/skills/metrics that aren't
  in your real resume — always double-check the drafts before sending.
