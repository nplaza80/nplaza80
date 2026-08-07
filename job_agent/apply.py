#!/usr/bin/env python3
"""
Job application drafting assistant.

This tool never submits applications on your behalf. It helps you:
  1. Track job postings you're interested in.
  2. Draft a tailored resume summary + cover letter per posting (via Claude).
  3. Keep a status tracker (new -> drafted -> applied -> interviewing -> ...).

You still review every draft and submit it yourself on the employer's site.
"""
import argparse
import html
import itertools
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
RESUME_PATH = BASE_DIR / "resume.md"
TRACKER_PATH = BASE_DIR / "applications.json"
DRAFTS_DIR = BASE_DIR / "drafts"

VALID_STATUSES = ["new", "drafted", "applied", "interviewing", "rejected", "offer"]


def load_tracker() -> list:
    if not TRACKER_PATH.exists():
        return []
    return json.loads(TRACKER_PATH.read_text())


def save_tracker(entries: list) -> None:
    TRACKER_PATH.write_text(json.dumps(entries, indent=2))


def require_file(path: Path, example_name: str) -> str:
    if not path.exists():
        sys.exit(
            f"Missing {path.name}. Copy {example_name} to {path.name} and fill it in "
            f"(run `python apply.py init` to do this automatically)."
        )
    return path.read_text()


def cmd_init(_args) -> None:
    for target, example in [
        (CONFIG_PATH, BASE_DIR / "config.example.yaml"),
        (RESUME_PATH, BASE_DIR / "resume.example.md"),
    ]:
        if target.exists():
            print(f"{target.name} already exists, skipping.")
            continue
        target.write_text(example.read_text())
        print(f"Created {target.name} from {example.name}. Edit it with your real info.")
    if not TRACKER_PATH.exists():
        save_tracker([])
        print(f"Created empty {TRACKER_PATH.name}.")


def fetch_job_text(url: str) -> tuple[str, str]:
    """Fetch a job posting URL and return (title_guess, plain_text)."""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return title, text[:20000]  # cap to keep prompts reasonable


def cmd_add_job(args) -> None:
    if not args.url and not args.file:
        sys.exit("Provide either --url or --file.")
    entries = load_tracker()
    if args.url:
        print(f"Fetching {args.url} ...")
        title, description = fetch_job_text(args.url)
    else:
        text_path = Path(args.file)
        if not text_path.exists():
            sys.exit(f"No such file: {text_path}")
        description = text_path.read_text()
        title = args.title or text_path.stem

    entry = {
        "id": uuid.uuid4().hex[:8],
        "title": args.title or title,
        "company": args.company or "",
        "location": "",
        "url": args.url or "",
        "description": description,
        "status": "new",
        "source": "manual",
        "source_id": None,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "draft_resume_path": None,
        "draft_cover_letter_path": None,
    }
    entries.append(entry)
    save_tracker(entries)
    print(f"Added job {entry['id']}: {entry['title']} ({entry['company'] or 'company unknown'})")
    print("Next: python apply.py draft " + entry["id"])


