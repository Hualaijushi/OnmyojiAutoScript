"""活动数值解析和成功判据，不访问设备或服务。"""

import re
import unicodedata

from module.exception import ScriptError


class EventGoalError(ScriptError):
    """活动未确认完成，不能通过重启或次数上限伪造成功。"""


def parse_ticket_value(text: str) -> int | None:
    normalized = re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(text)))
    match = re.fullmatch(r'(\d{1,2})/50', normalized, flags=re.ASCII)
    if match and 0 <= int(match[1]) <= 50:
        return int(match[1])
    return None


def event_complete(state: dict, group: int) -> bool:
    node = state.get('event_groups', {}).get(str(group), {})
    # 人工完成必须有当日独立来源标记，不能伪造成OCR读值或跨日沿用。
    if (node.get('completion_source') == 'user_confirmed'
            and str(node.get('manual_completed_at', '')).startswith(str(state.get('date')) + 'T')):
        return True
    roles = node.get('roles', {})
    return all(roles.get(role, {}).get('reached') is True
               and roles[role].get('value') == 50 for role in ('leader', 'member_1', 'member_2'))
