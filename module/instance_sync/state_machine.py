# This Python file uses the following encoding: utf-8
"""双实例同步账本的状态机：全部是对「账本文档（dict）」的纯函数，不碰文件、时钟、设备。

调用方式：`Ledger.transact` 把账本深拷贝后交给 `op_*`，`op_*` 原地修改并返回 `OpResult`；
变更是否合法由 `invariants.validate_transition` 在写盘前再独立校验一遍。
所以「操作函数写错」不会直接变成「坏账本落盘」。

约定：
- 被拒绝的操作不修改文档（`op_fail` / `op_resolve_attempt` 在终态后只追加 late_events）。
- 时间 `now` 由事务在锁内取一次传入，所有判断都对这一个值。
- 一个账本文件 = 一个业务日 × 一个业务 × 一对账号；`rounds` 只追加，只有最后一轮可能是 open。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1

# 整轮状态
G_OPEN = 'open'
G_COMPLETED = 'completed'
G_FAILED = 'failed'
G_TERMINAL = (G_COMPLETED, G_FAILED)

# 参与方（本地）状态
P_JOINED = 'joined'
P_READY = 'ready'
P_EXECUTING = 'executing'
P_VERIFIED = 'verified'
P_FAILED = 'failed'
P_TERMINAL = (P_VERIFIED, P_FAILED)
P_TRANSITIONS = {
    P_JOINED: (P_READY, P_FAILED),
    P_READY: (P_EXECUTING, P_FAILED),
    P_EXECUTING: (P_VERIFIED, P_FAILED),
    P_VERIFIED: (),
    P_FAILED: (),
}

# 单次尝试（attempt）状态。prepared 是「点击前先写下的意图」
A_PREPARED = 'prepared'
A_DONE = 'confirmed_done'
A_NOT_DONE = 'confirmed_not_done'
A_ABORTED = 'aborted_before_dispatch'
A_UNKNOWN = 'unknown'
A_RESOLVED = (A_DONE, A_NOT_DONE, A_ABORTED, A_UNKNOWN)
A_ALL = (A_PREPARED,) + A_RESOLVED

# 失败轮次的分类：safe = 没有任何可能已经发出去的请求，可以开新轮
SAFE = 'safe'
UNSAFE = 'unsafe'

# 失败原因
R_RENDEZVOUS_TIMEOUT = 'rendezvous_timeout'
R_BUDGET_TIMEOUT = 'budget_timeout'
R_HANDSHAKE = 'handshake_mismatch'
R_PREPARE_FAILED = 'prepare_failed'
R_ATTEMPT_UNKNOWN = 'attempt_unknown'
R_ATTEMPT_ABORTED = 'attempt_aborted'
R_NO_BUDGET = 'retry_budget_exhausted'
R_VERIFY_FAILED = 'verify_failed'
R_EXCEPTION = 'exception'

# op_enter 的结果
OUT_CREATED = 'created'
OUT_JOINED = 'joined'
OUT_RESUMED = 'resumed'
OUT_COMPLETED = 'already_completed'
OUT_MANUAL = 'manual_required'
OUT_CAP = 'round_cap'
OUT_REJECTED = 'handshake_mismatch'

PARAM_KEYS = ('retry_wait', 'budget', 'min_attempt_cost', 'max_rounds')

# late_events 里的人工确认事件：只表示「人已经核对过游戏、同意当天再开新轮」，不改变任何状态
LATE_ACK = 'acknowledge_unsafe'

_BUSINESS_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
_BUSINESS_DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


@dataclass(frozen=True)
class OpResult:
    ok: bool
    reason: str = ''
    value: Any = None


@dataclass(frozen=True)
class Actor:
    """操作者：实例名 + 本进程会话 id。会话 id 变了说明有更新的进程接管了该实例。"""
    instance: str
    session_id: str


def _ok(value=None) -> OpResult:
    return OpResult(True, '', value)


def _no(reason: str, value=None) -> OpResult:
    return OpResult(False, reason, value)


# ----------------------------------------------------------------------------------------------------------------------
# 键 / 文档构造
# ----------------------------------------------------------------------------------------------------------------------
def canonical_members(members: Iterable[tuple[str, str]]) -> list[dict]:
    """两个成员 (instance, alias) → 按 (alias, instance) 排序的规范列表。两端算出同一个结果，与谁发起无关。"""
    pairs = sorted((str(alias), str(instance)) for instance, alias in members)
    if len(pairs) != 2:
        raise ValueError('members must contain exactly two (instance, alias)')
    if any(not alias or not instance for alias, instance in pairs):
        raise ValueError('instance and alias must be non-empty')
    if pairs[0][0] == pairs[1][0] or pairs[0][1] == pairs[1][1]:
        raise ValueError('instance and alias of the two members must differ')
    return [{'instance': instance, 'alias': alias} for alias, instance in pairs]


def make_key(business_day: str, business_id: str, members: list[dict]) -> dict:
    if not _BUSINESS_DAY_RE.match(business_day or ''):
        raise ValueError(f'invalid business_day: {business_day!r}')
    if not _BUSINESS_ID_RE.match(business_id or ''):
        raise ValueError(f'invalid business_id: {business_id!r}')
    return {'business_day': business_day, 'business_id': business_id,
            'pair': sorted(m['alias'] for m in members)}


def ledger_filename(key: dict) -> str:
    """文件名只含日期、业务 id 和别名对的哈希：别名里的任意字符不会进文件系统。"""
    digest = hashlib.sha1(json.dumps(key['pair'], ensure_ascii=False).encode('utf-8')).hexdigest()[:8]
    return f"{key['business_day']}_{key['business_id']}_{digest}.json"


def new_document(key: dict) -> dict:
    return {'schema_version': SCHEMA_VERSION, 'key': key, 'rounds': []}


def check_params(params: Mapping[str, Any]) -> dict:
    missing = [k for k in PARAM_KEYS if k not in params]
    if missing:
        raise ValueError(f'protocol params missing: {missing}')
    out = {}
    for k in PARAM_KEYS:
        v = params[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f'protocol param {k} must be a non-negative number: {v!r}')
        out[k] = v
    if out['budget'] <= 0 or out['max_rounds'] < 1:
        raise ValueError('protocol params: budget must be > 0 and max_rounds >= 1')
    return out


def make_protocol(params: Mapping[str, Any]) -> dict:
    return {'version': PROTOCOL_VERSION, 'params': check_params(params)}


def _new_participant(alias: str, session_id: str, now: float) -> dict:
    return {'alias': alias, 'session_id': session_id, 'state': P_JOINED, 'state_at': now, 'failure': None}


def _new_round(*, round_id: str, seq: int, actor: Actor, now: float, members: list[dict], protocol: dict,
               rendezvous_timeout: float) -> dict:
    return {
        'round_id': round_id,
        'seq': seq,
        'created_by': actor.instance,
        'created_at': now,
        'protocol': protocol,
        'members': members,
        'rendezvous_deadline_at': now + rendezvous_timeout,
        'ready_at': None,
        'deadline_at': None,
        'global': {'state': G_OPEN, 'reason': None, 'at': None, 'by': None, 'detail': ''},
        'participants': {actor.instance: _new_participant(_alias_of(members, actor.instance), actor.session_id, now)},
        'attempts': [],
        'late_events': [],
    }


def _alias_of(members: list[dict], instance: str) -> str:
    for m in members:
        if m['instance'] == instance:
            return m['alias']
    raise ValueError(f'{instance!r} is not a member of this pair')


def _peer_of(members: list[dict], instance: str) -> str:
    return next(m['instance'] for m in members if m['instance'] != instance)


# ----------------------------------------------------------------------------------------------------------------------
# 内部变更原语
# ----------------------------------------------------------------------------------------------------------------------
def _fail_round(r: dict, now: float, reason: str, by: Optional[str] = None, detail: str = '') -> None:
    """open → failed，并把所有未到终态的参与方一起置 failed（失败优先，不依赖对端配合）。"""
    g = r['global']
    if g['state'] != G_OPEN:
        return
    g.update(state=G_FAILED, reason=reason, at=now, by=by, detail=detail)
    for p in r['participants'].values():
        if p['state'] not in P_TERMINAL:
            p.update(state=P_FAILED, state_at=now, failure=reason)


def expire(r: dict, now: float) -> bool:
    """按时间推进：会合窗口（创建 → 双方 ready）和总预算（ready_at → deadline_at）。返回是否改动。

    任何一方的任何事务都会顺带做这件事，所以不需要额外的监工进程。
    """
    if r['global']['state'] != G_OPEN:
        return False
    if r['ready_at'] is None:
        if now >= r['rendezvous_deadline_at']:
            _fail_round(r, now, R_RENDEZVOUS_TIMEOUT)
            return True
    elif now > r['deadline_at']:
        _fail_round(r, now, R_BUDGET_TIMEOUT)
        return True
    return False


def _try_complete(r: dict, now: float) -> None:
    """全局完成的唯一入口：双方都 verified，且没有未决 / 未知的尝试。"""
    if r['global']['state'] != G_OPEN or r['ready_at'] is None:
        return
    parts = r['participants']
    if not all(m['instance'] in parts and parts[m['instance']]['state'] == P_VERIFIED for m in r['members']):
        return
    if any(a['status'] in (A_PREPARED, A_UNKNOWN) for a in r['attempts']):
        return
    r['global'].update(state=G_COMPLETED, reason=G_COMPLETED, at=now)


def _late(r: dict, now: float, actor: Actor, op: str, detail: str = '') -> None:
    r['late_events'].append({'at': now, 'instance': actor.instance, 'op': op, 'detail': detail})


def classify_failed_round(r: dict) -> str:
    """失败轮次里只要有任何尝试可能已经发出去（prepared / unknown / confirmed_done），就是 unsafe。"""
    for a in r['attempts']:
        if a['status'] not in (A_NOT_DONE, A_ABORTED):
            return UNSAFE
    return SAFE


def is_acknowledged(r: dict) -> bool:
    return any(e['op'] == LATE_ACK for e in r['late_events'])


def _target(doc: dict, round_id: str):
    """只允许操作最后一轮；旧 round_id 一律拒绝，不自动切到新轮。"""
    if not doc['rounds']:
        return None, _no('no_round')
    r = doc['rounds'][-1]
    if r['round_id'] != round_id:
        return None, _no('round_mismatch')
    return r, None


def _live(doc: dict, now: float, actor: Actor, round_id: str):
    """通用前置：定位轮次 → 推进时间 → 要求仍是 open 且本会话仍是该实例的当前会话。"""
    r, err = _target(doc, round_id)
    if err:
        return None, None, err
    expire(r, now)
    p = r['participants'].get(actor.instance)
    if p is not None and p['session_id'] != actor.session_id:
        return None, None, _no('session_superseded')
    if r['global']['state'] != G_OPEN:
        return None, None, _no('terminal', r['global']['reason'])
    if p is None:
        return None, None, _no('not_participant')
    return r, p, None


# ----------------------------------------------------------------------------------------------------------------------
# 操作
# ----------------------------------------------------------------------------------------------------------------------
def op_enter(doc: dict, now: float, actor: Actor, *, members: list[dict], protocol: dict, rendezvous_timeout: float,
             new_round_id: str) -> OpResult:
    """任务启动时的唯一入口：按当天账本里最近一轮的状态决定「新建 / 加入 / 恢复 / 已完成 / 需人工 / 达上限」。"""
    max_rounds = protocol['params']['max_rounds']
    rounds = doc['rounds']
    if rounds:
        last = rounds[-1]
        expire(last, now)
        state = last['global']['state']
        if state == G_OPEN:
            if last['members'] != members or last['protocol'] != protocol:
                # 配对声明 / 协议参数不一致（加入和恢复都校验）：这一轮不可能成功，直接失败，创建者不必干等 600 秒
                _fail_round(last, now, R_HANDSHAKE, by=actor.instance)
                return _no(R_HANDSHAKE, {'outcome': OUT_REJECTED, 'round_id': last['round_id'], 'seq': last['seq']})
            part = last['participants'].get(actor.instance)
            if part is None:
                last['participants'][actor.instance] = _new_participant(_alias_of(members, actor.instance),
                                                                          actor.session_id, now)
                return _ok({'outcome': OUT_JOINED, 'round_id': last['round_id'], 'seq': last['seq']})
            part['session_id'] = actor.session_id
            return _ok({'outcome': OUT_RESUMED, 'round_id': last['round_id'], 'seq': last['seq']})
        if state == G_COMPLETED:
            return _ok({'outcome': OUT_COMPLETED, 'round_id': last['round_id'], 'seq': last['seq']})
        if classify_failed_round(last) == UNSAFE and not is_acknowledged(last):
            return _no('unsafe_prior_round', {'outcome': OUT_MANUAL, 'round_id': last['round_id'], 'seq': last['seq']})
        if len(rounds) >= max_rounds:
            return _no('round_cap', {'outcome': OUT_CAP, 'round_id': last['round_id'], 'seq': last['seq']})
    seq = len(rounds) + 1
    rounds.append(_new_round(round_id=new_round_id, seq=seq, actor=actor, now=now, members=members, protocol=protocol,
                             rendezvous_timeout=rendezvous_timeout))
    return _ok({'outcome': OUT_CREATED, 'round_id': new_round_id, 'seq': seq})


def op_acknowledge_unsafe(doc: dict, now: float, actor: Actor, *, reason: str = '') -> OpResult:
    """人工确认：最后一轮可能已经发出的请求我核对过了，当天可以再开新轮。

    只在最后一轮的 late_events 里追加一条事件，整轮状态和 attempts 原样保留（证据不丢）；
    之后 `op_enter` 不再把这一轮当作拦截条件。不绕过每天的轮次上限。
    不适用的情况都只返回原因、不改账本（过期的 open 轮次会先被判 failed，这是时间推进，不算本操作的改动）。
    """
    if not doc['rounds']:
        return _no('no_round')
    last = doc['rounds'][-1]
    if actor.instance not in {m['instance'] for m in last['members']}:
        return _no('not_member')
    expire(last, now)
    info = {'round_id': last['round_id'], 'seq': last['seq']}
    state = last['global']['state']
    if state == G_OPEN:
        return _no('round_open', info)
    if state == G_COMPLETED:
        return _no('already_completed', info)
    if classify_failed_round(last) == SAFE or is_acknowledged(last):
        return _no('not_unsafe', info)
    _late(last, now, actor, LATE_ACK, reason)
    return _ok(info)


def op_poll(doc: dict, now: float) -> OpResult:
    """只推进时间（会合 / 预算超时），用于轮询和协作式取消检查。"""
    if doc['rounds']:
        expire(doc['rounds'][-1], now)
    return _ok()


def op_ready(doc: dict, now: float, actor: Actor, *, round_id: str) -> OpResult:
    """joined → ready。第二个 ready 的同一事务里写入 ready_at / deadline_at，之后不可再改。"""
    r, p, err = _live(doc, now, actor, round_id)
    if err:
        return err
    if p['state'] != P_JOINED:
        return _no('bad_state', p['state'])
    p.update(state=P_READY, state_at=now)
    parts = r['participants']
    if all(m['instance'] in parts and parts[m['instance']]['state'] == P_READY for m in r['members']):
        r['ready_at'] = now
        r['deadline_at'] = now + r['protocol']['params']['budget']
    return _ok({'deadline_at': r['deadline_at']})


def op_start(doc: dict, now: float, actor: Actor, *, round_id: str) -> OpResult:
    """ready → executing，要求双方已 ready（deadline_at 已写入）。"""
    r, p, err = _live(doc, now, actor, round_id)
    if err:
        return err
    if p['state'] != P_READY:
        return _no('bad_state', p['state'])
    if r['deadline_at'] is None:
        return _no('peer_not_ready')
    p.update(state=P_EXECUTING, state_at=now)
    return _ok()


def op_begin_attempt(doc: dict, now: float, actor: Actor, *, round_id: str, kind: str, attempt_id: str) -> OpResult:
    """点击前先持久化「发送意图」。所有「能不能再发一次」的规则都在这里和校验器里，不靠调用方自觉。"""
    r, p, err = _live(doc, now, actor, round_id)
    if err:
        return err
    if p['state'] != P_EXECUTING:
        return _no('bad_state', p['state'])
    mine = [a for a in r['attempts'] if a['instance'] == actor.instance]
    if any(a['status'] == A_PREPARED for a in mine):
        return _no('attempt_pending')
    same_kind = [a for a in mine if a['kind'] == kind]
    params = r['protocol']['params']
    earliest = now
    if same_kind:
        last = same_kind[-1]
        if last['status'] != A_NOT_DONE:
            # done / unknown / aborted 之后一律不重发：unknown 绝不能自动重发
            return _no('no_resend', last['status'])
        earliest = last['resolved_at'] + params['retry_wait']
    if earliest + params['min_attempt_cost'] > r['deadline_at']:
        return _no('no_budget', {'earliest_at': earliest})
    if now < earliest:
        return _no('too_early', {'earliest_at': earliest})
    r['attempts'].append({
        'attempt_id': attempt_id, 'instance': actor.instance, 'kind': kind, 'seq': len(same_kind) + 1,
        'prepared_at': now, 'status': A_PREPARED, 'resolved_at': None, 'evidence': None,
    })
    return _ok({'attempt_id': attempt_id})


def op_resolve_attempt(doc: dict, now: float, actor: Actor, *, round_id: str, attempt_id: str, status: str,
                       evidence: str = '') -> OpResult:
    """记录一次尝试的结果。游戏里发生过的事是事实：整轮已终态时仍然记录（并追加 late_events）。"""
    if status not in A_RESOLVED:
        raise ValueError(f'invalid attempt status: {status!r}')
    r, err = _target(doc, round_id)
    if err:
        return err
    expire(r, now)
    p = r['participants'].get(actor.instance)
    if p is None:
        return _no('not_participant')
    if p['session_id'] != actor.session_id:
        return _no('session_superseded')
    attempt = next((a for a in r['attempts'] if a['attempt_id'] == attempt_id and a['instance'] == actor.instance), None)
    if attempt is None:
        return _no('no_attempt')
    if attempt['status'] != A_PREPARED:
        return _no('already_resolved', attempt['status'])
    attempt.update(status=status, resolved_at=now, evidence=evidence)
    if r['global']['state'] != G_OPEN:
        _late(r, now, actor, 'resolve_attempt', f'{attempt_id}:{status}')
    elif status == A_UNKNOWN:
        _fail_round(r, now, R_ATTEMPT_UNKNOWN, by=actor.instance, detail=evidence)
    elif status == A_ABORTED:
        _fail_round(r, now, R_ATTEMPT_ABORTED, by=actor.instance, detail=evidence)
    return _ok()


def op_verify(doc: dict, now: float, actor: Actor, *, round_id: str) -> OpResult:
    """executing → verified（游戏内二次核验已通过）。双方都 verified 的同一事务里写 completed。"""
    r, p, err = _live(doc, now, actor, round_id)
    if err:
        return err
    if p['state'] != P_EXECUTING:
        return _no('bad_state', p['state'])
    mine = [a for a in r['attempts'] if a['instance'] == actor.instance]
    if any(a['status'] != A_DONE and a['status'] != A_NOT_DONE for a in mine):
        return _no('attempt_unresolved')
    if not any(a['status'] == A_DONE for a in mine):
        return _no('no_done_attempt')
    p.update(state=P_VERIFIED, state_at=now)
    _try_complete(r, now)
    return _ok({'completed': r['global']['state'] == G_COMPLETED})


def op_fail(doc: dict, now: float, actor: Actor, *, round_id: str, reason: str, detail: str = '') -> OpResult:
    """本方报告不可恢复错误：整轮同一事务置 failed。终态之后的报告只追加 late_events，不改任何状态。"""
    r, err = _target(doc, round_id)
    if err:
        return err
    expire(r, now)
    p = r['participants'].get(actor.instance)
    if p is None:
        return _no('not_participant')
    if p['session_id'] != actor.session_id:
        return _no('session_superseded')
    if r['global']['state'] != G_OPEN or p['state'] in P_TERMINAL:
        _late(r, now, actor, 'fail', f'{reason}:{detail}' if detail else reason)
        return _no('terminal', r['global']['reason'])
    _fail_round(r, now, reason, by=actor.instance, detail=detail)
    return _ok()


# ----------------------------------------------------------------------------------------------------------------------
# 只读视图：适配器 / 调用方拿到的是快照，不是可写的账本结构
# ----------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AttemptView:
    attempt_id: str
    kind: str
    seq: int
    status: str
    prepared_at: float
    resolved_at: Optional[float]


@dataclass(frozen=True)
class RoundView:
    round_id: str
    seq: int
    rounds_count: int
    global_state: str
    global_reason: Optional[str]
    rendezvous_deadline_at: float
    ready_at: Optional[float]
    deadline_at: Optional[float]
    params: Mapping[str, Any]
    me_state: Optional[str]
    peer_state: Optional[str]
    my_attempts: tuple
    peer_attempts: tuple
    classification: Optional[str]

    @property
    def terminal(self) -> bool:
        return self.global_state in G_TERMINAL


def _attempt_views(attempts: list[dict], instance: str) -> tuple:
    return tuple(AttemptView(a['attempt_id'], a['kind'], a['seq'], a['status'], a['prepared_at'], a['resolved_at'])
                 for a in attempts if a['instance'] == instance)


def build_view(doc: dict, instance: str) -> Optional[RoundView]:
    if not doc['rounds']:
        return None
    r = doc['rounds'][-1]
    peer = _peer_of(r['members'], instance)
    parts = r['participants']
    failed = r['global']['state'] == G_FAILED
    return RoundView(
        round_id=r['round_id'],
        seq=r['seq'],
        rounds_count=len(doc['rounds']),
        global_state=r['global']['state'],
        global_reason=r['global']['reason'],
        rendezvous_deadline_at=r['rendezvous_deadline_at'],
        ready_at=r['ready_at'],
        deadline_at=r['deadline_at'],
        params=MappingProxyType(dict(r['protocol']['params'])),
        me_state=parts[instance]['state'] if instance in parts else None,
        peer_state=parts[peer]['state'] if peer in parts else None,
        my_attempts=_attempt_views(r['attempts'], instance),
        peer_attempts=_attempt_views(r['attempts'], peer),
        classification=classify_failed_round(r) if failed else None,
    )
