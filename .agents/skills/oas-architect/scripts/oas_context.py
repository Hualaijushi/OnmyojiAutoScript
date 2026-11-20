"""OAS 普通恢复。预算只提醒，严格协议由显式入口选择。"""

import argparse
from pathlib import Path
import subprocess
import sys


REFERENCE_CHARS = 12000
COMPATIBLE_MODES = ('entry', 'bootstrap', 'git', 'current')


def git_output(repo, *arguments):
    result = subprocess.run(
        ['git', '--no-optional-locks', *arguments],
        cwd=repo, capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf8', errors='replace').strip())
    if result.stderr:
        raise RuntimeError(result.stderr.decode('utf8', errors='replace').strip())
    return result.stdout.decode('utf8', errors='strict')


def count_changes(porcelain):
    counts = dict(staged=0, unstaged=0, untracked=0, deleted=0, renamed=0, conflicts=0)
    records = porcelain.split('\0')
    position = 0
    while position < len(records):
        record = records[position]
        position += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != ' ':
            raise ValueError('Git 状态记录格式无法识别')
        state = record[:2]
        if any(character not in ' MADRCUT?!' for character in state):
            raise ValueError('Git 状态包含未知代码')
        if state == '??':
            counts['untracked'] += 1
            continue
        if state == '!!':
            continue
        counts['staged'] += state[0] != ' '
        counts['unstaged'] += state[1] != ' '
        counts['deleted'] += 'D' in state
        counts['renamed'] += 'R' in state
        counts['conflicts'] += state in ('DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU')
        if 'R' in state or 'C' in state:
            if position >= len(records) or not records[position]:
                raise ValueError('Git 重命名或复制记录缺少原路径')
            position += 1
    return counts


def git_summary(repo):
    actual_root = git_output(repo, 'rev-parse', '--show-toplevel').strip()
    if Path(actual_root).resolve() != repo:
        raise ValueError('所选目录与实际 worktree 根目录不同')
    branch = git_output(repo, 'branch', '--show-current').strip() or '(detached)'
    head = git_output(repo, 'rev-parse', 'HEAD').strip()
    counts = count_changes(git_output(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all'))
    lines = [f'项目根目录 = {actual_root}', f'分支 = {branch}', f'HEAD = {head}']
    labels = dict(staged='暂存', unstaged='未暂存', untracked='未跟踪文件',
                  deleted='删除', renamed='重命名', conflicts='冲突')
    lines.extend(f'{labels[key]} = {value}' for key, value in counts.items())
    return '\n'.join(lines)


def current_summary(path):
    """兼容旧 CURRENT。仅将显式历史基线章节保留为位置引用。"""
    lines = path.read_bytes().decode('utf-8-sig', errors='strict').splitlines()
    if not any(line.strip() and not line.lstrip().startswith('#') for line in lines):
        raise ValueError('CURRENT 缺少任务内容，当前任务尚待确认')
    result = []
    historical_start = None
    for number, line in enumerate(lines, 1):
        if line.startswith('## '):
            if historical_start is not None:
                result.append(f'历史工作区基线参见 CURRENT L{historical_start}–L{number - 1}，保护全部预存 WIP。')
                historical_start = None
            if line.strip() in ('## 2. 工作区基线', '## 历史记录'):
                historical_start = number
        if historical_start is None:
            result.append(line)
    if historical_start is not None:
        result.append(f'历史工作区基线参见 CURRENT L{historical_start}–L{len(lines)}，保护全部预存 WIP。')
    return '\n'.join(result).strip()


def recover(repo):
    sections = ['OAS 普通上下文恢复']
    issues = []
    try:
        sections.extend(['## 实时 Git', git_summary(repo)])
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        issues.append('Git')
        sections.append(f'Git 待核实。{error}')
    try:
        sections.extend(['## 当前任务', current_summary(repo / 'docs/CURRENT.md')])
    except FileNotFoundError:
        issues.append('CURRENT')
        sections.append('CURRENT 缺失，当前任务尚待确认。可按用户本轮明确的新需求继续分析。')
    except (OSError, UnicodeError, ValueError) as error:
        issues.append('CURRENT')
        sections.append(f'CURRENT 待核实。{error}')
    if issues:
        sections.append('恢复结果 = 部分恢复。请报告已知事实，并继续处理可独立完成的事项。')
    else:
        sections.append('恢复材料 = Git 与 CURRENT 已取得。请依据正文核实必要事实，再按本轮请求选择角色。')
    return '\n\n'.join(sections) + '\n', issues


def strict_command(arguments):
    arguments = [argument for argument in arguments if argument != '--strict']
    if not arguments or arguments[0] == 'status':
        print('严格兼容入口需要明确的旧协议模式，请按批准的验收对象选择。')
        return 2
    script = Path(__file__).with_name('oas_strict.py')
    return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(script), '--strict', *arguments]).returncode


def main(arguments=None):
    sys.stdout.reconfigure(encoding='utf8', errors='strict', newline='\n')
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if '--strict' in arguments:
        return strict_command(arguments)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='status', choices=('status',) + COMPATIBLE_MODES)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--warn-at', type=int, default=REFERENCE_CHARS)
    parser.add_argument('--spent', type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument('--remaining', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--memory-required', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args(arguments)
    if options.warn_at < 1 or options.spent < 0:
        parser.error('提醒值须为正整数，已发生读取量须为非负数')
    repo = (options.repo or Path(__file__).resolve().parents[4]).resolve()
    body, issues = recover(repo)
    if options.mode in COMPATIBLE_MODES:
        body += '兼容入口已采用普通恢复规则。\n'
    if options.remaining is not None:
        body += f'旧预算参数 remaining={options.remaining} 仅供提醒，必要信息已继续读取。\n'
    if options.memory_required:
        body += '宿主记忆请复用会话已有结果，按宿主要求补齐尚缺的相关提醒。\n'
    estimate = len(body) + options.spent
    if estimate >= options.warn_at:
        body += f'读取提醒 = 正文及已知前置量估算 {estimate} 字符，参考值 {options.warn_at}。请收缩可选历史检索并补齐必要依据。\n'
    sys.stdout.write(body)
    return 2 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
