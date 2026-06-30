"""Command-line interface for Octopus LinkedIn.

A thin CLI over the same engine the MCP server uses, for scripting and cron.

    octopus-linkedin authorize
    octopus-linkedin profile
    octopus-linkedin post "Hello, world" --visibility PUBLIC
    octopus-linkedin draft "A post to review later"
    octopus-linkedin drafts --status approved
    octopus-linkedin approve drft_abc123 --note "lgtm"
    octopus-linkedin schedule drft_abc123 2026-07-02T09:00:00Z
    octopus-linkedin publish drft_abc123
    octopus-linkedin publish-due
    octopus-linkedin run-scheduler --interval 60
    octopus-linkedin stats urn:li:share:123
"""

from __future__ import annotations

import argparse
import json
import sys

from linkedin import content, llm, scheduler
from linkedin.auth import authorize
from linkedin.client import LinkedInClient, LinkedInError
from linkedin.content import ContentError
from linkedin.drafts import STATUS_APPROVED, DraftError, DraftStore
from linkedin.llm import LLMError
from linkedin.voice import VoiceProfile


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="octopus-linkedin", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("authorize", help="Run the one-time OAuth flow")
    sub.add_parser("profile", help="Show the authenticated member's identity")

    sp = sub.add_parser("post", help="Publish a text post now")
    sp.add_argument("text")
    sp.add_argument("--visibility", default="PUBLIC")

    sp = sub.add_parser("link", help="Publish a link post now")
    sp.add_argument("text")
    sp.add_argument("url")
    sp.add_argument("--title", default="")
    sp.add_argument("--description", default="")
    sp.add_argument("--visibility", default="PUBLIC")

    sp = sub.add_parser("image", help="Publish image post(s) now")
    sp.add_argument("text")
    sp.add_argument("images", nargs="+", help="One or more local image paths")
    sp.add_argument("--visibility", default="PUBLIC")

    sp = sub.add_parser("draft", help="Save a text draft")
    sp.add_argument("text")
    sp.add_argument("--visibility", default="PUBLIC")

    sp = sub.add_parser("drafts", help="List drafts")
    sp.add_argument("--status", default="")

    sp = sub.add_parser("approve", help="Approve a draft")
    sp.add_argument("draft_id")
    sp.add_argument("--note", default="")

    sp = sub.add_parser("schedule", help="Schedule an approved draft (ISO 8601 UTC)")
    sp.add_argument("draft_id")
    sp.add_argument("when")

    sp = sub.add_parser("publish", help="Publish an approved draft now")
    sp.add_argument("draft_id")

    sub.add_parser("publish-due", help="Publish all approved, due drafts now")

    sp = sub.add_parser("run-scheduler", help="Loop, publishing due drafts")
    sp.add_argument("--interval", type=int, default=60)

    sp = sub.add_parser("stats", help="Show engagement for a post URN")
    sp.add_argument("post_urn")

    sp = sub.add_parser("delete", help="Delete a post by URN")
    sp.add_argument("post_urn")

    # -- content intelligence (LLM) --
    sub.add_parser("llm-info", help="Show the active LLM provider/model")

    sp = sub.add_parser("generate", help="Write a draft from a brief (LLM)")
    sp.add_argument("brief")
    sp.add_argument("--visibility", default="PUBLIC")

    sp = sub.add_parser("polish", help="Polish text for clarity (LLM)")
    sp.add_argument("text")

    sp = sub.add_parser("optimize", help="Optimize text for engagement (LLM)")
    sp.add_argument("text")

    sp = sub.add_parser("ab", help="Generate A/B variants of text (LLM)")
    sp.add_argument("text")
    sp.add_argument("-n", type=int, default=3)

    sp = sub.add_parser("repurpose", help="Turn a URL into a draft (LLM)")
    sp.add_argument("url")
    sp.add_argument("--angle", default="")
    sp.add_argument("--visibility", default="PUBLIC")

    sub.add_parser("voice", help="Show the brand-voice profile")

    sp = sub.add_parser("set-voice", help="Update the brand-voice profile")
    sp.add_argument("--tone", default="")
    sp.add_argument("--audience", default="")
    sp.add_argument("--banned", nargs="*", default=None, help="Banned phrases")

    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = DraftStore()

    voice = VoiceProfile()

    try:
        if args.command == "authorize":
            authorize()
            return 0

        # Content/voice commands need no LinkedIn client.
        cmd = args.command
        if cmd == "llm-info":
            _print(llm.provider_info())
            return 0
        elif cmd == "generate":
            text = content.generate_draft(args.brief, voice)
            _print(store.create(text, visibility=args.visibility))
            return 0
        elif cmd == "polish":
            print(content.polish(args.text, voice))
            return 0
        elif cmd == "optimize":
            print(content.optimize(args.text, voice))
            return 0
        elif cmd == "ab":
            _print(content.ab_variants(args.text, args.n, voice))
            return 0
        elif cmd == "repurpose":
            text = content.repurpose_url(args.url, angle=args.angle, voice=voice)
            _print(store.create(text, visibility=args.visibility))
            return 0
        elif cmd == "voice":
            _print(voice.get())
            return 0
        elif cmd == "set-voice":
            _print(
                voice.set(
                    tone=args.tone or None,
                    audience=args.audience or None,
                    banned_phrases=args.banned,
                )
            )
            return 0

        client = LinkedInClient()

        if cmd == "profile":
            _print(client.get_profile())
        elif cmd == "post":
            _print(client.create_post(args.text, visibility=args.visibility))
        elif cmd == "link":
            _print(
                client.share_link(
                    args.text,
                    args.url,
                    title=args.title or None,
                    description=args.description or None,
                    visibility=args.visibility,
                )
            )
        elif cmd == "image":
            _print(
                client.share_images(args.text, args.images, visibility=args.visibility)
            )
        elif cmd == "draft":
            _print(store.create(args.text, visibility=args.visibility))
        elif cmd == "drafts":
            _print(store.list(status=args.status or None))
        elif cmd == "approve":
            _print(store.approve(args.draft_id, note=args.note or None))
        elif cmd == "schedule":
            _print(store.schedule(args.draft_id, args.when))
        elif cmd == "publish":
            d = store.get(args.draft_id)
            if d["status"] != STATUS_APPROVED:
                print(f"Draft is '{d['status']}', not approved.", file=sys.stderr)
                return 1
            _print(scheduler.publish_one(client, store, d))
        elif cmd == "publish-due":
            _print(scheduler.publish_due(client, store))
        elif cmd == "run-scheduler":
            scheduler.run_loop(args.interval, store)
        elif cmd == "stats":
            _print(client.get_post_stats(args.post_urn))
        elif cmd == "delete":
            _print(client.delete_post(args.post_urn))
        return 0
    except (LinkedInError, DraftError, ContentError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
