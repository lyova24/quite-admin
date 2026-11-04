"""Small maintenance commands for library-owned service storage."""

import argparse
from datetime import UTC, datetime, timedelta

import anyio

from .storage import StorageError, create_store


async def _cleanup(args):
    store = create_store(args.storage, namespace=args.namespace)
    try:
        purge = getattr(store, "purge_activities", None)
        if purge is None:
            raise ValueError("The store does not support activity retention.")
        before = datetime.now(UTC) - timedelta(days=args.days)
        total = 0
        while True:
            count = await purge(before=before, limit=args.batch_size)
            total += count
            if count < args.batch_size:
                break
        print(f"Deleted {total} expired activity events.")
    finally:
        close = getattr(store, "aclose", None)
        if close is not None:
            await close()


def main():
    parser = argparse.ArgumentParser(prog="python -m quite_admin")
    commands = parser.add_subparsers(dest="command", required=True)
    cleanup = commands.add_parser("cleanup-history", help="Delete expired history in batches.")
    cleanup.add_argument("--storage", help="Storage path/URL; defaults to QUITE_ADMIN_STORAGE_URL.")
    cleanup.add_argument("--namespace", default="default")
    cleanup.add_argument("--days", type=int, default=90)
    cleanup.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.days <= 365000 or not 1 <= args.batch_size <= 1000:
        parser.error("Use 1–365000 days and a batch size between 1 and 1000.")
    try:
        anyio.run(_cleanup, args)
    except (StorageError, ValueError):
        parser.exit(1, "History cleanup failed. Check storage availability and configuration.\n")


if __name__ == "__main__":
    main()
