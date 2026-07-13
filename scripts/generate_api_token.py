#!/usr/bin/env python3
"""Generate a Bearer token for AI Marketing customer-site API gateways."""

from __future__ import annotations

import argparse
import hashlib
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AI Marketing API token and SHA-256 hash.")
    parser.add_argument("--prefix", default="amkt", help="Token prefix. Default: amkt")
    parser.add_argument("--bytes", type=int, default=32, help="Random byte count. Default: 32")
    parser.add_argument("--env-prefix", default="AI_MARKETING", help="Environment variable prefix.")
    args = parser.parse_args()

    if args.bytes < 32:
        raise SystemExit("--bytes must be at least 32")

    token = f"{args.prefix}_{secrets.token_urlsafe(args.bytes)}"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    env_prefix = args.env_prefix.upper()

    print("Raw token - show this once and paste into AI Marketing:")
    print(token)
    print()
    print("Store this hash on the customer website:")
    print(token_hash)
    print()
    print("Example .env:")
    print(f"{env_prefix}_API_TOKEN_HASH={token_hash}")


if __name__ == "__main__":
    main()
