"""式神活动三种玩法共用运行能力。"""

from datetime import datetime

from cached_property import cached_property

from module.atom.image import RuleImage
from module.base.protect import random_sleep
from module.exception import TaskEnd
from module.logger import logger
from tasks.ActivityShikigami.assets import ActivityShikigamiAssets
from tasks.ActivityShikigami.config import ActivityShikigami, BATTLE_TYPES
from tasks.Component.BaseActivity.base_activity import BaseActivity
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralBattle.general_battle import BattleAction, BattleContext, GeneralBattle
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GameUi.game_ui import GameUi
import tasks.ActivityShikigami.page as pages


class ActivityResourceNotEnough(Exception):
    """当前子玩法资源不足，可以切换到下一项。"""


class BaseAct(GameUi, GeneralBattle, SwitchSoul, BaseActivity, ActivityShikigamiAssets):
    """统一保存计数、软时间边界、随机休息、御魂和战斗配置。"""

    def __init__(self, config, device):
        super().__init__(config, device)
        self.action_count = {name: 0 for name in BATTLE_TYPES}
        climb_consumables = ('pass', 'ap', 'boss', 'ap100', 'penta_pass')
        self.climb_consumable_count = {
            name: -1 for name in climb_consumables
        }
        self.climb_pending_consumption = {
            name: 0 for name in climb_consumables
        }
        self.penta_pass_active = False
        self.switched_soul = {name: False for name in BATTLE_TYPES}
        self.current_action_type = ''
        self.activity_time_reached = False
        # 某个玩法把「宏观空闲（macro idle）」交给 Fatigue 安全节点接管后置 True，
        # 此时 `prepare_next_action` 不再叠加旧的 `random_sleep`（避免两个 macro-idle owner）。
        # 当前仅爬塔线（`NormalClimbAct.run_climb`）启用；大富翁 / 伪神降临线保持 random_sleep。
        #
        # ownership 契约：同一个 `ScriptTask` 实例会按 `task_sequence_v` 顺序连跑多条玩法线，
        # 因此**每条线都必须在自己的 `run_*` 入口显式声明** owner，不能沿用上一条线的残留值
        # （否则「爬塔 → 伪神降临」会让伪神线既没有 Fatigue 安全节点、也跳过 random_sleep，
        # 出现零 macro-idle owner）。这里的值只是实例初始默认，不承担线间切换职责。
        self._fatigue_owns_macro_idle = False

    @cached_property
    def conf(self) -> ActivityShikigami:
        return self.config.model.activity_shikigami

    @property
    def scheduled_task_name(self) -> str:
        return 'ActivityShikigami'

    def before_run(self):
        pages.page_battle_result = self.navigator.resolve_page(pages.page_battle_result)
        pages.page_battle_result.recognizer = pages.any_of(
            self.I_UI_BACK_RED,
            pages.page_battle_result.recognizer,
        )

    def _exit_matcher(self):
        if self.current_action_type == 'fakegod':
            return self.I_FG_ACT_FIRE
        if self.current_action_type == 'boss':
            return self.I_AS_BOSS_FIRE
        if self.current_action_type in ('ap', 'pass', 'ap100'):
            return self.I_ACT_FIRE
        return None

    def _is_active_battle_entry(self) -> bool:
        """当前 fresh frame 是否**确实已进入一场新战斗**（准备页 / 战斗进行页）。

        **不是** `GeneralBattle.is_in_battle()`：后者是「准备 + 战斗 + 结果 + 奖励」整个战斗
        生命周期 detector，OR 里含失败横幅 `I_FALSE`、胜负横幅 `I_WIN` / `I_DE_WIN`、奖励页
        `I_REWARD` / `I_REWARD_GOLD`。本期活动战斗结束后是一个「活动专用结算弹窗」，若用宽
        detector 判「新战斗已开始」，结算弹窗 / 上一场结果残留会被误判成已进入下一场战斗
        （与 `docs/DECISIONS.md` D001 补记「Battle Lifecycle Detector ≠ New Battle Entry
        Detector」一致，RealmRaid `_is_active_battle_entry()` 同款）。

        这里只取窄 active-battle-entry positive：`is_in_prepare()`（`I_BUFF` /
        `I_PREPARE_HIGHLIGHT` / `I_PREPARE_DARK` / `I_PRESET` / `I_PRESET_WIT_NUMBER`）或
        `is_in_real_battle()`（`I_BATTLE_INFO`）——都是 GeneralBattle 已有的窄 detector、不含
        result / reward marker。只读当前帧：不截图 / 不点击 / 不 sleep。
        """
        return self.is_in_prepare(False) or self.is_in_real_battle(False)

    def _handle_result(self, context: BattleContext, config: GeneralBattleConfig) -> BattleAction:
        if self.current_action_type == 'boss':
            self.appear_then_click(self.I_UI_BACK_RED, interval=1.5)
        return super()._handle_result(context, config)

    def battle_config(self, action_type: str) -> GeneralBattleConfig:
        return getattr(self.conf, f'{action_type}_battle_conf')

    def action_limit(self, action_type: str) -> int:
        return self.conf.general_config.limit_for(action_type)

    def time_limit_reached(self) -> bool:
        reached = datetime.now() - self.start_time >= self.conf.general_config.limit_time_v
        if reached and not self.activity_time_reached:
            logger.info('ActivityShikigami task time limit reached; stop before next action')
        self.activity_time_reached = self.activity_time_reached or reached
        return self.activity_time_reached

    def prepare_next_action(self, action_type: str) -> bool:
        """下一次骰子/战斗/行动的软停止节点：次数上限 / 墙钟时限 / 行动计数 / current_action_type。

        宏观空闲（macro idle）的处理分两种：`_fatigue_owns_macro_idle` 为真的玩法（爬塔线）
        已把它交给 Fatigue 安全节点（`NormalClimbAct._activity_challenge_safe_break` 里的
        `try_fatigue_break`），此处**不再**叠加旧的 `random_sleep`（否则同一 cycle 出现两个
        macro-idle owner）；大富翁 / 伪神降临线不启用 Fatigue，仍走 `random_sleep`。
        """
        limit = self.action_limit(action_type)
        if limit <= 0 or self.action_count[action_type] >= limit:
            logger.info(
                f'Activity action {action_type} count limit reached: '
                f'{self.action_count[action_type]}/{limit}'
            )
            return False
        if self.time_limit_reached():
            return False

        if self.conf.general_config.random_sleep and not self._fatigue_owns_macro_idle:
            random_sleep(probability=0.2)
            if self.time_limit_reached():
                return False

        self.current_action_type = action_type
        return True

    def record_action(self, action_type: str):
        self.action_count[action_type] += 1
        logger.info(
            f'Activity action {action_type} count: '
            f'{self.action_count[action_type]}/{self.action_limit(action_type)}'
        )

    def switch_soul_for(
        self,
        action_type: str,
        enter_button: RuleImage,
        *,
        return_page=None,
        exit_records: bool = False,
    ):
        """按六种战斗字段切换一次御魂。"""
        if self.switched_soul[action_type]:
            return
        conf = self.conf.switch_soul_config
        enable_number = getattr(conf, f'enable_switch_{action_type}')
        enable_name = getattr(conf, f'enable_switch_{action_type}_by_name')
        self.switched_soul[action_type] = True
        if not enable_number and not enable_name:
            return

        conf.validate_switch_soul()
        logger.hr(f'Start switch soul: {action_type}', 2)
        self.ui_click(enter_button, stop=self.I_CHECK_RECORDS, interval=1)
        if enable_name:
            group, team = getattr(conf, f'{action_type}_group_team_name').split(',', 1)
            self.run_switch_soul_by_name(group.strip(), team.strip())
        elif enable_number:
            self.run_switch_soul(getattr(conf, f'{action_type}_group_team'))

        if exit_records:
            self.exit_shikigami_records()
        elif return_page is not None:
            self.goto_page(return_page)

    def switch_soul_for_from_courtyard(self, action_type: str):
        """从庭院进入式神录，按原配置切换指定玩法的御魂预设。"""
        if self.switched_soul[action_type]:
            return
        conf = self.conf.switch_soul_config
        enable_number = getattr(conf, f'enable_switch_{action_type}')
        enable_name = getattr(conf, f'enable_switch_{action_type}_by_name')
        self.switched_soul[action_type] = True
        if not enable_number and not enable_name:
            return

        conf.validate_switch_soul()
        logger.hr(f'Start switch soul from courtyard: {action_type}', 2)
        self.goto_page(pages.page_main)
        self.goto_page(pages.page_shikigami_records)
        if enable_name:
            group, team = getattr(conf, f'{action_type}_group_team_name').split(',', 1)
            self.run_switch_soul_by_name(group.strip(), team.strip())
        elif enable_number:
            self.run_switch_soul(getattr(conf, f'{action_type}_group_team'))

        self.exit_shikigami_records()
        self.goto_page(pages.page_main)

    def finish_activity_task(self):
        self.goto_page(pages.page_main)
        if self.conf.general_config.active_souls_clean:
            self.set_next_run(task='SoulsTidy', success=False, finish=False, target=datetime.now())
        self.set_next_run(task=self.scheduled_task_name, success=True)
        raise TaskEnd
