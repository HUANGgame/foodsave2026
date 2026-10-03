"""Offline-reviewed owner tool; dry-run by default. Never run by startup/API."""
import argparse
import json
import sys
from pathlib import Path
from foodsave.erasure import Eraser, Policy
from owner_migrate import owner_database, add_connection_arguments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--auth-counter-cleanup',action='store_true',help='Only four expired email quota identifiers; email JSON on stdin, no account deletion')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    # Validate before fetching any token or connecting. No implicit retention default.
    policy = Policy(**json.loads(args.policy.read_text()))
    if args.apply and not policy.enabled:
        parser.error('Execution disabled; operator-approved policy required')
    if not 1 <= args.limit <= 100:
        parser.error('Batch limit must be 1..100')
    email=None
    if args.auth_counter_cleanup:
        from foodsave.schemas import EmailRequest
        try:email=EmailRequest(**json.load(sys.stdin)).email
        except Exception:parser.error('Valid email-only JSON on stdin required; input suppressed')
    database = owner_database(args.server, args.driver)
    try:
        worker=Eraser(database, policy)
        result = [worker.cleanup_auth_rate_identifiers(email,apply=args.apply)] if args.auth_counter_cleanup else worker.run(apply=args.apply, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False))
        if any(r['state'] == 'failed_retryable' for r in result):
            raise SystemExit(1)
    finally:
        database.dispose()


if __name__ == '__main__':
    main()
