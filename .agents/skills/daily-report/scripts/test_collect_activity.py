import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).with_name('collect_activity.py'))
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class HistoricalActivityTest(unittest.TestCase):
    def test_reopened_session_midnight_and_no_tool_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / 'conversation.jsonl'
            events = []
            for ts, role, text in [
                ('2026-11-15T20:59:59Z', 'user', 'before day'),
                ('2026-11-15T21:00:00Z', 'user', 'midnight included'),
                ('2026-11-16T20:59:59Z', 'assistant', 'last second included'),
                ('2026-11-16T21:00:00Z', 'assistant', 'next day excluded'),
            ]:
                events.append({'timestamp': ts, 'type': 'response_item', 'payload': {'type': 'message', 'role': role, 'content': [{'type': 'output_text', 'text': text}]}})
            events.append({'timestamp': '2026-11-16T10:00:00Z', 'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'secret tool output'}})
            log.write_text('\n'.join(json.dumps(e) for e in events))
            db = root / 'index.db'
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE threads (id, rollout_path, cwd, title, git_branch, git_origin_url, updated_at)')
            # Last updated several days later: historical day must still be read.
            con.execute('INSERT INTO threads VALUES (?,?,?,?,?,?,?)', ('s1', str(log), '/Users/x/orca/workspaces/client/task', 'Task', 'feature', 'url', 1795100000))
            con.commit()
            con.close()
            start, end = collector.window('2026-11-16', 'Europe/Istanbul')
            warnings = []
            rows = collector.read_codex(db, start, end, warnings)
            self.assertEqual([m['text'] for m in rows[0]['messages']], ['midnight included', 'last second included'])
            self.assertEqual(rows[0]['source'], 'orca-codex')
            self.assertIsNone(rows[0]['status_as_of_date'])
            self.assertEqual(warnings, [])

    def test_missing_source_is_not_empty_success(self):
        warnings = []
        start, end = collector.window('2026-11-16', 'Europe/Istanbul')
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(collector.read_codex(Path(temp) / 'missing', start, end, warnings), [])
        self.assertTrue(warnings)


if __name__ == '__main__':
    unittest.main()
