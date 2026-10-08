import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class AdminScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scripts = self.root / 'scripts'
        shutil.copytree(ROOT / 'scripts', self.scripts)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        curl = self.bin / 'curl'
        curl.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$TEST_ARGS"\nexit "${TEST_CURL_STATUS:-0}"\n')
        curl.chmod(0o755)
        self.args = self.root / 'args'
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'], 'TEST_ARGS': str(self.args), 'EZBET_ADMIN_API_TOKEN': ''}

    def run_script(self, name):
        return subprocess.run(['sh', str(self.scripts / name)], cwd='/tmp', env=self.env, capture_output=True, text=True)

    def test_all_admin_scripts_load_token_independent_of_cwd(self):
        (self.root / '.env').write_text('EZBET_ADMIN_API_TOKEN=fixture-token\n')
        for name in ['pipeline-tick.sh', 'scheduler-tick.sh', 'pipeline-cron.sh', 'forecast-cron.sh', 'guides-cron.sh']:
            with self.subTest(script=name):
                self.args.write_text('')
                result = self.run_script(name)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = self.args.read_text()
                self.assertIn('x-admin-token: fixture-token', args)
                self.assertIn('--fail-with-body', args)
                self.assertIn('--max-time', args)
                self.assertNotIn('fixture-token', result.stdout + result.stderr)

    def test_missing_token_does_not_call_curl(self):
        self.assertNotEqual(self.run_script('pipeline-cron.sh').returncode, 0)
        self.assertFalse(self.args.exists())

    def test_pipeline_stops_after_first_http_failure(self):
        self.env.update(EZBET_ADMIN_API_TOKEN='fixture-token', TEST_CURL_STATUS='22')
        self.assertEqual(self.run_script('pipeline-tick.sh').returncode, 22)
        self.assertEqual(self.args.read_text().count('x-admin-token:'), 1)

    def test_explicit_environment_overrides_dotenv_defaults(self):
        (self.root / '.env').write_text('EZBET_ADMIN_API_TOKEN=dotenv-token\nEZBET_API_BASE_URL=http://dotenv:8000\n')
        self.env.update(EZBET_ADMIN_API_TOKEN='override-token', EZBET_API_BASE_URL='http://override:8000')
        self.assertEqual(self.run_script('pipeline-cron.sh').returncode, 0)
        args = self.args.read_text()
        self.assertIn('x-admin-token: override-token', args)
        self.assertIn('http://override:8000/api/v1/pipeline/run', args)
        self.assertNotIn('dotenv-token', args)
