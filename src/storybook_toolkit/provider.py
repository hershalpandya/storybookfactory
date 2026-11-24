# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Choose and set up the image provider for a project: a Gemini API key, or a subscription tool.

`storybook provider status PROJECT` explains what is configured and what to do next.
`storybook provider set-key` stores a Gemini API key in the macOS login Keychain (the key is typed into the
system prompt, never passed on the command line or written to the project).
`storybook provider choose PROJECT gemini-api|subscription [--tool NAME]` records the owner's explicit choice;
the toolkit never switches provider on its own.
"""

import json
import os
import platform
import subprocess
from pathlib import Path

from .store import emit, prose, require

DEFAULT_KEYCHAIN_SERVICE = "Storybook Toolkit Gemini API"
KEYCHAIN_SERVICE_ENV = "STORYBOOK_KEYCHAIN_SERVICE"
KEYCHAIN_ACCOUNT = "storybook"
SECURITY = "/usr/bin/security"   # absolute: never resolve the Keychain tool through PATH
CHOICE_FILE = "provider.json"
SUBSCRIPTION_TOOLS = ("codex", "chatgpt", "other")

GEMINI_STEPS = [
    "1. Open Google AI Studio (aistudio.google.com), sign in, choose 'Get API key' and create a key for a project "
    "with billing enabled. Image generation is billed per image (about USD 0.03-0.05 per output image, plus "
    "input and thinking tokens; the journal records an upper-bound estimate for every call).",
    "2. Store the key: run `storybook provider set-key` and paste the key into the macOS prompt. On Linux or "
    "Windows, set the GEMINI_API_KEY environment variable in your shell profile instead (never in the project).",
    "3. Check it: `storybook provider status PROJECT` shows whether a key is found; "
    "`storybook edition gemini-probe PROJECT SLOT` checks the edition's budget and the key without a paid call.",
]
SUBSCRIPTION_STEPS = [
    "A subscription tool (for example Codex or ChatGPT with built-in image generation) has no API key: your agent "
    "operates the tool in its own interface and saves each returned image.",
    "Every image still goes through the journal: `storybook edition art-round` freezes a small round, "
    "`art-start` records the exact prompt and inputs before each request, `art-capture` saves the returned file "
    "and `art-review` records the frozen checks. Assign passing images with an `assign` revision.",
    "Cost is covered by the subscription and is not tracked in USD; the journal still counts calls and retries.",
]


def keychain_service():
    """The Keychain item name; STORYBOOK_KEYCHAIN_SERVICE keeps a key stored under another name usable."""
    return os.environ.get(KEYCHAIN_SERVICE_ENV, "").strip() or DEFAULT_KEYCHAIN_SERVICE


def keychain_available():
    return platform.system() == "Darwin" and Path(SECURITY).is_file()


def key_sources():
    """Where a Gemini key can be found, without reading the key itself into the report."""
    sources = {"environment": bool(os.environ.get("GEMINI_API_KEY", "").strip()), "keychain": False}
    if keychain_available():
        result = subprocess.run([SECURITY, "find-generic-password", "-s", keychain_service(), "-a", KEYCHAIN_ACCOUNT],
                                capture_output=True, text=True, check=False)
        sources["keychain"] = result.returncode == 0
    return sources


def load_choice(project):
    path = Path(project) / CHOICE_FILE
    return json.loads(path.read_text()) if path.is_file() else None


def status(args):
    choice = load_choice(args.project) if args.project else None
    sources = key_sources()
    report = {"choice": choice, "gemini_key_found": sources}
    if choice is None:
        report["next"] = ("No provider chosen for this project yet. Choose one explicitly: "
                          "`storybook provider choose PROJECT gemini-api` (pay per image with an API key) or "
                          "`storybook provider choose PROJECT subscription --tool codex` (use a subscription tool).")
        report["gemini_api_steps"] = GEMINI_STEPS
        report["subscription_steps"] = SUBSCRIPTION_STEPS
    elif choice["provider"] == "gemini-api":
        report["next"] = ("Ready: a Gemini key was found." if any(sources.values())
                          else "No Gemini key found yet; follow the steps below.")
        if not any(sources.values()):
            report["gemini_api_steps"] = GEMINI_STEPS
    else:
        report["next"] = f"Subscription tool '{choice.get('tool')}': follow the steps below for each image round."
        report["subscription_steps"] = SUBSCRIPTION_STEPS
    emit(report)


def set_key(args):
    require(keychain_available(), "The macOS Keychain is not available here; set GEMINI_API_KEY in your shell "
                                  "profile instead (never inside the project)")
    print("Paste your Gemini API key at the password prompt (it is not shown and not stored in the project).")
    # A trailing -w with no value makes `security` prompt for the secret, so it never appears in argv or history.
    result = subprocess.run([SECURITY, "add-generic-password", "-U", "-s", keychain_service(),
                             "-a", KEYCHAIN_ACCOUNT, "-w"], check=False)
    require(result.returncode == 0, "The Keychain did not store the key")
    print(json.dumps({"stored": True, "service": keychain_service(), "account": KEYCHAIN_ACCOUNT}))


def choose(args):
    require(args.provider in ("gemini-api", "subscription"), "Choose gemini-api or subscription")
    if args.provider == "subscription":
        require(args.tool in SUBSCRIPTION_TOOLS, f"Name the subscription tool: {', '.join(SUBSCRIPTION_TOOLS)}")
    require(prose(args.owner), "Record who chose the provider (the owner's choice)")
    choice = {"provider": args.provider, "tool": args.tool if args.provider == "subscription" else "gemini-nano-banana-2.1",
              "chosen_by": args.owner,
              "rule": "The toolkit never switches provider on its own; a change needs a new owner choice."}
    path = Path(args.project) / CHOICE_FILE
    path.write_text(json.dumps(choice, indent=2) + "\n")
    print(json.dumps({**choice, "saved": str(path)}, indent=2))


def register(subparsers):
    command = subparsers.add_parser("provider", help="Choose and set up the image provider (API key or subscription tool)")
    commands = command.add_subparsers(dest="provider_command", required=True)
    p = commands.add_parser("status", help="Show the chosen provider, whether a key is found, and next steps")
    p.add_argument("project", type=Path, nargs="?")
    p.set_defaults(func=status)
    p = commands.add_parser("set-key", help="Store a Gemini API key in the macOS login Keychain (prompted)")
    p.set_defaults(func=set_key)
    p = commands.add_parser("choose", help="Record the owner's provider choice for a project")
    p.add_argument("project", type=Path)
    p.add_argument("provider", choices=("gemini-api", "subscription"))
    p.add_argument("--tool", choices=SUBSCRIPTION_TOOLS)
    p.add_argument("--owner", required=True, help="Who made the choice")
    p.set_defaults(func=choose)
