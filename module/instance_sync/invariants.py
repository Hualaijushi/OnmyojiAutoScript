# This Python file uses the following encoding: utf-8
"""账本不变式校验：独立于 `state_machine.op_*` 的第二道防线。

- `validate_document`：一份账本本身是否结构合法、状态自洽（读盘时用；损坏 / 未知版本在这里被拒）。
- `validate_transition`：一次事务前后两份账本之间的变更是否合法（写盘前用）。

校验器不信任操作函数：终态不可逆、失败优先、写一次的时间戳、attempt 只追加、
「unknown / done 之后不再发」「重试间隔」等规则在这里再检查一遍，操作函数写错也不会让坏账本落盘。
两个函数都只返回问题列表（空列表 = 合法），不抛异常、不改参数。
"""

from __future__ import annotations

from typing import Any, Optional

from module.instance_sync.state_machine import (
    A_ALL, A_DONE, A_NOT_DONE, A_PREPARED, A_ABORTED, A_UNKNOWN,
    G_COMPLETED, G_FAILED, G_OPEN, G_TERMINAL, LATE_ACK,
    P_EXECUTING, P_FAILED, P_JOINED, P_READY, P_TERMINAL, P_TRANSITIONS, P_VERIFIED,
    PARAM_KEYS, SCHEMA_VERSION,
)

_EPS = 1e-6
_ROUND_KEYS = {'round_id', 'seq', 'created_by', 'created_at', 'protocol', 'members', 'rendezvous_deadline_at',
               'ready_at', 'deadline_at', 'global', 'participants', 'attempts', 'late_events'}
_GLOBAL_KEYS = {'state', 'reason', 'at', 'by', 'detail'}
_PARTICIPANT_KEYS = {'alias', 'session_id', 'state', 'state_at', 'failure'}
_ATTEMPT_KEYS = {'attempt_id', 'instance', 'kind', 'seq', 'prepared_at', 'status', 'resolved_at', 'evidence'}
_LATE_KEYS = {'at', 'instance', 'op', 'detail'}
_ATTEMPT_IMMUTABLE = ('attempt_id', 'instance', 'kind', 'seq', 'prepared_at')
_ROUND_IMMUTABLE = ('round_id', 'seq', 'created_by', 'created_at', 'protocol', 'members', 'rendezvous_deadline_at')


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num_or_none(v: Any) -> bool:
    return v is None or _num(v)


# ----------------------------------------------------------------------------------------------------------------------
# 单份文档
# ----------------------------------------------------------------------------------------------------------------------
def validate_document(doc: Any, expected_key: Optional[dict] = None) -> list[str]:
    try:
        return _validate_document(doc, expected_key)
    except (TypeError, KeyError, AttributeError, IndexError, ValueError) as exc:
        # 手改 / 部分写入的账本可能让某个字段类型错乱：一律当作不合法，不让校验器自己崩
        return [f'malformed document: {type(exc).__name__}: {exc}']


def _validate_document(doc: Any, expected_key: Optional[dict] = None) -> list[str]:
    if not isinstance(doc, dict):
        return ['document is not an object']
    if doc.get('schema_version') != SCHEMA_VERSION:
        return [f"unsupported schema_version: {doc.get('schema_version')!r}"]
    problems: list[str] = []
    key = doc.get('key')
    if not isinstance(key, dict) or set(key) != {'business_day', 'business_id', 'pair'}:
        return ['invalid key']
    if expected_key is not None and key != expected_key:
        problems.append('key does not match the expected ledger key')
    rounds = doc.get('rounds')
    if not isinstance(rounds, list):
        return problems + ['rounds is not a list']
    seen = set()
    for index, r in enumerate(rounds):
        found = _round_structure(r)
        if not found:
            found = _round_semantics(r)
        problems.extend(f'round[{index}]: {m}' for m in found)
        if not isinstance(r, dict) or not isinstance(r.get('round_id'), str):
            continue
        if r['round_id'] in seen:
            problems.append(f'round[{index}]: duplicate round_id')
        seen.add(r['round_id'])
        if r.get('seq') != index + 1:
            problems.append(f'round[{index}]: seq must be {index + 1}')
        if index < len(rounds) - 1 and isinstance(r.get('global'), dict) and r['global'].get('state') not in G_TERMINAL:
            problems.append(f'round[{index}]: only the last round may be open')
    return problems