def cmd_import(args) -> None:
    import_path = Path(args.file)
    if not import_path.exists():
        sys.exit(f"No such file: {import_path}")
    try:
        raw = json.loads(import_path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid JSON in {import_path}: {exc}")
    if not isinstance(raw, list):
        sys.exit("Import file must contain a JSON array of job objects.")

    source_label = args.source or import_path.stem
    entries = load_tracker()
    existing_keys = {(e.get("source"), e.get("source_id")) for e in entries if e.get("source_id")}
    existing_urls = {e["url"] for e in entries if e.get("url")}

    added = 0
    skipped = 0
    for item in raw:
        if not isinstance(item, dict) or not item.get("title"):
            skipped += 1
            continue
        source = item.get("source", source_label)
        source_id = str(item["source_id"]) if item.get("source_id") is not None else None
        url = item.get("url", "")
        if source_id and (source, source_id) in existing_keys:
            skipped += 1
            continue
        if not source_id and url and url in existing_urls:
            skipped += 1
            continue

        entry = {
            "id": uuid.uuid4().hex[:8],
            "title": item["title"].strip(),
            "company": (item.get("company") or "").strip(),
            "location": (item.get("location") or "").strip(),
            "url": url,
            "description": item.get("description", ""),
            "status": "new",
            "source": source,
            "source_id": source_id,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "draft_resume_path": None,
            "draft_cover_letter_path": None,
        }
        entries.append(entry)
        if source_id:
            existing_keys.add((source, source_id))
        if url:
            existing_urls.add(url)
        added += 1

    save_tracker(entries)
    print(f"Imported {added} new posting(s) from {import_path.name}, skipped {skipped} (invalid or already-tracked).")
    print("Run `python apply.py list` to see them, `python apply.py draft <job_id>` to draft materials.")


ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"


def adzuna_search(country: str, app_id: str, app_key: str, what: str, where: str | None, results: int) -> list:
    import requests

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results,
        "what": what,
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
    resp = requests.get(f"{ADZUNA_BASE_URL}/{country}/search/1", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results", [])


def cmd_search(args) -> None:
    if not CONFIG_PATH.exists():
        sys.exit("Run `python apply.py init` first, then fill in config.yaml.")
    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}

    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        sys.exit(
            "Set ADZUNA_APP_ID and ADZUNA_APP_KEY in your environment.\n"
            "Get free credentials at https://developer.adzuna.com/"
        )

    roles = config.get("target_roles") or []
    locations = config.get("locations") or [None]
    if not roles:
        sys.exit("Add at least one entry to target_roles in config.yaml.")

    adzuna_cfg = config.get("adzuna") or {}
    country = adzuna_cfg.get("country", "us")
    results_per_query = args.limit or adzuna_cfg.get("results_per_search", 10)

    queries = list(itertools.product(roles, locations))
    if len(queries) > 20:
        sys.exit(
            f"{len(queries)} role/location combinations would be queried (roles x locations). "
            "Trim target_roles or locations in config.yaml to 20 or fewer combinations."
        )

    entries = load_tracker()
    existing_ids = {e["source_id"] for e in entries if e.get("source") == "adzuna" and e.get("source_id")}

    added = 0
    skipped = 0
    for role, location in queries:
        where = None if location == "Remote" else location
        print(f"Searching Adzuna: '{role}' in '{location or 'anywhere'}' ...")
        try:
            results = adzuna_search(country, app_id, app_key, role, where, results_per_query)
        except Exception as exc:  # noqa: BLE001 - surface API errors without crashing the whole run
            print(f"  Skipped query due to error: {exc}")
            continue

        for r in results:
            source_id = str(r.get("id"))
            if not source_id or source_id in existing_ids:
                skipped += 1
                continue
            entry = {
                "id": uuid.uuid4().hex[:8],
                "title": html.unescape(r.get("title", "")).strip(),
                "company": html.unescape((r.get("company") or {}).get("display_name", "")).strip(),
                "location": html.unescape((r.get("location") or {}).get("display_name", "")).strip(),
                "url": r.get("redirect_url", ""),
                "description": html.unescape(r.get("description", "")).strip(),
                "status": "new",
                "source": "adzuna",
                "source_id": source_id,
                "added_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "draft_resume_path": None,
                "draft_cover_letter_path": None,
            }
            entries.append(entry)
            existing_ids.add(source_id)
            added += 1

    save_tracker(entries)
    print(f"\nAdded {added} new posting(s), skipped {skipped} already-tracked duplicate(s).")
    print("Run `python apply.py list` to see them, `python apply.py draft <job_id>` to draft materials.")


def build_prompt(config: dict, resume: str, job: dict) -> str:
    return f"""You are helping a job applicant prepare application materials. You are NOT submitting
anything - you are only drafting text for the applicant to review and edit.

CANDIDATE PREFERENCES:
{config.get('preferences', '')}
Tone for cover letter: {config.get('cover_letter_tone', 'professional')}

CANDIDATE RESUME:
---
{resume}
---

JOB POSTING ({job.get('title', 'Unknown role')} at {job.get('company', 'Unknown company')}):
---
{job.get('description', '')[:8000]}
---

Produce two things, clearly separated by the exact markers below:

===RESUME_SUMMARY===
A tailored 3-5 bullet "highlights" section (not a full resume rewrite) that reorders/reframes
the candidate's real, existing experience to match this specific posting. Do not invent
experience, skills, or metrics that aren't in the resume above.

===COVER_LETTER===
A concise cover letter (under 350 words) addressed generically ("Dear Hiring Team," unless a
name is given), referencing specific, real details from both the resume and the job posting.
Do not invent facts.
"""


def cmd_draft(args) -> None:
    entries = load_tracker()
    entry = next((e for e in entries if e["id"] == args.job_id), None)
    if entry is None:
        sys.exit(f"No job with id {args.job_id}. Run `python apply.py list` to see ids.")

    if not CONFIG_PATH.exists() or not RESUME_PATH.exists():
        sys.exit("Run `python apply.py init` first, then fill in config.yaml and resume.md.")

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    resume = RESUME_PATH.read_text()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY in your environment to generate drafts.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_prompt(config, resume, entry)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")

    resume_part, _, cover_part = text.partition("===COVER_LETTER===")
    resume_part = resume_part.replace("===RESUME_SUMMARY===", "").strip()
    cover_part = cover_part.strip()

    DRAFTS_DIR.mkdir(exist_ok=True)
    resume_out = DRAFTS_DIR / f"{entry['id']}_resume_highlights.md"
    cover_out = DRAFTS_DIR / f"{entry['id']}_cover_letter.md"
    resume_out.write_text(resume_part)
    cover_out.write_text(cover_part)

    entry["status"] = "drafted"
    entry["draft_resume_path"] = str(resume_out.relative_to(BASE_DIR))
    entry["draft_cover_letter_path"] = str(cover_out.relative_to(BASE_DIR))
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_tracker(entries)

    print(f"Draft written to:\n  {resume_out}\n  {cover_out}")
    print("Review and edit these before you submit anything yourself.")


def cmd_list(_args) -> None:
    entries = load_tracker()
    if not entries:
        print("No jobs tracked yet. Add one with `python apply.py add-job ...`.")
        return
    for e in entries:
        loc = f" ({e['location']})" if e.get("location") else ""
        print(f"{e['id']}  [{e['status']:12}]  {e['title']} @ {e.get('company') or '?'}{loc}  [{e.get('source', 'manual')}]")


def cmd_update_status(args) -> None:
    if args.status not in VALID_STATUSES:
        sys.exit(f"Status must be one of: {', '.join(VALID_STATUSES)}")
    entries = load_tracker()
    entry = next((e for e in entries if e["id"] == args.job_id), None)
    if entry is None:
        sys.exit(f"No job with id {args.job_id}.")
    entry["status"] = args.status
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_tracker(entries)
    print(f"Updated {args.job_id} -> {args.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create config.yaml and resume.md from templates.").set_defaults(func=cmd_init)

    p_add = sub.add_parser("add-job", help="Track a new job posting.")
    p_add.add_argument("--url", help="URL of the job posting to fetch.")
    p_add.add_argument("--file", help="Path to a text file with the job description.")
    p_add.add_argument("--title", help="Job title (optional if scraped from URL).")
    p_add.add_argument("--company", help="Company name.")
    p_add.set_defaults(func=cmd_add_job)

    p_import = sub.add_parser(
        "import",
        help="Import job postings from a JSON file (e.g. results fetched via an Indeed/LinkedIn tool).",
    )
    p_import.add_argument("file", help="Path to a JSON file containing a list of job objects.")
    p_import.add_argument("--source", help="Label to tag these postings with (defaults to the filename).")
    p_import.set_defaults(func=cmd_import)

    p_search = sub.add_parser(
        "search", help="Query Adzuna for postings matching target_roles/locations in config.yaml and track new ones."
    )
    p_search.add_argument("--limit", type=int, help="Results per role/location query (overrides config.yaml).")
    p_search.set_defaults(func=cmd_search)

    p_draft = sub.add_parser("draft", help="Generate tailored resume highlights + cover letter for a job.")
    p_draft.add_argument("job_id")
    p_draft.set_defaults(func=cmd_draft)

    sub.add_parser("list", help="List tracked jobs and their status.").set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="Update a job's status.")
    p_status.add_argument("job_id")
    p_status.add_argument("status", choices=VALID_STATUSES)
    p_status.set_defaults(func=cmd_update_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
