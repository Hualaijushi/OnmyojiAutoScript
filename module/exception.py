class CampaignEnd(Exception):
    pass


class MapDetectionError(Exception):
    pass


class MapWalkError(Exception):
    pass


class MapEnemyMoved(Exception):
    pass


class CampaignNameError(Exception):
    pass


class ScriptError(Exception):
    # This is likely to be a mistake of developers, but sometimes a random issue
    pass


class ScriptEnd(Exception):
    pass


class GameStuckError(Exception):
    pass


class GameBugError(Exception):
    # An error has occurred in Azur Lane game client. Alas is unable to handle.
    # A restart should fix it.
    pass


class GameTooManyClickError(Exception):
    pass


class EmulatorNotRunningError(Exception):
    pass


class GameNotRunningError(Exception):
    pass


class GamePageUnknownError(Exception):
    pass


class CourtyardStallRecoveryExhausted(GamePageUnknownError):
    """返回庭院连续无进展，额外兜底已用尽。"""


class RequestHumanTakeover(Exception):
    # Request human takeover
    # Alas is unable to handle such error, probably because of wrong settings.
    pass

class TaskEnd(Exception):
    pass


class OcrUnavailableError(Exception):
    """识别暂时不可用，由任务边界延期或协同恢复。"""


class ImageFrameExpiredError(Exception):
    """旧截图缓存失效且缺少原图，不能继续使用旧坐标。"""
