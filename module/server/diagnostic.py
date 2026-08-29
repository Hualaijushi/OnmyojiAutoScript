# This Python file uses the following encoding: utf-8
# @author runhey
"""导出脱敏后的配置摘要与最近日志为 zip，用于风控对照分析。不导出账号/token/密码。"""
import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from module.config.utils import read_file, deep_get
from module.server.config_manager import ConfigManager
from module.logger import logger

PROJECT_ROOT = Path.cwd().resolve()
LOG_DIR = PROJECT_ROOT / 'log'
OUT_DIR = LOG_DIR / 'diagnostic'

_RECENT_INSTANCE_LOGS = 4
_RECENT_SHARED_LOGS = 3
_RECENT_ERROR_LOGS = 10
_MAX_DIAGNOSTIC_ZIPS = 5

# 白名单：只导出这些字段，不带出 URS 凭据
_DEVICE_FIELDS = [
    'control_method', 'screenshot_method', 'serial', 'package_name',
    'emulatorinfo_type', 'emulatorinfo_name',
]

_SENSITIVE_KEYS = {
    'password', 'passwd', 'pwd',
    'token', 'access_token', 'refresh_token', 'id_token',
    'authorization', 'cookie', 'set_cookie',
    'api_key', 'apikey', 'secret', 'client_secret',
    'account', 'username', 'urs',
}
_KEY_PATTERN = '|'.join(sorted((re.escape(key) for key in _SENSITIVE_KEYS), key=len, reverse=True))
_URL_PATTERN = re.compile(r'(?i)\b(?:https?|socks5)://[^\s"\'<>\[\]{}]+')
_HEADER_PATTERN = re.compile(
    r'(?im)(?P<prefix>\b(?:authorization|cookie|set-cookie)\b\s*[:=]\s*)(?P<value>[^\r\n]+)'
)
_BRACKET_ACCOUNT_PATTERN = re.compile(
    r'(?i)(?P<prefix>\b(?:account|username|urs)\b\s*)\[\s*[^\]\r\n]+\s*\]'
)
_KEY_VALUE_PATTERN = re.compile(
    rf'(?P<prefix>(?<![\w])(?:{_KEY_PATTERN})\b["\']?\s*[:=：]\s*["\']?)'
    r'(?P<value>[^\s"\',;&?{}\[\]]+)',
    re.I,
)
_CHINESE_ACCOUNT_PATTERN = re.compile(r'(账号\s*[:：=]\s*)([^\s"\',;&?{}\[\]]+)', re.I)
_EMAIL_PATTERN = re.compile(r'(?i)\b([a-z0-9.!#$%&\'*+/=?^_`{|}~-]+)@([a-z0-9.-]+\.[a-z]{2,})\b')
_WINDOWS_USER_PATH_PATTERN = re.compile(r'(?i)([a-z]:\\Users\\)[^\\/\r\n]+')
_PHONE_PATTERN = re.compile(r'\b(1[3-9]\d)\d{4}(\d{4})\b')
_IPV4_PATTERN = re.compile(
    r'(?<!\d)(?P<a>\d{1,3})\.(?P<b>\d{1,3})\.(?P<c>\d{1,3})\.(?P<d>\d{1,3})'
    r'(?P<port>:\d+)?(?!\d)'
)


def _normalize_sensitive_key(key: object) -> str:
    return str(key).strip().lower().replace('-', '_')


def _is_sensitive_key(key: object) -> bool:
    return _normalize_sensitive_key(key) in _SENSITIVE_KEYS


def _mask_email(match: re.Match) -> str:
    return f'{match.group(1)[0]}***@{match.group(2)}'


def _scrub_plain_text(text: str) -> str:
    text = _HEADER_PATTERN.sub(lambda match: f'{match.group("prefix")}***', text)
    text = _BRACKET_ACCOUNT_PATTERN.sub(lambda match: f'{match.group("prefix")}[***]', text)
    text = _KEY_VALUE_PATTERN.sub(lambda match: f'{match.group("prefix")}***', text)
    text = _CHINESE_ACCOUNT_PATTERN.sub(r'\1***', text)
    text = _EMAIL_PATTERN.sub(_mask_email, text)
    text = _WINDOWS_USER_PATH_PATTERN.sub(r'\1***', text)
    text = _PHONE_PATTERN.sub(r'\1****\2', text)
    return text


def _scrub_url(match: re.Match) -> str:
    raw_url = match.group(0)
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return _scrub_plain_text(raw_url)

    netloc = parts.netloc
    if '@' in netloc:
        netloc = f'***@{netloc.rsplit("@", 1)[1]}'

    query_items = []
    try:
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if _is_sensitive_key(key):
                value = '***'
            else:
                value = _scrub_text(value, decode_once=False)
            query_items.append((_scrub_plain_text(key), value))
        query = urlencode(query_items, doseq=True, safe='*')
    except ValueError:
        query = _scrub_plain_text(parts.query)

    path = _scrub_plain_text(parts.path)
    fragment = _scrub_text(parts.fragment, decode_once=False)
    return urlunsplit((parts.scheme, netloc, path, query, fragment))


def _scrub_text(text: str, decode_once: bool) -> str:
    if decode_once and '%' in text:
        try:
            text = unquote(text)
        except (UnicodeDecodeError, ValueError):
            pass
    text = _URL_PATTERN.sub(_scrub_url, text)
    return _scrub_plain_text(text)


def _scrub(text: str) -> str:
    """统一脱敏日志、URL和异常文本，URL编码最多解码一次。"""
    return _scrub_text(str(text), decode_once=True)


