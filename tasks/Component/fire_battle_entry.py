# This Python file uses the following encoding: utf-8
"""FIRE（Battle Entry Action）点击后的只读状态判据，供 FIRE Batch A 的四个 battle-entry 状态机共用。

只读当前帧：不截图 / 不点击 / 不 sleep。`task` 需混入 `GeneralBattle`（资产来自 `GeneralBattleAssets`）。
"""


def is_new_battle_entry(task) -> bool:
    """当前帧是否已正向进入**一场新战斗**：准备页的「准备」按钮（亮 / 暗）或战斗进行页 `I_BATTLE_INFO`。

    不用 `is_in_battle()`：它是准备 + 战斗 + 结果 + 奖励的整段生命周期判据，结果页 / 奖励页残留会被误判成
    「已进入新战斗」（D001 补记「Battle Lifecycle Detector ≠ New Battle Entry Detector」）。也不取
    `is_in_prepare()` 里左下角的 `I_BUFF` / `I_PRESET*`：挑战页 / 组队房间同位置是否出现同类图标没有证据。
    准备页在点「准备」前后必有亮 / 暗准备按钮之一，所以这个子集足以覆盖准备页。
    """
    return (
        task.appear(task.I_PREPARE_HIGHLIGHT)
        or task.appear(task.I_PREPARE_DARK)
        or task.appear(task.I_BATTLE_INFO)
    )


def is_battle_result_residue(task) -> bool:
    """当前帧是否是上一场的结果 / 奖励页（异常：不能当成功，也不能在其上点 FIRE）。"""
    return (
        task.appear(task.I_WIN)
        or task.appear(task.I_DE_WIN)
        or task.appear(task.I_FALSE)
        or task.appear(task.I_REWARD)
        or task.appear(task.I_REWARD_GOLD)
    )
