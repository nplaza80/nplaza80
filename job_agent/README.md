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