def _scrub_mapping(data):
    """递归复制并脱敏配置摘要，不修改原对象。"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            output_key = _scrub(key) if isinstance(key, str) else key
            result[output_key] = '***' if _is_sensitive_key(key) else _scrub_mapping(value)
        return result
    if isinstance(data, list):
        return [_scrub_mapping(value) for value in data]
    if isinstance(data, tuple):
        return tuple(_scrub_mapping(value) for value in data)
    if isinstance(data, str):
        return _scrub(data)
    return data


def _scrub_serial(value):
    if not isinstance(value, str):
        return value

    def replace(match: re.Match) -> str:
        parts = [int(match.group(name)) for name in ('a', 'b', 'c', 'd')]
        if any(part > 255 for part in parts) or parts[0] == 127:
            return match.group(0)
        port = match.group('port') or ''
        return f'{parts[0]}.{parts[1]}.*.*{port}'

    return _scrub(_IPV4_PATTERN.sub(replace, value))


def _safe_archive_component(value: object, fallback: str) -> str:
    value = _scrub(str(value)).replace('/', '_').replace('\\', '_').replace('..', '_').strip(' .')
    return value or fallback


def _config_summary(name: str) -> dict:
    data = read_file(str(PROJECT_ROOT / 'config' / f'{name}.json'))
    if not isinstance(data, dict):
        return {'instance': _scrub(name), 'error': 'config unreadable'}
    device = {key: deep_get(data, f'script.device.{key}') for key in _DEVICE_FIELDS}
    device = _scrub_mapping(device)
    device['serial'] = _scrub_serial(device.get('serial'))
    optimization = _scrub_mapping(data.get('script', {}).get('optimization', {}))
    anti_ban = _scrub_mapping(data.get('script', {}).get('anti_ban', {}))
    enabled = []
    for task, cfg in data.items():
        if isinstance(cfg, dict) and deep_get(cfg, 'scheduler.enable') is True:
            enabled.append(_scrub(str(task)))
    return {
        'instance': _scrub(name),
        'device': device,
        'optimization': optimization,
        'anti_ban': anti_ban,
        'enabled_tasks': sorted(enabled),
    }


def _recent_files(pattern: str, limit: int) -> list:
    try:
        candidates = [path for path in LOG_DIR.glob(pattern) if path.is_file() and not path.is_symlink()]
    except OSError:
        return []
    recent = []
    for path in candidates:
        try:
            recent.append((path.stat().st_mtime, path))
        except OSError:
            continue
    recent.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in recent[:limit]]


def _cleanup_old_archives(current_zip: Path) -> None:
    try:
        candidates = [
            path for path in OUT_DIR.glob('*.zip')
            if path.is_file() and not path.is_symlink()
        ]
    except OSError as e:
        logger.warning(f'诊断包清理失败：{_scrub(e)}')
        return

    archives = []
    for path in candidates:
        try:
            archives.append((path == current_zip, path.stat().st_mtime, path))
        except OSError as e:
            logger.warning(f'诊断包状态读取失败：{_scrub(path)}，{_scrub(e)}')
    archives.sort(key=lambda item: (item[0], item[1]), reverse=True)
    for _, _, path in archives[_MAX_DIAGNOSTIC_ZIPS:]:
        try:
            path.unlink()
        except OSError as e:
            logger.warning(f'诊断包清理失败：{_scrub(path)}，{_scrub(e)}')


def build_diagnostic_zip(config_name: str = '') -> Path:
    """config_name 为空或 'Home' 时导出全部实例。"""
    # 只接受已存在的实例名，防止 config_name 带 ../ 造成路径穿越
    valid = ConfigManager.all_script_files()
    if config_name and config_name in valid:
        instances = [config_name]
        tag = 'single'
    else:
        instances = valid
        tag = 'all'

    summary = _scrub_mapping({
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'platform': platform.platform(),
        'python': sys.version.split()[0],
        'instances': [_config_summary(name) for name in instances],
    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    zip_path = OUT_DIR / f'oas_diag_{tag}_{stamp}.zip'

    log_files = []
    for name in instances:
        log_files += _recent_files(f'*_{name}.txt', _RECENT_INSTANCE_LOGS)
    log_files += _recent_files('*_api.txt', _RECENT_SHARED_LOGS)
    log_files += _recent_files('*_server.txt', _RECENT_SHARED_LOGS)

    error_logs = []
    error_root = LOG_DIR / 'error'
    if error_root.exists():
        try:
            error_logs = [
                path for path in error_root.glob('*/log.txt')
                if path.is_file() and not path.is_symlink()
            ]
            error_logs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            error_logs = error_logs[:_RECENT_ERROR_LOGS]
        except OSError:
            error_logs = []

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('summary.json', json.dumps(summary, ensure_ascii=False, indent=2))
        for path in dict.fromkeys(log_files):
            try:
                content = _scrub(path.read_text(encoding='utf-8', errors='replace'))
                archive_name = _safe_archive_component(path.name, 'log.txt')
                zf.writestr(f'log/{archive_name}', content)
            except OSError as e:
                logger.warning(f'诊断导出跳过文件：{_scrub(path)}，{_scrub(e)}')
        for path in error_logs:
            try:
                content = _scrub(path.read_text(encoding='utf-8', errors='replace'))
                folder = _safe_archive_component(path.parent.name, 'error')
                zf.writestr(f'error/{folder}/log.txt', content)
            except OSError as e:
                logger.warning(f'诊断导出跳过文件：{_scrub(path)}，{_scrub(e)}')

    _cleanup_old_archives(zip_path)
    logger.info(f'诊断日志已导出：{zip_path}')
    return zip_path
