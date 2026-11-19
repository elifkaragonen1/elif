#!/usr/bin/env python3
"""Read local Codex conversation events by Istanbul day, plus legacy collectors.
Never writes app databases or treats workspace.updatedAt as proof of work.
"""
import argparse
from datetime import datetime, time, timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo


def window(day, timezone):
    start = datetime.combine(datetime.strptime(day, '%Y-%m-%d').date(), time(), ZoneInfo(timezone))
    return start, start + timedelta(days=1)


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def read_codex(db, start, end, warnings):
    sessions = []
    if not db.exists():
        warnings.append('Codex index unavailable; Orca/Codex activity not checked.')
        return sessions
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute('SELECT id,rollout_path,cwd,title,git_branch,git_origin_url FROM threads WHERE updated_at >= ?', (int(start.timestamp()),)).fetchall()
    finally:
        con.close()
    for row in rows:
        messages, fallback = [], []
        path = Path(row['rollout_path'])
        try:
            with path.open() as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        warnings.append(f'Malformed conversation event: {row["id"]}')
                        continue
                    ts = parse_time(event.get('timestamp'))
                    if not ts or not ts.tzinfo or not start <= ts < end:
                        continue
                    payload = event.get('payload', {})
                    if not isinstance(payload, dict):
                        continue
                    if event.get('type') == 'response_item' and payload.get('type') == 'message' and payload.get('role') in ('user', 'assistant'):
                        text = '\n'.join(p.get('text', '') for p in payload.get('content', []) if isinstance(p, dict) and p.get('type') in ('input_text', 'output_text', 'text'))
                        # Exclude injected environment/AGENTS context, never extract tool output.
                        if text and not text.lstrip().startswith(('<environment_context>', '# AGENTS.md instructions')):
                            messages.append({'at': ts.astimezone(start.tzinfo).isoformat(), 'role': payload['role'], 'text': text})
                    elif event.get('type') == 'event_msg' and payload.get('type') in ('user_message', 'agent_message'):
                        text = payload.get('message')
                        if isinstance(text, str) and text:
                            fallback.append({'at': ts.astimezone(start.tzinfo).isoformat(), 'role': 'user' if payload['type'] == 'user_message' else 'assistant', 'text': text})
        except OSError as exc:
            warnings.append(f'Conversation unavailable {row["id"]}: {exc.strerror}')
            continue
        messages = sorted(messages or fallback, key=lambda m: m['at'])
        if messages:
            sessions.append(dict(row) | {'source': 'orca-codex' if '/orca/' in row['cwd'] else 'conductor-codex' if '/conductor/' in row['cwd'] else 'codex', 'messages': messages, 'evidence_file': str(path), 'status_as_of_date': None})
    return sessions


def legacy(name, day, warnings):
    script = Path(__file__).with_name(name + '.py')
    if not script.exists():
        warnings.append(name + ': collector missing')
        return {'checked': False, 'rows': []}
    try:
        result = subprocess.run([sys.executable, str(script), day], capture_output=True, text=True, timeout=240, env=dict(os.environ, TZ='Europe/Istanbul'))
        if result.returncode:
            warnings.append(name + ': failed: ' + result.stderr[-500:])
            return {'checked': False, 'rows': []}
        if result.stderr.strip():
            warnings.append(name + ': ' + result.stderr[-500:])
        warnings.append(name + ': legacy collector can suppress per-repository forge/auth failures; empty rows are not verified absence.')
        return {'checked': True, 'rows': json.loads(result.stdout), 'coverage': 'legacy best effort; verify forge access separately'}
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        warnings.append(name + ': ' + str(exc))
        return {'checked': False, 'rows': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('date')
    parser.add_argument('--timezone', default='Europe/Istanbul')
    parser.add_argument('--codex-db', type=Path, default=Path.home() / '.codex/state_5.sqlite')
    parser.add_argument('--include-legacy', action='store_true')
    parser.add_argument('--output', type=Path, required=True, help='Private local evidence JSON; contains conversation text, do not commit/share')
    args = parser.parse_args()
    start, end = window(args.date, args.timezone)
    warnings = ['Local Codex conversations only: Claude/other agents and remote hosts require separate collection. Conversation text is evidence to review, not proof that a claimed change succeeded.']
    try:
        sessions = read_codex(args.codex_db, start, end, warnings)
    except sqlite3.Error as exc:
        sessions = []
        warnings.append('Codex index/schema unavailable: ' + str(exc))
    result = {'date': args.date, 'timezone': args.timezone, 'generated_at': datetime.now(start.tzinfo).isoformat(), 'window': {'start': start.isoformat(), 'end_exclusive': end.isoformat()}, 'sessions': sessions, 'warnings': warnings}
    if args.include_legacy:
        result['conductor'] = legacy('collect_conductor', args.date, warnings)
        result['closed_prs'] = legacy('collect_merged_prs', args.date, warnings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # File is private on initial creation and replacement.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'date': args.date, 'sessions': len(sessions), 'messages': sum(len(s['messages']) for s in sessions), 'warnings': len(warnings), 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
