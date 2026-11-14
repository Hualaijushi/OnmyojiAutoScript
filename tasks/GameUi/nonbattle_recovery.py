"""返回庭院无进展时的非战斗兜底。"""

from module.exception import GamePageUnknownError, RequestHumanTakeover
from tasks.GameUi import page as pages


class _ProtectedPage(Exception):
    pass


def _is_protected_frame(task):
    protected = (pages.page_battle, pages.page_battle_prepare, pages.page_battle_result,
                 pages.page_reward, pages.page_battle_team, pages.page_battle_team_exit,
                 pages.page_login)
    return any(local is not None and task.match_page_once(local)
               for local in (task.navigator.resolve_page(page) for page in protected))


def ensure_nonbattle_frame(task):
    """仅检查当前画面，不在受保护页面执行庭院恢复。"""
    if _is_protected_frame(task):
        raise RequestHumanTakeover('检测到战斗、结算、登录器或组队页面，停止额外庭院恢复')


def is_protected_page_now(task):
    """使用新画面判断是否需要退出额外兜底。"""
    task.screenshot()
    return _is_protected_frame(task)


def try_unknown_closer_once(task):
    """排除受保护页面后，调用一次原有未知页兜底。"""
    screenshot = task.screenshot
    had_override = 'screenshot' in task.__dict__
    previous_override = task.__dict__.get('screenshot')

    def guarded_screenshot():
        result = screenshot()
        if _is_protected_frame(task):
            raise _ProtectedPage
        return result

    task.screenshot = guarded_screenshot
    try:
        task.screenshot()
        return task.close_unknown_pages(skip_first_screenshot=True)
    except _ProtectedPage:
        return None
    except GamePageUnknownError:
        return False
    finally:
        if had_override:
            task.screenshot = previous_override
        else:
            del task.screenshot


def recover_nonbattle_courtyard(task, *, timeout=20):
    """先执行正常导航；仅在返回庭院卡住时使用原有兜底。"""
    task.screenshot()
    ensure_nonbattle_frame(task)
    return bool(task.goto_page(pages.page_main, timeout=timeout))
