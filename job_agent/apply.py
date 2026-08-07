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
        "url": args.url or "",
        "description": description,
        "status": "new",
        "added_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "draft_resume_path": None,
        "draft_cover_letter_path": None,
    }
    entries.append(entry)
    save_tracker(entries)
    print(f"Added job {entry['id']}: {entry['title']} ({entry['company'] or 'company unknown'})")
    print("Next: python apply.py draft " + entry["id"])


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
        print(f"{e['id']}  [{e['status']:12}]  {e['title']} @ {e.get('company') or '?'}")


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
