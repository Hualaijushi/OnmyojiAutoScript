# This Python file uses the following encoding: utf-8

"""棋局 Frame 运行时需要、而本地 BaseTask 没有的入口。

上游把 ``runframe`` 放在公共 BaseTask 里；本地不扩 BaseTask（它已经很大，且只有棋局用 Frame），
所以放在棋局自己的 mixin 里，函数体与上游 73d4ae84 的 ``BaseTask.runframe`` 一致。
"""

from module.atom.frame import FrameResult, RuleFrame
from module.exception import ScriptError


class ChessFrameCompatMixin:
    def runframe(self, target: RuleFrame, *range_results, interval=None, threshold=None) -> FrameResult:
        """读取 frame.data（坐标、裁剪图、文字）；仅 Click 显式 True 点击，其余参数可选比对。"""
        if not isinstance(target, RuleFrame):
            raise ScriptError('runframe 的第一个参数必须是 RuleFrame')
        try:
            return target.run(self, *range_results, interval=interval, threshold=threshold)
        except (TypeError, ValueError) as error:
            raise ScriptError(f'runframe 配置或区域无效: {error}') from error
