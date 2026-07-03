"""Operator CLI for the MCP server's per-client API keys (Phase A go-to-market).

Phase A billing is manual: a client pays via a Stripe Payment Link, then the
operator runs this script to issue them a key and sends it over by hand. No
self-serve signup, no automated billing - see linchpin-monetization-plan.

    python examples/issue_mcp_key.py issue "Acme Co"
    python examples/issue_mcp_key.py list
    python examples/issue_mcp_key.py revoke lpk_xxxxxxxx
    python examples/issue_mcp_key.py revoke-client "Acme Co"

Points at data/mcp_keys.sqlite3 by default (same file webapp/app.py reads),
or $LINCHPIN_MCP_KEYS_PATH if set.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.mcp_keys import DEFAULT_PATH, McpKeyStore  # noqa: E402


def _store() -> McpKeyStore:
    path = os.environ.get("LINCHPIN_MCP_KEYS_PATH", "").strip() or DEFAULT_PATH
    return McpKeyStore(path)


def _cmd_issue(args: argparse.Namespace) -> None:
    key = _store().issue(args.client_name)
    print(f"Issued a key for '{args.client_name}':")
    print(key)
    print("This is shown once. Save it now - it cannot be recovered from the store.")


def _cmd_list(_args: argparse.Namespace) -> None:
    keys = _store().list_keys()
    if not keys:
        print("No keys issued yet.")
        return
    for entry in keys:
        status = "active" if entry["active"] else "revoked"
        last_used = entry["last_used_at"]
        last_used_str = "never" if last_used is None else f"{last_used:.0f}"
        print(f"{entry['client_name']:<30} {status:<8} issued={entry['issued_at']:.0f} last_used={last_used_str}")


def _cmd_revoke(args: argparse.Namespace) -> None:
    revoked = _store().revoke(args.key)
    print("Revoked." if revoked else "No active key matched - already revoked or never issued.")


def _cmd_revoke_client(args: argparse.Namespace) -> None:
    count = _store().revoke_client(args.client_name)
    print(f"Revoked {count} active key(s) for '{args.client_name}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="issue a new key for a client")
    p_issue.add_argument("client_name")
    p_issue.set_defaults(func=_cmd_issue)

    p_list = sub.add_parser("list", help="list all issued keys (no plaintext/hash shown)")
    p_list.set_defaults(func=_cmd_list)

    p_revoke = sub.add_parser("revoke", help="revoke one key by its plaintext value")
    p_revoke.add_argument("key")
    p_revoke.set_defaults(func=_cmd_revoke)

    p_revoke_client = sub.add_parser("revoke-client", help="revoke every active key for a client")
    p_revoke_client.add_argument("client_name")
    p_revoke_client.set_defaults(func=_cmd_revoke_client)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