def _round_structure(r: Any) -> list[str]:
    if not isinstance(r, dict) or set(r) != _ROUND_KEYS:
        return ['invalid round structure']
    p = []
    if not (isinstance(r['round_id'], str) and r['round_id']):
        p.append('invalid round_id')
    if not isinstance(r['seq'], int) or isinstance(r['seq'], bool):
        p.append('invalid seq')
    if not isinstance(r['created_by'], str):
        p.append('invalid created_by')
    for f in ('created_at', 'rendezvous_deadline_at'):
        if not _num(r[f]):
            p.append(f'invalid {f}')
    for f in ('ready_at', 'deadline_at'):
        if not _num_or_none(r[f]):
            p.append(f'invalid {f}')
    protocol = r['protocol']
    if (not isinstance(protocol, dict) or set(protocol) != {'version', 'params'}
            or not isinstance(protocol['params'], dict)
            or any(not _num(protocol['params'].get(k)) for k in PARAM_KEYS)):
        p.append('invalid protocol')
    members = r['members']
    if (not isinstance(members, list) or len(members) != 2
            or any(not isinstance(m, dict) or set(m) != {'instance', 'alias'} for m in members)):
        p.append('invalid members')
    g = r['global']
    if not isinstance(g, dict) or set(g) != _GLOBAL_KEYS or g['state'] not in (G_OPEN, G_COMPLETED, G_FAILED):
        p.append('invalid global')
    if not isinstance(r['participants'], dict) or any(
            not isinstance(v, dict) or set(v) != _PARTICIPANT_KEYS or v['state'] not in P_TRANSITIONS
            or not _num(v['state_at']) for v in r['participants'].values()):
        p.append('invalid participants')
    if not isinstance(r['attempts'], list) or any(
            not isinstance(a, dict) or set(a) != _ATTEMPT_KEYS or a['status'] not in A_ALL
            or not _num(a['prepared_at']) or not _num_or_none(a['resolved_at']) for a in r['attempts']):
        p.append('invalid attempts')
    if not isinstance(r['late_events'], list) or any(
            not isinstance(e, dict) or set(e) != _LATE_KEYS for e in r['late_events']):
        p.append('invalid late_events')
    return p


def _round_semantics(r: dict) -> list[str]:
    p = []
    instances = [m['instance'] for m in r['members']]
    if len(set(instances)) != 2:
        p.append('members must have two distinct instances')
    aliases = {m['instance']: m['alias'] for m in r['members']}
    parts = r['participants']
    for inst, part in parts.items():
        if inst not in aliases:
            p.append(f'participant {inst!r} is not a member')
        elif part['alias'] != aliases[inst]:
            p.append(f'participant {inst!r} alias does not match the member list')
    attempts = r['attempts']
    prepared_owners = [a['instance'] for a in attempts if a['status'] == A_PREPARED]
    if len(prepared_owners) != len(set(prepared_owners)):
        p.append('an instance has more than one prepared attempt')
    for a in attempts:
        if a['instance'] not in aliases:
            p.append(f"attempt {a['attempt_id']!r} belongs to a non-member")
        if (a['status'] == A_PREPARED) != (a['resolved_at'] is None):
            p.append(f"attempt {a['attempt_id']!r}: resolved_at does not match its status")
        if r['deadline_at'] is not None and a['prepared_at'] > r['deadline_at'] + _EPS:
            p.append(f"attempt {a['attempt_id']!r} was prepared after the deadline")
    if (r['ready_at'] is None) != (r['deadline_at'] is None):
        p.append('ready_at and deadline_at must be set together')
    elif r['ready_at'] is not None:
        budget = r['protocol']['params']['budget']
        if abs(r['deadline_at'] - r['ready_at'] - budget) > _EPS:
            p.append('deadline_at must equal ready_at + budget')
    for inst, part in parts.items():
        if part['state'] in (P_EXECUTING, P_VERIFIED) and r['deadline_at'] is None:
            p.append(f'participant {inst!r} is {part["state"]} before the deadline was set')
        if part['state'] == P_VERIFIED and not any(
                a['instance'] == inst and a['status'] == A_DONE for a in attempts):
            p.append(f'participant {inst!r} is verified without a confirmed_done attempt')
    g = r['global']
    state = g['state']
    if state == G_OPEN:
        if g['reason'] is not None or g['at'] is not None:
            p.append('open round must not carry a reason / terminal time')
        if any(part['state'] == P_FAILED for part in parts.values()):
            p.append('open round has a failed participant (failure-first violated)')
        if any(a['status'] in (A_UNKNOWN, A_ABORTED) for a in attempts):
            p.append('open round has an unknown / aborted attempt')
    else:
        if not isinstance(g['reason'], str) or not g['reason'] or not _num(g['at']):
            p.append('terminal round needs a reason and a terminal time')
        if any(part['state'] not in P_TERMINAL for part in parts.values()):
            p.append('terminal round has a non-terminal participant')
        if state == G_COMPLETED:
            if r['ready_at'] is None:
                p.append('completed before both participants were ready')
            if not all(inst in parts and parts[inst]['state'] == P_VERIFIED for inst in instances):
                p.append('completed without both participants verified')
            if any(a['status'] in (A_PREPARED, A_UNKNOWN) for a in attempts):
                p.append('completed with a pending / unknown attempt')
    return p


