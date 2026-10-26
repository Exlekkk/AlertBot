#!/usr/bin/env python3
"""Exercise the actual scanner and Plan B path without Telegram or formal writes."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.scanner import SMCTScanner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shadow', action='store_true', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    scanner = SMCTScanner()
    while True:
        result = scanner.run_once(shadow=True)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0 if result['ok'] and not result['summary']['early_observation'].get('error') else 1
        time.sleep(60)


if __name__ == '__main__':
    raise SystemExit(main())
