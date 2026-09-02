from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from eliapplybot.config import AppConfig
from eliapplybot.profile_io import load_profile, profile_template, save_profile
from eliapplybot.storage import Storage
from eliapplybot.workflow import run_application, scan_application


def main() -> None:
    parser = argparse.ArgumentParser(prog="eliapplybot")
    parser.add_argument("--db", help="SQLite database path. Defaults to ELIAPPLYBOT_DB_PATH.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    new_profile = sub.add_parser(
        "new-profile", help="Write a profile template JSON to edit with your real details."
    )
    new_profile.add_argument("path")

    import_profile = sub.add_parser("import-profile")
    import_profile.add_argument("path")
    import_profile.add_argument("--name", default="default")

    export_profile = sub.add_parser("export-profile")
    export_profile.add_argument("path")
    export_profile.add_argument("--name", default="default")

    add_job = sub.add_parser("add-job")
    add_job.add_argument("url")
    add_job.add_argument("--title")
    add_job.add_argument("--company")

    sub.add_parser("list-jobs")

    set_status = sub.add_parser(
        "set-status", help="Track a job: saved, applied, interviewing, offer, rejected, withdrawn."
    )
    set_status.add_argument("job_id", type=int)
    set_status.add_argument("status")

    show_attempt = sub.add_parser("show-attempt")
    show_attempt.add_argument("id", type=int)

    run = sub.add_parser("run")
    run.add_argument("url")
    run.add_argument("--profile", default="default")
    run.add_argument("--report")
    run.add_argument("--close-browser", action="store_true")
    run.add_argument("--headless", action="store_true")
    run.add_argument(
        "--no-input",
        action="store_true",
        help="Skip the interactive prompts (for testing against local fixture pages).",
    )

    scan = sub.add_parser("scan")
    scan.add_argument("url")
    scan.add_argument("--profile", default="default")
    scan.add_argument("--report")
    scan.add_argument("--headless", action="store_true")
    scan.add_argument("--no-input", action="store_true")

    args = parser.parse_args()
    config = AppConfig.from_env()
    if args.db:
        config = dataclasses.replace(config, db_path=Path(args.db))
    if getattr(args, "headless", False):
        config = dataclasses.replace(config, headless=True)
    storage = Storage(config.db_path)
    storage.init_db()

    try:
        dispatch(args, config, storage)
    except ValidationError as exc:
        print("Error: the profile JSON is invalid:", file=sys.stderr)
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            print(f"  {location}: {error['msg']}", file=sys.stderr)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: the file is not valid JSON ({exc}).") from exc
    except (LookupError, ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"Error: {exc}") from exc


def dispatch(args: argparse.Namespace, config: AppConfig, storage: Storage) -> None:
    if args.command == "init-db":
        print(f"Initialized database at {config.db_path}")
    elif args.command == "new-profile":
        target = Path(args.path)
        if target.exists():
            raise SystemExit(f"Refusing to overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(profile_template(), encoding="utf-8")
        print(f"Wrote profile template to {target}")
        print("Edit it with your real details, then run: eliapplybot import-profile " + str(target))
    elif args.command == "import-profile":
        profile = load_profile(args.path)
        resume = profile.documents.resume_path
        if resume and not Path(resume).exists():
            print(f"Warning: resume_path does not exist on this machine: {resume}")
        cover = profile.documents.cover_letter_path
        if cover and not Path(cover).exists():
            print(f"Warning: cover_letter_path does not exist on this machine: {cover}")
        profile_id = storage.save_profile(profile, name=args.name)
        print(f"Imported profile {args.name!r} as id {profile_id}")
    elif args.command == "export-profile":
        profile = storage.load_profile(args.name)
        save_profile(profile, args.path)
        print(f"Exported profile {args.name!r} to {args.path}")
    elif args.command == "add-job":
        job_id = storage.add_job(args.url, title=args.title, company=args.company)
        print(f"Job id {job_id}: {args.url}")
    elif args.command == "list-jobs":
        for job in storage.list_jobs():
            title = f"  ({job.title})" if job.title else ""
            print(f"{job.id}\t{job.status}\t{job.url}{title}")
    elif args.command == "set-status":
        storage.update_job_status(args.job_id, args.status)
        print(f"Job {args.job_id} status set to {args.status}")
    elif args.command == "show-attempt":
        data = storage.show_attempt(args.id)
        print(json.dumps(data, indent=2))
    elif args.command == "run":
        run_application(
            args.url,
            config=config,
            storage=storage,
            profile_name=args.profile,
            keep_browser_open=not args.close_browser,
            report_path=args.report,
            interactive=not args.no_input,
        )
    elif args.command == "scan":
        scan_application(
            args.url,
            config=config,
            storage=storage,
            profile_name=args.profile,
            report_path=args.report,
            interactive=not args.no_input,
        )
