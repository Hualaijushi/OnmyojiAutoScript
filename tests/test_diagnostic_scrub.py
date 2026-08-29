import copy
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from module.server import diagnostic


class DiagnosticScrubTest(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.log_dir = self.root / 'log'
        self.out_dir = self.log_dir / 'diagnostic'
        (self.root / 'config').mkdir(parents=True)
        self.log_dir.mkdir(parents=True)

        patchers = [
            patch.object(diagnostic, 'PROJECT_ROOT', self.root),
            patch.object(diagnostic, 'LOG_DIR', self.log_dir),
            patch.object(diagnostic, 'OUT_DIR', self.out_dir),
            patch.object(diagnostic.ConfigManager, 'all_script_files', return_value=['oas1']),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        config = {
            'script': {
                'device': {
                    'control_method': 'minitouch',
                    'screenshot_method': 'nemu_ipc',
                    'serial': '192.168.1.88:5555',
                    'package_name': 'com.netease.onmyoji',
                    'emulatorinfo_type': 'MuMuPlayer12',
                    'emulatorinfo_name': 'Alice@example.com',
                },
                'optimization': {
                    'normal': 'value',
                    'token': 'CONFIG_TOKEN_SECRET',
                },
                'anti_ban': {
                    'nested': {'password': 'CONFIG_PASSWORD_SECRET'},
                },
            },
            'TestTask': {'scheduler': {'enable': True}},
        }
        (self.root / 'config' / 'oas1.json').write_text(
            json.dumps(config, ensure_ascii=False),
            encoding='utf-8',
        )

    def _write_fake_logs(self):
        (self.log_dir / '2026-01-01_oas1.txt').write_text(
            'account [ INSTANCE_ACCOUNT_SECRET ] Token: INSTANCE_TOKEN_SECRET',
            encoding='utf-8',
        )
        (self.log_dir / '2026-01-01_api.txt').write_text(
            'https://host/api?a=1&token=API_TOKEN_SECRET&account=API_ACCOUNT_SECRET',
            encoding='utf-8',
        )
        (self.log_dir / '2026-01-01_server.txt').write_bytes(
            b'\xffCookie: session=COOKIE_SECRET\nAuthorization: Bearer AUTH_SECRET'
        )
        error_dir = self.log_dir / 'error' / 'oas1_1'
        error_dir.mkdir(parents=True)
        (error_dir / 'log.txt').write_text(
            'http://PROXY_USER_SECRET:PROXY_PASSWORD_SECRET@host:1234\n'
            'abc@example.com\nC:\\Users\\Alice\\project',
            encoding='utf-8',
        )

    def test_scrub_covers_sensitive_text_formats(self):
        cases = {
            'token_header': ('Token: TOKEN_SECRET', 'TOKEN_SECRET'),
            'token_value': ('token=TOKEN_VALUE_SECRET', 'TOKEN_VALUE_SECRET'),
            'password': ('password=PASSWORD_SECRET', 'PASSWORD_SECRET'),
            'account_colon': ('account: ACCOUNT_SECRET', 'ACCOUNT_SECRET'),
            'account_bracket_email': ('account [ abc@example.com ]', 'abc@example.com'),
            'account_bracket': ('Account [ test123 ]', 'test123'),
            'account_bracket_compact': ('ACCOUNT[foo]', 'foo'),
            'cookie': ('Cookie: session=COOKIE_SECRET', 'COOKIE_SECRET'),
            'authorization': ('Authorization: Bearer AUTH_SECRET', 'AUTH_SECRET'),
            'api_key': ('api_key=API_KEY_SECRET', 'API_KEY_SECRET'),
            'url_query': (
                'https://host/path?a=1&token=URL_TOKEN_SECRET&account=URL_ACCOUNT_SECRET',
                'URL_TOKEN_SECRET',
            ),
            'encoded_token': ('token%3AENCODED_TOKEN_SECRET', 'ENCODED_TOKEN_SECRET'),
            'encoded_password': ('password%3DENCODED_PASSWORD_SECRET', 'ENCODED_PASSWORD_SECRET'),
            'encoded_query_value': (
                'https://host/notify?setting=provider%3Atest%0Atoken%3ANESTED_TOKEN_SECRET',
                'NESTED_TOKEN_SECRET',
            ),
            'proxy': (
                'http://PROXY_USER_SECRET:PROXY_PASSWORD_SECRET@host:1234',
                'PROXY_PASSWORD_SECRET',
            ),
            'email': ('abc@example.com', 'abc@example.com'),
            'windows_user': ('C:\\Users\\Alice\\project', 'Alice'),
        }

        for name, (source, secret) in cases.items():
            with self.subTest(name=name):
                result = diagnostic._scrub(source)
                self.assertNotIn(secret, result)

        proxy_result = diagnostic._scrub('socks5://proxy_user:proxy_password@host:1080')
        self.assertEqual(proxy_result, 'socks5://***@host:1080')
        email_result = diagnostic._scrub('abc@example.com')
        self.assertEqual(email_result, 'a***@example.com')

    def test_scrub_preserves_non_sensitive_content(self):
        source = (
            'Python 3.12\n'
            'control_method=minitouch\n'
            '127.0.0.1:16384\n'
            '普通错误文本\n'
            'TestTask'
        )
        self.assertEqual(diagnostic._scrub(source), source)
        self.assertEqual(diagnostic._scrub_serial('127.0.0.1:16384'), '127.0.0.1:16384')
        self.assertEqual(diagnostic._scrub_serial('192.168.1.88:5555'), '192.168.*.*:5555')

    def test_scrub_mapping_is_recursive_and_does_not_modify_input(self):
        source = {
            'token': 'MAPPING_TOKEN_SECRET',
            'nested': {
                'password': 'MAPPING_PASSWORD_SECRET',
                'normal': 'value',
            },
            'list': [
                {'account': 'MAPPING_ACCOUNT_SECRET'},
                'safe',
            ],
            'tuple': ({'client_secret': 'MAPPING_CLIENT_SECRET'}, 'normal'),
        }
        original = copy.deepcopy(source)

        result = diagnostic._scrub_mapping(source)

        self.assertEqual(source, original)
        self.assertEqual(result['token'], '***')
        self.assertEqual(result['nested']['password'], '***')
        self.assertEqual(result['nested']['normal'], 'value')
        self.assertEqual(result['list'], [{'account': '***'}, 'safe'])
        self.assertEqual(result['tuple'], ({'client_secret': '***'}, 'normal'))

    def test_zip_content_is_scrubbed_before_writing(self):
        self._write_fake_logs()

        zip_path = diagnostic.build_diagnostic_zip('oas1')

        self.assertTrue(zip_path.is_file())
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            content = '\n'.join(
                zf.read(name).decode('utf-8', errors='replace')
                for name in names
            )

        self.assertIn('summary.json', names)
        self.assertTrue(any(name.startswith('log/') for name in names))
        self.assertTrue(any(name.startswith('error/') for name in names))
        for secret in (
            'CONFIG_TOKEN_SECRET',
            'CONFIG_PASSWORD_SECRET',
            'INSTANCE_ACCOUNT_SECRET',
            'INSTANCE_TOKEN_SECRET',
            'API_TOKEN_SECRET',
            'API_ACCOUNT_SECRET',
            'COOKIE_SECRET',
            'AUTH_SECRET',
            'PROXY_USER_SECRET',
            'PROXY_PASSWORD_SECRET',
            'abc@example.com',
            'Alice',
            '192.168.1.88',
        ):
            self.assertNotIn(secret, content)
        self.assertIn('control_method', content)
        self.assertIn('minitouch', content)
        self.assertIn('192.168.*.*:5555', content)

    def test_zip_cleanup_keeps_latest_five(self):
        self.out_dir.mkdir(parents=True)
        for index in range(7):
            path = self.out_dir / f'old_{index}.zip'
            path.write_bytes(b'old')
            os.utime(path, (index + 1, index + 1))

        current_zip = diagnostic.build_diagnostic_zip('oas1')
        archives = list(self.out_dir.glob('*.zip'))

        self.assertEqual(len(archives), diagnostic._MAX_DIAGNOSTIC_ZIPS)
        self.assertIn(current_zip, archives)

    def test_zip_cleanup_failure_does_not_break_new_export(self):
        self.out_dir.mkdir(parents=True)
        old_archives = []
        for index in range(5):
            path = self.out_dir / f'old_{index}.zip'
            path.write_bytes(b'old')
            os.utime(path, (index + 1, index + 1))
            old_archives.append(path)
        blocked_path = old_archives[0]
        original_unlink = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == blocked_path:
                raise PermissionError('测试清理失败')
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', autospec=True, side_effect=unlink), \
                patch.object(diagnostic.logger, 'warning') as warning_mock:
            current_zip = diagnostic.build_diagnostic_zip('oas1')

        self.assertTrue(current_zip.is_file())
        self.assertTrue(blocked_path.is_file())
        warning_mock.assert_called()
