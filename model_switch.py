"""Standalone small provider switcher for Loop ROS, not global CLI configs."""
import argparse
import json
from pathlib import Path

from terminal.config import ROOT, DEFAULT_STATE_DIR, load_config
from terminal.providers import ProviderStore, choose_profile
from terminal.llm import QwenClient
from terminal.setup import quick_setup


def edit_profile(store, name, editing=False):
    old = store.get(name) if editing else {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus", "api_key_env": "DASHSCOPE_API_KEY", "timeout_s": 60, "token_field": "max_tokens"}
    config = dict(old)
    for field in ("base_url", "model", "api_key_env", "timeout_s", "token_field", "protocol"):
        default = old.get(field, "openai" if field == "protocol" else "max_tokens")
        value = input("{} [{}]: ".format(field, default)).strip() or str(default)
        config[field] = float(value) if field == "timeout_s" else value
    if config['model'] != old['model']:
        config.pop('context_window', None)
    store.save(name, config, replace=editing)
    print("Saved. Set the API key in the named environment variable; keys are not stored in the database.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Loop Switch · Provider and model settings")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--advanced", action="store_true", help="Open the full profile manager")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list")
    setup = sub.add_parser("setup")
    setup.add_argument("slot", nargs="?", default="master", choices=("master", "expert"))
    for command in ("add", "edit", "remove", "check"):
        sub.add_parser(command).add_argument("name")
    select = sub.add_parser("use")
    select.add_argument("slot", choices=("master", "expert"))
    select.add_argument("name")
    pick = sub.add_parser("pick")
    pick.add_argument("slot", nargs="?", default="master", choices=("master", "expert"))
    args = parser.parse_args(argv)
    store = ProviderStore(args.state_dir / "providers.sqlite", load_config(args.config))
    try:
        if args.command == "setup" or (args.command is None and not args.advanced):
            quick_setup(store, getattr(args, "slot", "master"))
        elif args.command == "list":
            print(json.dumps(store.list(), ensure_ascii=False, indent=2))
        elif args.command in ("add", "edit"):
            edit_profile(store, args.name, args.command == "edit")
        elif args.command == "remove":
            store.remove(args.name)
            print("Inactive profile removed.")
        elif args.command == "check":
            # Explicit action only; no surprise requests when selecting a profile.
            result = QwenClient(store.get(args.name)).complete([{"role": "user", "content": "Reply OK."}], [])
            print("Valid model response. Tool calling and vision have not been verified.")
            if not result.get("content"):
                print("Note: response text is empty.")
        elif args.command == "use":
            store.use(args.slot, args.name)
            print("Selection saved. Use /switch reload in running terminals.")
        elif args.command == "pick":
            choose_profile(store, args.slot)
        else:
            while True:
                print("\nLoop Switch: 1 List  2 Add  3 Edit  4 Select model  6 Remove  0 Exit")
                choice = input("> ").strip()
                if choice == "0":
                    break
                try:
                    if choice == "1":
                        print(json.dumps(store.list(), ensure_ascii=False, indent=2))
                    elif choice in ("2", "3"):
                        edit_profile(store, input("Profile name: ").strip(), choice == "3")
                    elif choice in ("4", "5"):
                        choose_profile(store, "master" if choice == "4" else "expert")
                    elif choice == "6":
                        store.remove(input("Inactive profile to remove: ").strip())
                except (ValueError, RuntimeError) as exc:
                    print("Error: " + str(exc))
    except (ValueError, RuntimeError) as exc:
        print("Error: " + str(exc))
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nExited.")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
