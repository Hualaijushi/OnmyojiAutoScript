# This Python file uses the following encoding: utf-8

import time
from datetime import datetime, timedelta

from module.exception import GameStuckError, RequestHumanTakeover, TaskEnd
from module.logger import logger
from tasks.Chess.assets import ChessAssets
from tasks.Chess.config import Chess
from tasks.Chess.runtime.economy import ChessEconomyMixin
from tasks.Chess.runtime.frame_compat import ChessFrameCompatMixin
from tasks.Chess.runtime.hand_operations import (
    ChessHandOperationsMixin,
)
from tasks.Chess.runtime.recognition import ChessRecognitionMixin
from tasks.Chess.runtime.round_state import ChessRoundStateMixin
from tasks.Chess.runtime.settings import ChessRuntimeSettings
from tasks.Chess.runtime.state_loop import ChessStateLoopMixin
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_chess


class ChessLegacyScriptTask(
    ChessFrameCompatMixin,
    ChessRecognitionMixin,
    ChessHandOperationsMixin,
    ChessRoundStateMixin,
    ChessEconomyMixin,
    ChessRuntimeSettings,
    GameUi,
    GeneralBattle,
    ChessAssets,
):
    """百鬼棋局任务入口：仅负责任务、整局与回目编排。"""

    conf: Chess = None

    def _burst(self) -> bool:
        """棋局任务的所有截图均检查红叉，关闭遮挡操作的浮窗。"""
        if super()._burst():
            return True
        if self.appear_then_click(self.I_CHESS_CLOSE_RED, interval=0.8):
            logger.info('Chess: close floating window with red cross')
            return True
        return False

    def _wait_chess_action_state(self, condition) -> bool:
        """限时确认动作结果；截图节奏交给设备层，不额外固定等待。"""
        deadline = time.monotonic() + self.ACTION_ICON_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()
            if condition():
                return True
        self.device.stuck_record_clear()
        self.screenshot()
        return bool(condition())

    def run(self):
        # 上游在这里套 ChessActivityWatchdog（sys.setprofile + 异步线程异常注入）。本地不引入全局钩子，
        # 棋局的有界退出沿用各阶段自己的超时与设备层卡死保护。
        self._run_chess_task()

    def _run_chess_task(self):
        """按执行次数循环百鬼棋局，并可在鼬乐币刷满时提前结束。"""
        chess_task_config = getattr(self.config, 'chess', None)
        chess_config = getattr(chess_task_config, 'chess_config', None)
        # 阵容在任务开始、任何游戏操作之前选定一次，整次任务使用同一份快照。
        # 自定义阵容不存在 / 损坏 / 含本地不支持的设置时转人工，不回落到任何内置阵容。
        try:
            strategy = self.select_lineup_strategy(self._configured_lineup_key())
        except (OSError, ValueError) as exc:
            raise RequestHumanTakeover(f'百鬼棋局阵容无法加载，请在 OASX 或 chesslineup 中重新选择：{exc}') from exc

        # 启动恢复会主动退出遗留对局；正常循环只保留保段位退三局。
        self._recover_interrupted_chess_game()
        self.goto_page(page_chess)

        # Config 持有完整 ConfigModel，Chess 专属配置位于
        # self.config.chess.chess_config。旧配置未包含新字段时使用默认值，
        # 避免升级后任务在进入棋局大厅时直接崩溃。
        target_count = int(getattr(chess_config, 'run_count', 1))
        configured_limit_time = getattr(chess_config, 'limit_time', None)
        if configured_limit_time is None:
            self.limit_time = timedelta(minutes=30)
        else:
            self.limit_time = timedelta(
                hours=configured_limit_time.hour,
                minutes=configured_limit_time.minute,
                seconds=configured_limit_time.second,
            )
        coin_full_exit = bool(
            getattr(chess_config, 'coin_full_exit', False)
        )
        rank_protection = bool(
            getattr(chess_config, 'rank_protection', False)
        )
        self._matchmaking_timeout_seconds = max(
            10,
            int(getattr(chess_config, 'matchmaking_timeout_seconds', 60)),
        )
        self._consecutive_matchmaking_timeouts = 0
        completed = 0
        coin_limit_reached = False
        rank_protection_exits_remaining = 0
        next_game_already_started = False
        logger.info(
            'Chess task constraints: '
            f'lineup={strategy["key"]} ({strategy["display_name"]}), '
            f'run_count={target_count}, limit_time={self.limit_time}, '
            f'coin_full_exit={coin_full_exit}, '
            f'rank_protection={rank_protection}, '
            f'matchmaking_timeout={self._matchmaking_timeout_seconds}s'
        )

        while (
            target_count == -1
            or completed < target_count
            or rank_protection_exits_remaining > 0
        ):
            # 排名页“再来一局”已经发起匹配时，本轮必须直接接管该局；
            # 时间和满币条件已在点击按钮前检查，不能再次检查后把新局遗留。
            game_already_started = next_game_already_started
            next_game_already_started = False
            if not game_already_started:
                if datetime.now() - self.start_time >= self.limit_time:
                    logger.info(
                        'Chess task time reached; '
                        'stop before starting next game'
                    )
                    break
                self.screenshot()
                if coin_full_exit and self._coin_is_full():
                    logger.info(
                        'Stop Chess task before next game: '
                        'coin reached 600/600'
                    )
                    coin_limit_reached = True
                    break

            logger.debug(
                'Chess game loop '
                f'{completed + 1}/'
                f'{"infinite" if target_count == -1 else target_count}'
            )
            self._rank_protection_exit_requested = bool(
                rank_protection and rank_protection_exits_remaining > 0
            )
            self._rank_protection_exit_succeeded = False
            game_rank = self.run_one_game()

            if (
                self._rank_protection_exit_requested
                and self._rank_protection_exit_succeeded
            ):
                rank_protection_exits_remaining -= 1
                logger.info(
                    'Chess rank-protection exit completed: '
                    f'remaining={rank_protection_exits_remaining}/'
                    f'{self.RANK_PROTECTION_EXIT_COUNT}, '
                    f'completed_games={completed}'
                )
                if rank_protection_exits_remaining > 0:
                    next_game_already_started = (
                        self._restart_chess_game_from_result()
                    )
                else:
                    self.return_to_chess_lobby()
                continue

            completed += 1
            if rank_protection and game_rank is not None and game_rank <= 4:
                rank_protection_exits_remaining = (
                    self.RANK_PROTECTION_EXIT_COUNT
                )
                logger.info(
                    'Chess rank protection activated: '
                    f'last_rank=第{game_rank}名, schedule '
                    f'{self.RANK_PROTECTION_EXIT_COUNT} active exits'
                )
            else:
                rank_protection_exits_remaining = 0
                if rank_protection:
                    logger.info(
                        'Chess rank protection not activated: '
                        f'last_rank='
                        f'{"未知" if game_rank is None else f"第{game_rank}名"}, '
                        'requires 第1至第4名'
                    )
            logger.info(
                f'Chess completed games: {completed}/'
                f'{"infinite" if target_count == -1 else target_count}, '
                f'rank_protection_exits_pending='
                f'{rank_protection_exits_remaining}'
            )

            # “再来一局”只用于保段位的两次快速退出。正常对局即使还
            # 有运行次数，也仍返回大厅，再由原大厅开局流程开始下一场。
            if rank_protection_exits_remaining > 0:
                if datetime.now() - self.start_time >= self.limit_time:
                    logger.info(
                        'Chess task time reached; '
                        'skip rank-protection restart and return to lobby'
                    )
                    self.return_to_chess_lobby()
                    break
                next_game_already_started = (
                    self._restart_chess_game_from_result()
                )
                continue

            self.return_to_chess_lobby()

            # 鼬乐币总数只在大厅可读；普通对局回到大厅后先核对，再
            # 决定是否继续下一场。保段位两局一旦开始则连续执行完毕。
            if coin_full_exit:
                self.screenshot()
                if self._coin_is_full():
                    logger.info(
                        'Stop Chess task after game: coin reached 600/600'
                    )
                    coin_limit_reached = True
                    break

        logger.info(
            f'Chess task loop finished: completed={completed}, '
            f'target={target_count}, coin_full_exit={coin_full_exit}, '
            f'rank_protection={rank_protection}'
        )
        # 上游在鼬乐币刷满时改排到下周一（set_next_run_next_monday）；本地保持原语义：无论怎样结束都按
        # 调度配置的成功间隔排下一次，所以不引入这个 BaseTask 方法
        self.set_next_run(task='Chess', success=True, finish=True)
        raise TaskEnd('Chess')

    def run_one_game(self) -> int | None:
        """运行一局，停在结算流程并返回 OCR 得到的实际名次。"""
        self._start_chess_game()
        self._run_round_loop()
        rank = getattr(self, '_last_game_rank', None)
        if isinstance(rank, int) and 1 <= rank <= 8:
            logger.info(f'Chess game ended: 第{rank}名')
            return rank
        logger.warning(
            f'Chess game ended: result-page rank OCR unavailable [{rank}]'
        )
        return None

    def run_one_round(self, round_no: int) -> int | None:
        """执行一个回目：回合开始 -> 备 -> 战/鬼/待 -> 等待新回合。"""
        self._current_round_no = int(round_no)
        logger.debug(f'Chess round {round_no}')
        phase = 'await_preparation'
        preparation_done = False
        next_round_candidate = None
        next_round_confirmed = 0
        unknown_since = None
        battle_economy_done = False
        battle_hand_cleanup_done = False
        hyakki_round_seen = False
        hyakki_lineup_checked = False

        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue
            if self._finish_chess_game_after_markers_missing(
                f'round_{round_no}'
            ):
                return None
            if getattr(self, '_rank_protection_exit_requested', False):
                logger.info(
                    'Chess rank protection: actively exit this game; '
                    'the game will not count toward completed runs'
                )
                if self.Chess_Exit(return_to_lobby=False):
                    self._rank_protection_exit_succeeded = True
                    return None
                logger.warning(
                    'Chess rank-protection exit was unavailable; '
                    'retry on the next state refresh'
                )
            observed_round = self._read_round_number()
            mode = self._read_chess_mode()

            round_transition_pending = False
            if observed_round is not None and observed_round != round_no:
                if observed_round == next_round_candidate:
                    next_round_confirmed += 1
                else:
                    next_round_candidate = observed_round
                    next_round_confirmed = 1
                round_transition_pending = True
                if next_round_confirmed >= self.ROUND_CONFIRM_FRAMES:
                    if hyakki_round_seen and not hyakki_lineup_checked:
                        self._reconcile_lineup_after_hyakki_round(
                            next_round_no=observed_round,
                        )
                        hyakki_lineup_checked = True
                    logger.debug(
                        f'Chess round boundary confirmed: {round_no} -> '
                        f'{observed_round}, phase={phase}, '
                        f'preparation_done={preparation_done}'
                    )
                    return observed_round
            else:
                next_round_candidate = None
                next_round_confirmed = 0

            # 回目数字第一次变化时暂停所有旧回目动作，等待第二帧确认。
            if round_transition_pending:
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue

            in_game = mode is not None or self._is_in_chess_game()
            if in_game:
                unknown_since = None
            elif unknown_since is None:
                unknown_since = time.monotonic()
            elif time.monotonic() - unknown_since >= self.UNKNOWN_STATE_TIMEOUT:
                raise GameStuckError(
                    f'Chess: lost all markers during round {round_no}'
                )

            if mode in ('战', '鬼', '待'):
                if mode == '鬼':
                    hyakki_round_seen = True
                if mode == '战':
                    if not battle_hand_cleanup_done:
                        battle_hand_cleanup_done = (
                            self._handle_battle_sell_stage()
                        )
                    # 战阶段必须先完成非体系卡清理，再进入刷新升级。
                    # 若卖卡过程中阶段发生变化，本回目不再启动经济循环。
                    if (
                        battle_hand_cleanup_done
                        and not battle_economy_done
                        and self._read_chess_mode() == '战'
                    ):
                        self._run_battle_economy_until_budget_limit()
                        battle_economy_done = True
                    self._handle_passive_stage('战')
                else:
                    self._handle_passive_stage(mode)
                if phase == 'await_preparation':
                    preparation_done = True
                    phase = 'await_battle_end'
                    logger.warning(
                        f'Chess round {round_no}: resumed in passive mode '
                        f'{mode}; treat preparation as already passed'
                    )

            elif mode == '备':
                # 符咒面板是当前备阶段的高优先级中断事件。选完后不推进
                # phase/preparation_count；下一轮循环会把它当作新的同阶段备，
                # 从上式神、上御魂的起点重新执行。
                if self.appear(self.I_SELECT_GRIGRI):
                    logger.debug('Chess preparation interrupted by grigri selection')
                    self.select_grigri()
                    continue

                if phase == 'await_preparation':
                    # 回合开始先独立购买一次：开商店、扫商店、买目标。
                    # 买完立刻关店扫手牌优先上可上阵容卡；15 秒保护只约束后续升级/刷新循环。
                    self.purchase_lineup_cards_once()
                    self._run_preparation_initial_deploy_stage()
                    if not self._is_preparation_mode():
                        time.sleep(self.SLOW_POLL_INTERVAL)
                        continue
                    self._run_preparation_economy_until_time_limit()
                    if not self._is_preparation_mode():
                        time.sleep(self.SLOW_POLL_INTERVAL)
                        continue
                    if self._handle_preparation_stage(1):
                        preparation_done = True
                        phase = 'await_battle'
                        logger.debug(
                            f'Chess round {round_no}: preparation '
                            'complete; wait for 战/鬼/待'
                        )

            interval = (
                3 * self.SLOW_POLL_INTERVAL
                if mode == '鬼'
                else self.SLOW_POLL_INTERVAL
            )
            time.sleep(interval)

    def _run_round_loop(self) -> None:
        """运行单局回目循环；Chess 自行持续刷新通用卡死计时。"""
        self.device.stuck_record_clear()
        try:
            self._run_game_by_rounds_without_device_stuck_timeout()
        finally:
            self.device.stuck_record_clear()

    def _run_preparation_initial_deploy_stage(self) -> bool:
        """首轮准备切片：3 候选/回手收尾 -> 4a 金鱼 -> 4b 逐格整理 -> 5 首轮装备（在经济前保底执行）。"""
        if self.appear(self.I_SELECT_GRIGRI):
            self.select_grigri()
            return False
        if not self._is_preparation_mode():
            return False

        if hasattr(self, '_sync_board_slots_with_visual_scan') and not self._is_shop_open():
            self._sync_board_slots_with_visual_scan()
        budget = self._create_prep_slice_budget(is_before_first_equip=True, max_inspects=2)

        self._call_with_optional_budget(
            self.deploy_shikigami_from_hand,
            run_regular_goldfish=False,
            direct_only=True,
            budget=budget,
        )
        if hasattr(self, '_process_displaced_lineup_todos') and not budget.wall_exhausted():
            self._process_displaced_lineup_todos(budget=budget)
        needs_remaining_deploy = bool(
            getattr(self, '_last_deploy_stopped_for_direct_only', False)
        )
        if not self._is_preparation_mode():
            return False
        self._call_with_optional_budget(
            self._run_preparation_regular_goldfish_once,
            context='preparation_initial',
            budget=budget,
        )
        if not self._is_preparation_mode():
            return False
        if needs_remaining_deploy and not budget.wall_exhausted():
            remaining_deployed = self._call_with_optional_budget(
                self.deploy_shikigami_from_hand,
                run_regular_goldfish=False,
                direct_only=False,
                reconcile_pending=False,
                budget=budget,
            )
            if hasattr(self, '_process_displaced_lineup_todos') and not budget.wall_exhausted():
                self._process_displaced_lineup_todos(budget=budget)
            if (
                remaining_deployed
                or getattr(self, '_goldfish_lookup_needed', False)
            ) and not budget.wall_exhausted():
                self._call_with_optional_budget(
                    self._run_preparation_regular_goldfish_once,
                    context='preparation_post_deploy',
                    budget=budget,
                )
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_reconcile_pending_deploys_once')
            and not budget.wall_exhausted()
        ):
            self._call_with_optional_budget(
                self._reconcile_pending_deploys_once,
                budget=budget,
            )
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_run_board_check_and_arrange_slice')
            and not budget.wall_exhausted()
        ):
            allow_cursor = not self._get_pending_deploys() and budget.inspects_used == 0
            self._run_board_check_and_arrange_slice(budget=budget, allow_active_inspect=allow_cursor)
        # Step 5：在进入升级/刷店前先执行首轮装备（不因 Step 3/4 未全部做完而饿死）。
        if self._is_preparation_mode() and not self._is_shop_open():
            verified_board_names = self._verified_board_lineup_names()
            self.equip_souls_from_hand(verified_board_names)
            self._mark_first_equip_done_this_round()
        return self._is_preparation_mode()

    def _redeploy_after_preparation_economy_purchase(
        self,
        purchased_cards: list[str],
    ) -> list[str]:
        """升级/刷新买到新卡后，立即关店按共享预算补上卡、整理并补装备。"""
        if not self._is_preparation_mode() or self.appear(self.I_SELECT_GRIGRI):
            return []
        remaining = self._safe_read_remaining_time() if hasattr(self, '_safe_read_remaining_time') else self._read_remaining_time()
        if (
            remaining is not None
            and remaining < self.PREPARATION_ECONOMY_POST_BUY_REDEPLOY_MIN_REMAINING
        ):
            logger.info(
                'Skip Chess post-buy redeploy inside economy loop: '
                f'purchased={purchased_cards}, remaining_time={remaining} '
                f'< {self.PREPARATION_ECONOMY_POST_BUY_REDEPLOY_MIN_REMAINING}'
            )
            return []
        logger.info(
            'Close Chess shop and scan hand after economy purchase: '
            f'purchased={purchased_cards}, remaining_time={remaining}'
        )
        budget = self._create_prep_slice_budget(max_inspects=2)
        if not self._ensure_shop_closed():
            return []
        if hasattr(self, '_sync_board_slots_with_visual_scan'):
            self._sync_board_slots_with_visual_scan()
        self._invalidate_lineup_after_economy_purchase(purchased_cards)

        deployed = self._call_with_optional_budget(
            self.deploy_shikigami_from_hand,
            run_regular_goldfish=False,
            reconcile_pending=False,
            budget=budget,
        )
        if hasattr(self, '_process_displaced_lineup_todos') and not budget.wall_exhausted():
            todo_dep = self._process_displaced_lineup_todos(budget=budget)
            if todo_dep:
                deployed.extend(todo_dep)
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and (deployed or getattr(self, '_goldfish_lookup_needed', False))
        ):
            self._call_with_optional_budget(
                self._run_preparation_regular_goldfish_once,
                context='preparation_post_buy_deploy',
                budget=budget,
            )
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and not budget.wall_exhausted()
        ):
            self._call_with_optional_budget(
                self._reconcile_pending_deploys_once,
                budget=budget,
            )
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_run_board_check_and_arrange_slice')
            and not budget.wall_exhausted()
        ):
            self._run_board_check_and_arrange_slice(budget=budget, allow_active_inspect=False)
        if self._is_preparation_mode() and not self._is_shop_open():
            self.equip_souls_from_hand(self._verified_board_lineup_names())
        return deployed

    def _handle_preparation(self, *, run_regular_goldfish: bool = True) -> bool:
        """统一备阶段收尾切片：符咒优先，补上卡/金鱼/逐格整理/pending 核实后上装备。"""
        if self.appear(self.I_SELECT_GRIGRI):
            self.select_grigri()
            return False
        if not self._is_preparation_mode():
            return False
        if hasattr(self, '_sync_board_slots_with_visual_scan') and not self._is_shop_open():
            self._sync_board_slots_with_visual_scan()
        budget = self._create_prep_slice_budget(max_inspects=2)

        if hasattr(self, '_process_displaced_lineup_todos') and not budget.wall_exhausted():
            self._process_displaced_lineup_todos(budget=budget)
        deployed = self._call_with_optional_budget(
            self.deploy_shikigami_from_hand,
            run_regular_goldfish=False,
            reconcile_pending=not run_regular_goldfish,
            budget=budget,
        )
        if self._is_shop_open() or not self._is_preparation_mode():
            logger.warning(
                'Stop Chess preparation before soul phase: '
                'shop is open or mode left preparation'
            )
            return False
        if (
            run_regular_goldfish
            and (deployed or getattr(self, '_goldfish_lookup_needed', False))
        ):
            self._call_with_optional_budget(
                self._run_preparation_regular_goldfish_once,
                context='preparation_tail_deploy' if deployed else 'preparation_tail',
                budget=budget,
            )
        if (
            run_regular_goldfish
            and self._is_preparation_mode()
            and not self._is_shop_open()
        ):
            round_state = self._ensure_prep_goldfish_round_state()
            if (
                self._has_reconcilable_pending_deploys(round_state)
                and not round_state.get('regular_search_started', False)
                and not getattr(self, '_arakawa_goldfish_placed', False)
            ):
                self._call_with_optional_budget(
                    self._run_preparation_regular_goldfish_once,
                    context='preparation_tail',
                    budget=budget,
                )
        if (
            run_regular_goldfish
            and self._is_preparation_mode()
            and not self._is_shop_open()
            and not budget.wall_exhausted()
        ):
            self._call_with_optional_budget(
                self._reconcile_pending_deploys_once,
                self._ensure_prep_goldfish_round_state(),
                budget=budget,
            )
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_run_board_check_and_arrange_slice')
            and not budget.wall_exhausted()
        ):
            self._run_board_check_and_arrange_slice(budget=budget, allow_active_inspect=False)
        # 无论前面查格是否部分让出，必给装备一次执行机会。
        verified_board_names = self._verified_board_lineup_names()
        self.equip_souls_from_hand(verified_board_names)
        self._mark_first_equip_done_this_round()
        if (
            run_regular_goldfish
            and self._is_preparation_mode()
            and not self._is_shop_open()
            and not budget.wall_exhausted()
        ):
            self._call_with_optional_budget(
                self._run_preparation_regular_goldfish_once,
                context='preparation_tail',
                budget=budget,
            )
        return self._is_preparation_mode()

    def _run_preparation_economy_until_time_limit(self) -> str:
        """备阶段升级/刷新循环：优先可执行且未冷却的回手待办；买到新卡后关店补上阵与装备。

        返回本轮经济阶段结束状态：'complete' | 'blocked' | 'time_limit' | 'interrupted'。
        """
        if not self._is_preparation_mode():
            return 'interrupted'

        self._economy_purchased_cards_pending_deploy = []
        self._schedule_economy_cycle()
        while getattr(self, '_economy_pending', False):
            if not self._is_preparation_mode():
                return 'interrupted'
            if self.appear(self.I_SELECT_GRIGRI):
                return 'interrupted'
            if (
                hasattr(self, '_has_runnable_displaced_todos')
                and self._has_runnable_displaced_todos()
            ):
                if self._ensure_shop_closed():
                    todo_budget = self._create_prep_slice_budget()
                    self._process_displaced_lineup_todos(budget=todo_budget)
                    if self._is_preparation_mode() and not self._is_shop_open():
                        self.equip_souls_from_hand(self._verified_board_lineup_names())
            remaining = self._read_remaining_time()
            if remaining is not None and remaining < 15:
                logger.info(
                    'Stop Chess preparation upgrade/refresh loop: '
                    f'remaining_time={remaining} < 15'
                )
                return 'time_limit'
            result = self._run_economy_atomic_batch(battle_mode=False)
            purchased_cards = list(
                getattr(self, '_economy_purchased_cards_pending_deploy', ())
            )
            if purchased_cards:
                self._economy_purchased_cards_pending_deploy = []
                self._redeploy_after_preparation_economy_purchase(
                    purchased_cards
                )
            if result == 'complete':
                return 'complete'
            if result == 'blocked':
                return 'blocked'
            self.screenshot()
        return 'complete'

    def _should_enter_preparation_followup(self, progress) -> bool:
        """首轮准备结束后若仍在备阶段且余时允许，进入状态机外层可控的续作整理相。"""
        if not self._is_preparation_mode() or self.appear(self.I_SELECT_GRIGRI):
            return False
        min_action_s = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
        remaining = self._safe_read_remaining_time() if hasattr(self, '_safe_read_remaining_time') else self._read_remaining_time()
        if remaining is not None:
            return int(remaining) >= min_action_s
        started = getattr(progress, 'followup_started_at', None)
        max_dur = float(getattr(self, 'PREP_FOLLOWUP_MAX_DURATION_S', 25.0))
        return started is None or (time.monotonic() - started) < max_dur

    def _run_preparation_followup_slice(self, progress) -> bool:
        """首轮后单次有界续作切片；每次执行后返回外层循环保留符咒/切战/切回合守卫。"""
        if not self._is_preparation_mode():
            return False
        if self.appear(self.I_SELECT_GRIGRI):
            # 交回外层 RESOLVE_GRIGRI 处理符咒后，仍保留续作相（未切换至 await_battle）。
            return True
        if getattr(progress, 'followup_started_at', None) is None:
            progress.followup_started_at = time.monotonic()

        min_action_s = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
        remaining = self._safe_read_remaining_time() if hasattr(self, '_safe_read_remaining_time') else self._read_remaining_time()
        if remaining is not None and int(remaining) < min_action_s:
            return False
        max_dur = float(getattr(self, 'PREP_FOLLOWUP_MAX_DURATION_S', 25.0))
        if remaining is None and (time.monotonic() - progress.followup_started_at) >= max_dur:
            return False

        if self._is_shop_open() and not self._ensure_shop_closed():
            return self._is_preparation_mode()
        if hasattr(self, '_sync_board_slots_with_visual_scan'):
            self._sync_board_slots_with_visual_scan()

        sig_before = self._preparation_followup_signature()
        has_runnable_todo = (
            hasattr(self, '_has_runnable_displaced_todos')
            and self._has_runnable_displaced_todos()
        )
        round_state = self._ensure_prep_goldfish_round_state() if hasattr(self, '_ensure_prep_goldfish_round_state') else {}
        gf_pending = bool(
            not getattr(self, '_arakawa_goldfish_placed', False)
            and not round_state.get('goldfish_round_exhausted', False)
        )
        if (
            progress.prep_followup_last_signature == sig_before
            and not has_runnable_todo
            and (remaining is None or int(remaining) < 15 or getattr(progress, '_followup_economy_done', False))
        ):
            # 画面无变化且无新可动作项：直接返回 True，让外层以 SLOW_POLL_INTERVAL 等待下一帧，绝不忙循环。
            progress.prep_followup_idle_count = int(getattr(progress, 'prep_followup_idle_count', 0)) + 1
            return True

        budget = self._create_prep_slice_budget()
        progress.prep_followup_slices = int(getattr(progress, 'prep_followup_slices', 0)) + 1

        # 1) 可执行且未冷却的回手待办
        if hasattr(self, '_process_displaced_lineup_todos') and not budget.wall_exhausted():
            dep_todos = self._process_displaced_lineup_todos(budget=budget)
            if dep_todos:
                budget.actions_done += len(dep_todos)

        # 2) 手牌可上或高星替换候选
        if self._is_preparation_mode() and not self._is_shop_open() and not budget.wall_exhausted():
            dep_hand = self._call_with_optional_budget(
                self.deploy_shikigami_from_hand,
                run_regular_goldfish=False,
                direct_only=False,
                reconcile_pending=False,
                budget=budget,
            )
            if dep_hand:
                budget.actions_done += len(dep_hand)

        # 3) 金鱼续查（允许同轮预算分片续查）
        if (
            gf_pending
            and self._is_preparation_mode()
            and not self._is_shop_open()
            and not budget.wall_exhausted()
        ):
            if self._call_with_optional_budget(
                self._run_preparation_regular_goldfish_once,
                context='preparation_followup',
                budget=budget,
                allow_resume=True,
            ):
                budget.actions_done += 1

        # 4) 逐格检查与整理时间片
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_run_board_check_and_arrange_slice')
            and not budget.wall_exhausted()
        ):
            if self._run_board_check_and_arrange_slice(budget=budget):
                budget.actions_done += 1

        # 5) 跨回合旧 pending 核实（共享每回合 1 次与本切片 1 次上限）
        if (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and hasattr(self, '_reconcile_pending_deploys_once')
            and not budget.wall_exhausted()
        ):
            resolved = self._call_with_optional_budget(
                self._reconcile_pending_deploys_once,
                budget=budget,
            )
            if resolved:
                budget.actions_done += len(resolved)

        # 6) 补穿已确认式神装备
        if self._is_preparation_mode() and not self._is_shop_open():
            equipped = self.equip_souls_from_hand(self._verified_board_lineup_names())
            self._mark_first_equip_done_this_round()
            if equipped:
                budget.actions_done += len(equipped)

        # 7) 若仍有 >=15s 且经济尚未打完、无回手待办阻塞：给一次经济续作机会
        remaining_after = self._safe_read_remaining_time() if hasattr(self, '_safe_read_remaining_time') else self._read_remaining_time()
        if (
            self._is_preparation_mode()
            and remaining_after is not None
            and int(remaining_after) >= 15
            and not (hasattr(self, '_has_runnable_displaced_todos') and self._has_runnable_displaced_todos())
            and not getattr(progress, '_followup_economy_done', False)
            and not budget.wall_exhausted()
        ):
            eco_result = self._run_preparation_economy_until_time_limit()
            if eco_result == 'blocked' or (
                eco_result in (None, 'complete') and not getattr(self, '_economy_pending', False)
            ):
                # blocked 后本准备回合不再重复经济尝试；下回合 begin_round 会自然重置 progress。
                progress._followup_economy_done = True
            if eco_result in ('blocked', 'time_limit'):
                # 若阻塞或余时退出时商店仍开着，在备阶段内先关闭，避免下轮重复关店或污染签名。
                if self._is_preparation_mode() and self._is_shop_open():
                    self._ensure_shop_closed()
            elif eco_result in (None, 'complete'):
                budget.actions_done += 1

        if budget.actions_done > 0:
            progress.prep_followup_last_signature = None
            progress.prep_followup_idle_count = 0
        else:
            progress.prep_followup_last_signature = self._preparation_followup_signature()
            progress.prep_followup_idle_count = int(getattr(progress, 'prep_followup_idle_count', 0)) + 1
        return self._is_preparation_mode()

    def _run_battle_economy_until_budget_limit(self) -> None:
        """战阶段购买体系卡后续跑升级/刷新，并受 15 秒保护。"""
        if self._read_chess_mode() != '战':
            return
        # 与备阶段使用同一入口：先确保商店打开并购买当前体系卡，
        # 再根据金币门槛进入升级/刷新循环。
        self.purchase_lineup_cards_once()
        if self._read_chess_mode() != '战':
            return
        self._schedule_economy_cycle()
        while (
            self._read_chess_mode() == '战'
            and getattr(self, '_economy_pending', False)
        ):
            remaining = self._read_remaining_time()
            if remaining is not None and remaining < 15:
                logger.info(
                    'Stop Chess battle upgrade/refresh loop: '
                    f'remaining_time={remaining} < 15'
                )
                return
            result = self._run_economy_atomic_batch(battle_mode=True)
            if result in ('complete', 'blocked'):
                return
            self.screenshot()

    def _handle_preparation_stage(self, stage_index: int) -> bool:
        """执行一次完整备阶段；卖卡已移至独立的战阶段环节。"""
        logger.debug(f'Chess preparation stage {stage_index}/2')
        return self._handle_preparation() and self._is_preparation_mode()

    def _handle_battle_sell_stage(self) -> bool:
        """战阶段独立卖卡：持续清理杂卡和纹章，直到确认手牌干净。"""
        if self._read_chess_mode() != '战':
            return False
        logger.debug('Chess battle hand-card cleanup')
        sold = self.cleanup_non_lineup_hand_cards(allowed_modes=('战',))
        logger.debug(f'Chess battle hand-card cleanup complete: sold={sold}')
        return self._read_chess_mode() == '战'

    def _handle_passive_stage(self, mode: str) -> bool:
        """战、鬼、待阶段只等待，不主动改变商店状态，也不主动投掷（本地明确排除上游的百鬼试行投掷）。"""
        return mode in ('战', '鬼', '待')



    def _refresh_round_state_screenshot(self) -> bool:
        """刷新回目状态截图；选符咒出现时必须优先处理完毕。"""
        self.screenshot()
        if self.select_chess_sixrealms_if_visible():
            self.screenshot()
            return True
        if not self.appear(self.I_SELECT_GRIGRI):
            return False
        logger.info(
            'Chess round-state refresh interrupted by grigri selection; '
            'resolve grigri before reading round and mode'
        )
        self.select_grigri()
        self.screenshot()
        return True

    def _finish_chess_game_after_markers_missing(
        self,
        context: str,
    ) -> bool:
        """两个局内标志连续三帧消失后，等待结算页并读取实际名次。"""
        if self._is_in_chess_game():
            return False

        for frame in range(2, self.GAME_END_CONFIRM_FRAMES + 1):
            time.sleep(2 * self.SLOW_POLL_INTERVAL)
            self.device.stuck_record_clear()
            self.screenshot()
            if self._is_in_chess_game():
                logger.debug(
                    'Chess game-end confirmation cancelled: '
                    f'in-game marker recovered at frame={frame}, '
                    f'context={context}'
                )
                return False

        logger.info(
            'Chess game end detected: all in-game markers absent for '
            f'{self.GAME_END_CONFIRM_FRAMES} frames, context={context}'
        )
        deadline = time.monotonic() + self.GAME_OVER_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            if self._is_in_chess_game():
                logger.info(
                    'Chess game-end wait cancelled: in-game marker recovered; '
                    f'reset missing-frame count, context={context}'
                )
                return False
            if self.appear(self.I_GAME_OVER_1) or self.appear(self.I_GAME_OVER_2):
                rank, raw = self._read_game_rank()
                self._last_game_rank = rank
                if rank is None:
                    logger.warning(
                        f'Chess game-over rank OCR invalid: [{raw}]'
                    )
                else:
                    logger.info(
                        f'Chess game-over rank OCR: [{raw}] -> 第{rank}名'
                    )
                return True
            time.sleep(2 * self.SLOW_POLL_INTERVAL)
            self.screenshot()

        raise GameStuckError(
            'Chess: all in-game markers disappeared, but I_GAME_OVER did not '
            f'appear within {self.GAME_OVER_WAIT_TIMEOUT:.0f}s'
        )

    def _restart_chess_game_from_result(self) -> bool:
        """推进到排名页并点击“再来一局”；回到大厅时返回 False。"""
        logger.debug('Chess result flow: restart from rank page')
        self._chess_share_advancing = False
        deadline = time.monotonic() + self.CHESS_EXIT_TIMEOUT
        exit_clicked = False
        share_seen = False
        safe_clicks = 0
        next_safe_click_at = 0.0
        fallback_exit_at = time.monotonic() + 1.5

        while time.monotonic() < deadline:
            self.device.stuck_record_clear()
            self.screenshot()

            if self._advance_chess_result_stage():
                exit_clicked = True
                share_seen = True
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if self.appear(self.I_RESTART_AGAIN):
                for attempt in range(
                    1,
                    self.ACTION_ICON_MAX_ATTEMPTS + 1,
                ):
                    self.device.click_record_remove(self.I_RESTART_AGAIN)
                    self.click(self.I_RESTART_AGAIN)
                    if self._wait_chess_action_state(
                        lambda: not self.appear(self.I_RESTART_AGAIN)
                    ):
                        logger.info(
                            'Chess restart-again clicked from rank page: '
                            f'attempt={attempt}/'
                            f'{self.ACTION_ICON_MAX_ATTEMPTS}'
                        )
                        return True
                    logger.warning(
                        'Chess restart-again remained visible after click: '
                        f'attempt={attempt}/'
                        f'{self.ACTION_ICON_MAX_ATTEMPTS}'
                    )
                raise GameStuckError(
                    'Chess: failed to start next game from rank page '
                    'after 3 attempts'
                )

            if self.appear(self.I_CHECK_CHESS):
                logger.warning(
                    'Chess result flow reached lobby before restart-again; '
                    'start the next game from lobby instead'
                )
                return False

            # 已到排名页但按钮仍在动画中时只等待，不执行安全区点击，
            # 避免误触左侧“返回大厅”。
            if self.appear(self.I_CHECK_CHESS_RANK):
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if not exit_clicked:
                if self.appear(self.I_CHESS_EXIT_TO_LOBBY):
                    self.appear_then_click(
                        self.I_CHESS_EXIT_TO_LOBBY,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(self.I_CHESS_EXIT_TO_LOBBY_2):
                    self.appear_then_click(
                        self.I_CHESS_EXIT_TO_LOBBY_2,
                        interval=1.5,
                    )
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                if self.appear(ChessAssets.I_SHARE):
                    exit_clicked = True
                    share_seen = True
                    continue
                if time.monotonic() >= fallback_exit_at:
                    logger.warning(
                        'Chess result flow missed return image before '
                        'restart; click fixed return area'
                    )
                    self.click(self.I_CHESS_EXIT_TO_LOBBY)
                    exit_clicked = True
                    time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                    continue
                time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)
                continue

            if not share_seen and self.appear(ChessAssets.I_SHARE):
                share_seen = True

            now = time.monotonic()
            if share_seen and now >= next_safe_click_at:
                from tasks.GameUi.default_pages import random_click
                self.click(random_click(), interval=1.5)
                safe_clicks += 1
                next_safe_click_at = now + 1.5
            time.sleep(self.CHESS_EXIT_SCREENSHOT_INTERVAL)

        raise GameStuckError(
            'Chess: restart-again did not appear within '
            f'{self.CHESS_EXIT_TIMEOUT:.0f}s, safe_clicks={safe_clicks}'
        )

    def _wait_for_round_start(self) -> int | None:
        """等待稳定回目数字；返回 None 表示本局已经结算。"""
        candidate = None
        confirmed = 0
        while True:
            self.device.stuck_record_clear()
            if self._refresh_round_state_screenshot():
                candidate = None
                confirmed = 0
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue
            if self._finish_chess_game_after_markers_missing(
                'wait_for_round_start'
            ):
                return None

            round_no = self._read_round_number()
            if round_no is not None:
                if round_no == candidate:
                    confirmed += 1
                else:
                    candidate = round_no
                    confirmed = 1
                if confirmed >= self.ROUND_CONFIRM_FRAMES:
                    return round_no
            else:
                candidate = None
                confirmed = 0
            time.sleep(self.SLOW_POLL_INTERVAL)

    def _is_in_chess_game(self) -> bool:
        """以阵容入口、问号或特殊回合标志确认当前处于对局内。"""
        return (
            self.appear(self.I_OPEN_LINEUP)
            or self.appear(self.I_QUESTION_CHECK)
            or self._special_chess_mode() is not None
            or self._stage_marker_visible(self.I_STAGE_ORCHI)
            or self._stage_marker_visible(self.I_STAGE_DEMON)
        )

    def _close_chess_lobby_abnormal_page(self) -> bool:
        """关闭棋局大厅开战时偶发出现的红色返回键异常页面。"""
        if not self.appear(self.I_BACK_RED):
            return False
        logger.warning(
            'Chess start blocked by abnormal lobby page; '
            'close it with back red'
        )
        for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
            self.device.click_record_remove(self.I_BACK_RED)
            self.click(self.I_BACK_RED)
            if self._wait_chess_action_state(
                lambda: not self.appear(self.I_BACK_RED)
            ):
                logger.info(
                    'Chess abnormal lobby page closed; '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}'
                )
                return True
            logger.warning(
                'Chess abnormal lobby page still visible after click: '
                f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
            )
        raise GameStuckError(
            'Chess: failed to close abnormal lobby page after 3 attempts'
        )

    def _wait_until_in_chess_game(
        self,
        timeout: float,
        retry_start: bool = False,
    ) -> None:
        """点击开始后依次等待匹配、加载和局内标志。"""
        deadline = time.monotonic() + timeout
        waiting_logged = False
        waiting_started_at = None
        waiting_seen = False
        matched_loading_started_at = None
        matched_loading_logged = False
        matchmaking_timeout = float(
            getattr(self, '_matchmaking_timeout_seconds', 60)
        )
        while True:
            # 匹配可能持续很久。截图本身会先检查设备卡死计时，因此必须
            # 在每次截图之前清除，不能等识别到“取消等待”后才清除。
            self.device.stuck_record_clear()
            self.screenshot()

            if self.select_chess_sixrealms_if_visible():
                deadline = time.monotonic() + timeout
                continue

            # 以阵容入口或问号图标确认真正进入棋局；商店按钮不再作为
            # 开局成功标志，避免大厅或匹配动画中的相似区域造成误判。
            if self._is_in_chess_game():
                logger.info('Chess matchmaking complete: entered battle')
                self._consecutive_matchmaking_timeouts = 0
                return

            # 极慢加载可能越过原有进入超时，并直接落到名次结算页。
            # 先完整返回大厅，再由本方法重新点击开始，避免下一次任务导航
            # 将该页当作未知页面。
            if self.chess_result_page_visible():
                logger.warning(
                    'Chess matched loading ended on result page before '
                    'in-game markers appeared; recover to lobby and retry'
                )
                self.return_to_chess_lobby()
                deadline = time.monotonic() + timeout
                waiting_logged = False
                waiting_started_at = None
                waiting_seen = False
                matched_loading_started_at = None
                matched_loading_logged = False
                continue

            if self.appear(self.I_CANCEL_WAITING):
                now = time.monotonic()
                waiting_seen = True
                matched_loading_started_at = None
                matched_loading_logged = False
                if waiting_started_at is None:
                    waiting_started_at = now
                if not waiting_logged:
                    logger.info(
                        'Chess matchmaking: waiting for other players; '
                        f'limit={matchmaking_timeout:.0f}s'
                    )
                    waiting_logged = True
                self.device.stuck_record_clear()
                if now - waiting_started_at >= matchmaking_timeout:
                    # 超时点必须使用新截图复核；标志自然消失说明已经匹配，
                    # 此时中断取消流程，转入加载等待。
                    self.device.stuck_record_clear()
                    self.screenshot()
                    if not self.appear(self.I_CANCEL_WAITING):
                        logger.info(
                            'Chess matchmaking completed while timeout exit '
                            'was being verified; abort cancellation'
                        )
                        waiting_started_at = None
                        waiting_logged = False
                        matched_loading_started_at = time.monotonic()
                        matched_loading_logged = False
                        time.sleep(self.SLOW_POLL_INTERVAL)
                        continue
                    if not self.appear_then_click(
                        self.I_CANCEL_WAITING,
                        interval=0,
                    ):
                        self.device.stuck_record_clear()
                        self.screenshot()
                        if self._is_in_chess_game():
                            logger.info(
                                'Chess entered battle while matchmaking exit '
                                'failed; abort cancellation'
                            )
                            self._consecutive_matchmaking_timeouts = 0
                            return
                        if (
                            not self.appear(self.I_CANCEL_WAITING)
                            and not self.appear(self.I_CHESS_START)
                        ):
                            logger.info(
                                'Chess matchmaking completed while exit '
                                'click failed; wait for battle loading'
                            )
                            waiting_started_at = None
                            waiting_logged = False
                            matched_loading_started_at = time.monotonic()
                            matched_loading_logged = False
                            time.sleep(self.SLOW_POLL_INTERVAL)
                            continue
                        if self.appear(self.I_CANCEL_WAITING):
                            time.sleep(self.SLOW_POLL_INTERVAL)
                            continue
                        logger.info(
                            'Chess matchmaking exit completed before click; '
                            'retry from lobby'
                        )

                    # 点击取消后再次确认实际结果。仍显示取消按钮表示退出失败；
                    # 未回大厅则是匹配成功与退出动作发生竞态。
                    time.sleep(self.ACTION_SETTLE_INTERVAL)
                    self.device.stuck_record_clear()
                    self.screenshot()
                    if self._is_in_chess_game():
                        logger.info(
                            'Chess entered battle during matchmaking exit; '
                            'abort cancellation'
                        )
                        self._consecutive_matchmaking_timeouts = 0
                        return
                    if self.appear(self.I_CANCEL_WAITING):
                        logger.warning(
                            'Chess matchmaking exit was not completed; retry'
                        )
                        continue
                    if not self.appear(self.I_CHESS_START):
                        logger.info(
                            'Chess matchmaking marker disappeared without '
                            'returning to lobby; treat as matched and wait '
                            'for battle loading'
                        )
                        waiting_started_at = None
                        waiting_logged = False
                        matched_loading_started_at = time.monotonic()
                        matched_loading_logged = False
                        time.sleep(self.SLOW_POLL_INTERVAL)
                        continue
                    self._consecutive_matchmaking_timeouts += 1
                    logger.warning(
                        'Chess matchmaking timeout: '
                        f'{self._consecutive_matchmaking_timeouts}/3, '
                        f'limit={matchmaking_timeout:.0f}s'
                    )
                    if self._consecutive_matchmaking_timeouts >= 3:
                        logger.warning('Chess matchmaking: 等待过多，结束任务')
                        self.set_next_run(
                            task='Chess',
                            success=False,
                            finish=True,
                        )
                        raise TaskEnd('Chess: 等待过多')
                    waiting_started_at = None
                    waiting_logged = False
                    waiting_seen = False
                    deadline = now + timeout
                    time.sleep(self.ACTION_SETTLE_INTERVAL)
                    continue
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue

            waiting_started_at = None
            waiting_logged = False

            if (
                retry_start
                and self.appear(self.I_BACK_RED)
                and self._close_chess_lobby_abnormal_page()
            ):
                self.device.stuck_record_clear()
                deadline = time.monotonic() + timeout
                waiting_seen = False
                matched_loading_started_at = None
                matched_loading_logged = False
                continue

            if retry_start and self.appear(self.I_CHESS_START):
                waiting_seen = False
                matched_loading_started_at = None
                matched_loading_logged = False
                if self.appear_then_click(
                    self.I_CHESS_START,
                    interval=2 * self.SLOW_POLL_INTERVAL,
                ):
                    self.device.stuck_record_clear()
                    deadline = time.monotonic() + timeout

            # 只有确实见过取消匹配按钮、且它未经脚本取消便自然消失，
            # 才进入“已匹配加载”状态。此时不再使用 GAME_ENTER_TIMEOUT，
            # 防止加载中 100% 尚未切入棋局就被当作报错。
            if waiting_seen:
                now = time.monotonic()
                if matched_loading_started_at is None:
                    matched_loading_started_at = now
                    # 已自然离开等待队列，说明本轮匹配成功；此前的排队
                    # 超时不再属于连续超时。
                    self._consecutive_matchmaking_timeouts = 0
                if not matched_loading_logged:
                    logger.info(
                        'Chess matchmaking complete: waiting for battle '
                        'loading; '
                        f'limit={self.MATCHED_LOADING_TIMEOUT:.0f}s'
                    )
                    matched_loading_logged = True
                if (
                    now - matched_loading_started_at
                    >= self.MATCHED_LOADING_TIMEOUT
                ):
                    raise GameStuckError(
                        'Chess: matched successfully, but loading did not '
                        'reach battle or result page within '
                        f'{self.MATCHED_LOADING_TIMEOUT:.0f}s'
                    )
                time.sleep(self.SLOW_POLL_INTERVAL)
                continue

            if time.monotonic() >= deadline:
                raise GameStuckError(
                    'Chess: timeout waiting for in-game markers'
                )
            time.sleep(self.SLOW_POLL_INTERVAL)

    def _start_chess_game(self) -> None:
        """从棋局大厅开战，确认进入局内后直接开始回合流程。"""
        # 上游在这里 config.reload() 并重新选阵容；本地不在局间刷新：整次任务使用 run() 开头建立的阵容快照
        logger.debug('Chess game start')
        # 式神本局属性：(守护之印, 御魂1, 御魂2)。
        # 守护之印不占普通御魂槽，三个属性均允许为空。
        self._board_shikigami_attributes = {}
        self._board_slots = {}
        self._last_board_snapshot = {}
        self._board_equipment_status = {}
        self._displaced_lineup_todos = {}
        self._board_check_cursor = 1
        self._goldfish_search_progress = set()
        self._prep_first_equip_done_round = None
        self._last_legacy_sync_round = None
        self._board_lineup_names = set()
        self._board_actual_positions = {}
        self._player_deployed_positions = set()
        self._arakawa_goldfish_current_position = None
        self._arakawa_goldfish_placed = False
        self._pending_goldfish_probe = None
        self._goldfish_relocation_pending = False
        self._goldfish_relocation_source = None
        self._goldfish_lookup_needed = False
        self._last_deploy_stopped_for_direct_only = False
        self._prep_goldfish_round_state = None
        self._pending_deploys = {}
        self._pending_arakawa_deploy = None
        self._specifics_evidence_saved_slots = set()
        self._specifics_evidence_save_count = 0
        self._board_special_units = {}
        self._last_game_rank = None
        self._reset_economy_state()
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Reset Chess per-game state: '
            f'lineup={strategy["key"]} ({strategy["display_name"]})'
        )
        self._wait_until_in_chess_game(
            timeout=self.GAME_ENTER_TIMEOUT,
            retry_start=True,
        )
        logger.debug(
            'Chess entered game; skip lineup preset and start round loop'
        )

    def _recover_interrupted_chess_game(self) -> bool:
        """仅在任务启动时清理上次脚本中断后遗留的棋局。"""
        self.screenshot()

        # 已在大厅时无需恢复。
        if self.appear(self.I_CHECK_CHESS):
            return False

        # 上次可能已经进入结算、分享或排名阶段，直接继续既有返回流程。
        if self.chess_result_flow_visible():
            logger.debug('Chess startup recovery: unfinished result flow detected')
            self.return_to_chess_lobby()
            return True

        # 启动恢复属于全局页面判断，只允许使用 c_open_lineup.png 或
        # c_question_check.png。
        # chess_mode OCR 仅供已确认在局内后的回目状态机使用，不能拿来
        # 判断全局页面，否则庭院等页面中的任意非空误识别都会触发退出。
        selected_sixrealms = self.select_chess_sixrealms_if_visible()
        if not selected_sixrealms and not self._is_in_chess_game():
            return False

        logger.warning(
            'Chess startup recovery: interrupted in-game state detected '
            'by I_OPEN_LINEUP or I_QUESTION_CHECK'
        )
        if not self.Chess_Exit():
            raise GameStuckError(
                'Chess: interrupted game detected but active exit was unavailable'
            )
        return True

    def _run_game_by_rounds_without_device_stuck_timeout(self) -> None:
        """单局协调器：逐个调用单回目函数，直至完成结算返回。"""
        round_no = self._wait_for_round_start()
        while round_no is not None:
            round_no = self.run_one_round(round_no)


class ScriptTask(ChessStateLoopMixin, ChessLegacyScriptTask):
    """正式 Chess 入口：状态驱动回合循环复用原有执行动作。"""