# ----------------------------------------------------------------------------------------------------------------------
# 事务前后
# ----------------------------------------------------------------------------------------------------------------------
def validate_transition(old: dict, new: dict) -> list[str]:
    problems = validate_document(new)
    if problems:
        return problems
    if old['key'] != new['key']:
        return ['ledger key changed']
    o_rounds, n_rounds = old['rounds'], new['rounds']
    if len(n_rounds) < len(o_rounds):
        return ['rounds were removed']
    for index, o in enumerate(o_rounds):
        problems.extend(f'round[{index}]: {m}' for m in _round_transition(o, n_rounds[index]))
    appended = n_rounds[len(o_rounds):]
    if len(appended) > 1:
        problems.append('more than one round was appended in one transaction')
    for r in appended:
        parts = r['participants']
        if (len(parts) != 1 or r['created_by'] not in parts or parts[r['created_by']]['state'] != P_JOINED
                or r['attempts'] or r['late_events'] or r['ready_at'] is not None
                or r['global']['state'] != G_OPEN):
            problems.append(f"round {r['round_id']!r} was not appended in its initial state")
    return problems


def _round_transition(o: dict, n: dict) -> list[str]:
    p = []
    for f in _ROUND_IMMUTABLE:
        if o[f] != n[f]:
            p.append(f'{f} changed')
    for f in ('ready_at', 'deadline_at'):
        if o[f] is not None and o[f] != n[f]:
            p.append(f'{f} was rewritten')
    if o['ready_at'] is None and n['ready_at'] is not None:
        if not all(m['instance'] in n['participants'] and n['participants'][m['instance']]['state'] == P_READY
                   for m in n['members']):
            p.append('ready_at was set while a participant was not ready')

    og, ng = o['global'], n['global']
    o_terminal = og['state'] != G_OPEN
    if o_terminal and og != ng:
        p.append('a terminal global state changed')

    # 参与方
    for inst, op_ in o['participants'].items():
        np_ = n['participants'].get(inst)
        if np_ is None:
            p.append(f'participant {inst!r} was removed')
            continue
        if op_['state'] in P_TERMINAL:
            if op_ != np_:
                p.append(f'terminal participant {inst!r} changed')
            continue
        if np_['alias'] != op_['alias']:
            p.append(f'participant {inst!r} alias changed')
        if np_['state'] != op_['state'] and np_['state'] not in P_TRANSITIONS[op_['state']]:
            p.append(f"illegal participant transition {inst!r}: {op_['state']} -> {np_['state']}")
    for inst, np_ in n['participants'].items():
        if inst not in o['participants'] and (o_terminal or np_['state'] != P_JOINED):
            p.append(f'participant {inst!r} cannot join in this state')

    # attempts：只追加；非 prepared 的不可变；prepared 只能原样保留或一次性结算
    oa, na = o['attempts'], n['attempts']
    if len(na) < len(oa):
        p.append('attempts were removed')
    else:
        for index, a in enumerate(oa):
            b = na[index]
            if any(a[f] != b[f] for f in _ATTEMPT_IMMUTABLE):
                p.append(f"attempt {a['attempt_id']!r} identity changed")
            elif a['status'] != A_PREPARED and a != b:
                p.append(f"resolved attempt {a['attempt_id']!r} changed")
            elif a['status'] == A_PREPARED and b['status'] == A_PREPARED and a != b:
                p.append(f"prepared attempt {a['attempt_id']!r} changed")
        for index in range(len(oa), len(na)):
            p.extend(_new_attempt_problems(n, na, index, o_terminal))

    if n['late_events'][:len(o['late_events'])] != o['late_events']:
        p.append('late_events are append-only')
    # 人工确认只对已失败的轮次有意义；在 open 轮次上写确认会提前放行一个还在进行的轮次
    if ng['state'] != G_FAILED and any(e['op'] == LATE_ACK for e in n['late_events'][len(o['late_events']):]):
        p.append('acknowledge_unsafe is only valid on a failed round')
    return p


def _new_attempt_problems(n: dict, attempts: list, index: int, old_terminal: bool) -> list[str]:
    """新追加的尝试：这里集中检查「不重发」和「重试间隔」两条硬规则。"""
    b = attempts[index]
    tag = f"attempt {b['attempt_id']!r}"
    p = []
    if old_terminal or n['global']['state'] != G_OPEN:
        p.append(f'{tag} appended to a terminal round')
    if b['status'] != A_PREPARED:
        p.append(f'{tag} must be appended as prepared')
    part = n['participants'].get(b['instance'])
    if part is None or part['state'] != P_EXECUTING:
        p.append(f'{tag} appended while its owner is not executing')
    params = n['protocol']['params']
    if n['deadline_at'] is None or b['prepared_at'] + params['min_attempt_cost'] > n['deadline_at'] + _EPS:
        p.append(f'{tag} has no budget left')
    prior = [a for a in attempts[:index] if a['instance'] == b['instance'] and a['kind'] == b['kind']]
    if b['seq'] != len(prior) + 1:
        p.append(f'{tag} has a wrong seq')
    if prior:
        last = prior[-1]
        if last['status'] != A_NOT_DONE:
            p.append(f"{tag} resent after a {last['status']} attempt")
        elif b['prepared_at'] + _EPS < last['resolved_at'] + params['retry_wait']:
            p.append(f'{tag} retried before retry_wait elapsed')
    return p
