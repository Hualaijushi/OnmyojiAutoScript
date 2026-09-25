# This Python file uses the following encoding: utf-8
"""L2-2 Interaction Policy Migration 回归护栏（docs/L2_INTERACTION_POLICY_MAP.md，DECISIONS D001 L2-2 补记）。

- 审计范围内每个点击调用点都有显式分类（MIGRATE / ALREADY_L2 / KEEP_IMMEDIATE / KEEP_SPECIAL / NEEDS_C），
  源码 timing 漂移（例如把 NORMAL 改回立即点击、给 KEEP_SPECIAL 加 policy、新增未分类点击）直接失败。
- 迁移后的真实 consumer 走 fresh confirm：第二帧仍在 → 恰一次点击且用新帧坐标；第二帧消失 → 零点击。
- Timing ownership 静态守卫：通用 navigator 不注入 policy、FIRE 点击不带普通 policy、policy 前不叠本地 random_delay。
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from module import reaction_profile as rp

_REPO = Path(__file__).resolve().parents[1]

AUDIT_SCOPE = (
    'tasks/Component/GeneralInvite/general_invite.py',
    'tasks/Component/GeneralBattle/general_battle.py',
    'tasks/GameUi/navigator.py',
    'tasks/GameUi/default_pages.py',
    'tasks/GameUi/chess_battle.py',
    'tasks/EvoZone/script_task.py',
    'tasks/Orochi/script_task.py',
    'tasks/RealmRaid/script_task.py',
    'tasks/RyouToppa/script_task.py',
    'tasks/Exploration/base.py',
    'tasks/Exploration/script_task.py',
    'tasks/ActivityShikigami/page.py',
    'tasks/ActivityShikigami/base_act.py',
    'tasks/ActivityShikigami/activities/normal.py',
    'tasks/ActivityShikigami/activities/fake_god.py',
    'tasks/ActivityShikigami/activities/rich_man.py',
    'tasks/KekkaiUtilize/script_task.py',
    'tasks/KekkaiUtilize/page.py',
)

CLICK_NAMES = {'appear_then_click', 'ui_click', 'ui_click_until_disappear', 'ui_click_until_smt_disappear',
               'ui_click_until_appear_or_timeout', 'click', 'ocr_appear_click', 'list_appear_click'}

# (文件, 函数, 调用, 目标源码, 当前 timing, 分类) —— 与 docs/L2_INTERACTION_POLICY_MAP.md 一一对应
INVENTORY = [
    ('tasks/Component/GeneralInvite/general_invite.py', 'run_invite', 'appear_then_click', 'self.I_GI_EMOJI_1', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'run_invite', 'appear_then_click', 'self.I_GI_EMOJI_2', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'exit_room', 'appear_then_click', 'GeneralInviteAssets.I_GI_SURE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'exit_room', 'appear_then_click', 'GeneralInviteAssets.I_GI_SURE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'exit_room', 'appear_then_click', 'self.I_BACK_YELLOW', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'exit_room', 'appear_then_click', 'self.I_BACK_YELLOW_SEA', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'click_fire', 'appear_then_click', 'target', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_open_invite_panel_if_needed', 'appear_then_click', 'self.I_ADD_1', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_open_invite_panel_if_needed', 'appear_then_click', 'self.I_ADD_2', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_open_invite_panel_if_needed', 'appear_then_click', 'self.I_ADD_5_4', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_open_invite_panel_if_needed', 'appear_then_click', 'self.I_ADD_SEA', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_switch_friend_class', 'ui_click', 'self.I_FLAG_1_OFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_switch_friend_class', 'ui_click', 'self.I_FLAG_2_OFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_switch_friend_class', 'ui_click', 'self.I_FLAG_3_OFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_switch_friend_class', 'ui_click', 'self.I_FLAG_4_OFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', '_confirm_invite_and_validate', 'ui_click_until_disappear', 'confirm_rule', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'invite_again', 'appear_then_click', 'self.I_I_NO_DEFAULT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'invite_again', 'appear_then_click', 'self.I_I_DEFAULT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'invite_again', 'appear_then_click', 'self.I_GI_SURE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_and_invite', 'appear_then_click', 'self.I_I_NO_DEFAULT', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_and_invite', 'appear_then_click', 'self.I_GI_SURE', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'appear_then_click', 'self.I_I_NO_DEFAULT', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'appear_then_click', 'self.I_GI_SURE', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'appear_then_click', 'self.I_I_ACCEPT_DEFAULT', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'appear_then_click', 'self.I_I_ACCEPT', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'check_then_accept', 'appear_then_click', 'self.I_I_ACCEPT_APPRENTICE', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'wait_battle', 'appear_then_click', 'self.I_GI_EMOJI_1', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralInvite/general_invite.py', 'wait_battle', 'appear_then_click', 'self.I_GI_EMOJI_2', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_inspection_recover_auto_mode', 'ui_click', 'hand_marker', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'appear_then_click', 'self.I_DISABLE_7DAYS_DIFF_SOUL', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'appear_then_click', 'self.I_CONFIRM_CLOSE_DIFF_SOUL', 'IMMEDIATE', 'NEEDS_C'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_prepare', 'appear_then_click', 'self.I_PREPARE_HIGHLIGHT', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_reward', 'appear_then_click', 'self.I_OVER_GHOST', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', '_handle_reward', 'appear_then_click', 'self.I_GB_SKIN_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'exit_battle', 'appear_then_click', 'self.I_EXIT_ENSURE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'exit_battle', 'appear_then_click', 'self.I_EXIT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'exit_battle', 'ui_click_until_disappear', 'self.I_EXIT_ENSURE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'green_mark_choose', 'appear_then_click', 'self.I_LOCAL', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'appear_then_click', 'self.I_PRESET', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'appear_then_click', 'self.I_PRESET_WIT_NUMBER', 'NORMAL', 'MIGRATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'appear_then_click', 'self.O_PRESET', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'appear_then_click', 'self.O_PRESET_FULL', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'click', 'tmp', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'click', 'tmp', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'click', 'tmp', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'switch_preset_team', 'appear_then_click', 'self.I_PRESET_ENSURE', 'CONFIRM', 'MIGRATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'random_click_swipt', 'click', 'self.C_RANDOM_CLICK', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'check_lock', 'appear_then_click', 'unlock_image', 'policy', 'ALREADY_L2'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'check_lock', 'appear_then_click', 'lock_image', 'policy', 'ALREADY_L2'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'check_and_open_buff', 'ui_click_until_appear_or_timeout', 'self.I_BUFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Component/GeneralBattle/general_battle.py', 'check_and_open_buff', 'appear_then_click', 'self.I_BUFF', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/navigator.py', '_execute_action', 'list_appear_click', 'action', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/navigator.py', '_execute_action', 'appear_then_click', 'action', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/navigator.py', '_execute_action', 'ocr_appear_click', 'action', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/navigator.py', '_execute_action', 'click', 'action', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'find_activity_entry', 'appear_then_click', 'RightActivityAssets.I_TOGGLE_BUTTON', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'handle_activity_overlay', 'appear_then_click', 'GameUiAssets.I_ACTIVITY_SIGNIN_CLOSE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', '<module>', 'ui_click', '?', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_MOON_SEA', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_INCENSE_REALM', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_SEASONRIFT_FOREST', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_PURE_BUDDHA_REALM', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_MANTRA_TOWER', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'exploration_to_six_gates', 'appear_then_click', 'GameUiAssets.I_EXPLORATION_TO_PEACOCK_KINGDOM', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/default_pages.py', 'handle_battle_reward_page', 'appear_then_click', 'GeneralBattleAssets.I_OVER_GHOST', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'appear_then_click', 'self.I_CHESS_RANK_GOTO_LOBBY', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'click', 'GeneralBattleAssets.C_RANDOM_LEFT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'appear_then_click', 'self.I_CHESS_EXIT_TO_LOBBY', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'appear_then_click', 'self.I_CHESS_EXIT_TO_LOBBY_2', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'click', 'self.I_CHESS_EXIT_TO_LOBBY', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'return_to_chess_lobby', 'click', 'GeneralBattleAssets.C_RANDOM_LEFT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'exit_chess_battle', 'click', 'self.I_CHESS_EXIT_CONFIRM', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/GameUi/chess_battle.py', 'exit_chess_battle', 'click', 'self.I_CHESS_EXIT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/EvoZone/script_task.py', 'evozone_enter', 'appear_then_click', 'kirintype', 'DELIBERATE', 'ALREADY_L2'),
    ('tasks/EvoZone/script_task.py', 'run_leader', 'appear_then_click', 'self.I_FORM_TEAM', 'NORMAL', 'ALREADY_L2'),
    ('tasks/EvoZone/script_task.py', '_fire_evozone_alone', 'appear_then_click', 'self.I_EVOZONE_FIRE', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/Orochi/script_task.py', '_close_orochi_soul_choice_popup', 'appear_then_click', 'self.I_GB_CLOSE_RED', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Orochi/script_task.py', 'run_leader', 'appear_then_click', 'self.I_FORM_TEAM', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Orochi/script_task.py', 'run_member', 'appear_then_click', 'self.I_PET_PRESENT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Orochi/script_task.py', '_fire_orochi_alone', 'appear_then_click', 'self.I_OROCHI_FIRE', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/Orochi/script_task.py', 'run_alone', 'appear_then_click', 'self.I_PET_PRESENT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Orochi/script_task.py', 'run_wild', 'appear_then_click', 'self.I_FORM_TEAM', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Orochi/script_task.py', 'run_wild', 'appear_then_click', 'self.I_PET_PRESENT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Orochi/script_task.py', 'run_wild', 'appear_then_click', 'self.I_OROCHI_WILD_FIRE', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/RealmRaid/script_task.py', 'run', 'appear_then_click', 'self.I_FROG_RAID', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RealmRaid/script_task.py', 'ensure_lock', 'appear_then_click', 'self.I_UNLOCK', 'FAST', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', 'ensure_lock', 'appear_then_click', 'self.I_UNLOCK_2', 'FAST', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', 'ensure_lock', 'appear_then_click', 'self.I_LOCK', 'FAST', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', 'ensure_lock', 'appear_then_click', 'self.I_LOCK_2', 'FAST', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', '_enter_target', 'click', 'self.partition[order - 1]', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/RealmRaid/script_task.py', 'reward_detect_click', 'ui_click_until_disappear', 'self.I_SOUL_RAID', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RealmRaid/script_task.py', 'reward_detect_click', 'appear_then_click', 'self.I_SOUL_RAID', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RealmRaid/script_task.py', 'check_refresh', 'appear_then_click', 'self.I_FRESH', 'NORMAL', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', 'check_refresh', 'appear_then_click', 'self.I_FRESH_ENSURE', 'CONFIRM', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', 'fire', 'click', 'click', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/RealmRaid/script_task.py', 'fire', 'appear_then_click', 'self.I_FIRE', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', '_fire_again', 'appear_then_click', 'self.I_SHOW_AGAIN', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RealmRaid/script_task.py', '_fire_again', 'appear_then_click', 'self.I_FRESH_ENSURE', 'confirm_delay', 'ALREADY_L2'),
    ('tasks/RealmRaid/script_task.py', '_fire_again', 'appear_then_click', 'self.I_FIRE_AGAIN', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/RyouToppa/script_task.py', '_wait_for_ryou_toppa_state', 'appear_then_click', 'RealmRaidAssets.I_REALM_RAID', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RyouToppa/script_task.py', '_wait_for_ryou_toppa_state', 'appear_then_click', 'self.I_RYOU_TOPPA', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RyouToppa/script_task.py', '_ensure_team_lock_state', 'appear_then_click', 'source', 'FAST', 'ALREADY_L2'),
    ('tasks/RyouToppa/script_task.py', '_click_toppa_area', 'click', 'rule', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/RyouToppa/script_task.py', 'start_ryou_toppa', 'appear_then_click', 'self.I_SELECT_RYOU_BUTTON', 'FAST', 'ALREADY_L2'),
    ('tasks/RyouToppa/script_task.py', 'start_ryou_toppa', 'appear_then_click', 'self.I_GUILD_ORDERS_REWARDS', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/RyouToppa/script_task.py', 'start_ryou_toppa', 'appear_then_click', 'self.I_START_TOPPA_BUTTON', 'FAST', 'ALREADY_L2'),
    ('tasks/RyouToppa/script_task.py', 'attack_area', 'appear_then_click', 'RealmRaidAssets.I_FIRE', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/Exploration/base.py', 'open_expect_level', 'appear_then_click', 'self.I_UI_CONFIRM', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Exploration/base.py', 'open_expect_level', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Exploration/base.py', 'open_expect_level', 'appear_then_click', 'self.I_UI_CONFIRM', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Exploration/base.py', 'open_expect_level', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'NORMAL', 'ALREADY_L2'),
    ('tasks/Exploration/base.py', 'open_expect_level', 'ocr_appear_click', 'self.O_E_EXPLORATION_LEVEL_NUMBER', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'fill_shikigami', 'click', 'self.C_CLICK_STANDBY_TEAM', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'fill_shikigami', 'click', 'self.L_ROTATE_1', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'fire', 'appear_then_click', 'button', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Exploration/base.py', 'switch_rotate', 'click', 'self.C_CLICK_SETTINGS', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'collect_treasure_box', 'ui_click', 'self.I_E_REWARD_BOX_SMALL', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'collect_treasure_box', 'ui_click_until_disappear', 'self.I_REWARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'collect_treasure_box', 'ui_click', 'self.I_E_REWARD_BOX_BIG', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'collect_treasure_box', 'ui_click_until_disappear', 'self.I_REWARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/base.py', 'quit_exp_main', 'appear_then_click', 'self.I_UI_BACK_YELLOW', 'NAVIGATION', 'ALREADY_L2'),
    ('tasks/Exploration/script_task.py', 'exp_page_handle_dict', 'click', 'pages.random_click()', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/Exploration/script_task.py', 'exec_exp_page', 'appear_then_click', 'self.I_UI_CANCEL', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/Exploration/script_task.py', 'run_on_exp_settings', 'appear_then_click', 'self.I_E_AUTO_ROTATE_OFF', 'FAST', 'ALREADY_L2'),
    ('tasks/Exploration/script_task.py', 'run_on_exp_exit', 'appear_then_click', 'self.I_E_EXIT_CANCEL', 'NAVIGATION', 'ALREADY_L2'),
    ('tasks/Exploration/script_task.py', 'run_on_exp_exit', 'appear_then_click', 'self.I_E_EXIT_CONFIRM', 'CONFIRM', 'ALREADY_L2'),
    ('tasks/ActivityShikigami/page.py', 'goto_activity_entry', 'appear_then_click', 'ActivityShikigamiAssets.I_MAIN_GOTO_ACT_2', 'NAVIGATION', 'ALREADY_L2'),
    ('tasks/ActivityShikigami/page.py', 'goto_activity_entry', 'appear_then_click', 'ActivityShikigamiAssets.I_MAIN_GOTO_ACT', 'NAVIGATION', 'ALREADY_L2'),
    ('tasks/ActivityShikigami/page.py', 'find_activity_entry', 'appear_then_click', 'RightActivityAssets.I_TOGGLE_BUTTON', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/page.py', 'handle_activity_close', 'appear_then_click', 'GlobalGameAssets.I_UI_BACK_RED', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/page.py', 'handle_activity_story', 'appear_then_click', 'ActivityShikigamiAssets.I_SKIP_BUTTON', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/page.py', 'handle_activity_story', 'appear_then_click', 'ActivityShikigamiAssets.I_CONFIRM_SKIP', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/page.py', 'handle_activity_story', 'appear_then_click', 'ActivityShikigamiAssets.I_CONFIRM_SKIP', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/page.py', 'handle_activity_overlay', 'appear_then_click', 'ActivityShikigamiAssets.I_ACTIVITY_SIGNIN_CLOSE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/base_act.py', '_handle_result', 'appear_then_click', 'self.I_UI_BACK_RED', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/base_act.py', 'switch_soul_for', 'ui_click', 'enter_button', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/normal.py', '_run_climb_type', 'click', 'pages.random_click(ltrb=(False, False, True, False))', 'IMMEDIATE', 'KEEP_SPECIAL'),
    # 2026-09-23：爬塔线专用结算单击改造，`NormalClimbAct._handle_result` / `_handle_reward`
    # 接管 GeneralBattle 原有实现（只在本线生效，见 `_climb_owns_settlement_single_click`），
    # 三处 appear_then_click 分别是 base_act.py `_handle_result` 与 general_battle.py
    # `_handle_reward` 对应点位的逐字复制，分类与各自原型保持一致（KEEP_SPECIAL）。
    ('tasks/ActivityShikigami/activities/normal.py', '_handle_result', 'appear_then_click', 'self.I_UI_BACK_RED', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/normal.py', '_handle_reward', 'appear_then_click', 'self.I_OVER_GHOST', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/normal.py', '_handle_reward', 'appear_then_click', 'self.I_GB_SKIN_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/normal.py', '_sync_climb_penta_pass', 'click', 'click_rule', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle', 'appear_then_click', 'self.I_UI_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/normal.py', '_enter_climb_battle', 'appear_then_click', 'fire_rule', 'IMMEDIATE', 'ALREADY_L2'),
    ('tasks/ActivityShikigami/activities/normal.py', '_sync_climb_team_lock', 'ui_click', 'unlock_rule', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/normal.py', '_sync_climb_team_lock', 'ui_click', 'lock_rule', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/fake_god.py', 'run_fakegod', 'click', 'pages.random_click(ltrb=(False, False, True, False))', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/fake_god.py', '_enter_fakegod_battle', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/fake_god.py', '_enter_fakegod_battle', 'appear_then_click', 'self.I_UI_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/fake_god.py', '_enter_fakegod_battle', 'appear_then_click', 'self.I_FG_ACT_FIRE', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/fake_god.py', '_sync_fakegod_team_lock', 'ui_click', 'self.I_FG_UNLOCK', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/fake_god.py', '_sync_fakegod_team_lock', 'ui_click', 'self.I_FG_LOCK', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/rich_man.py', 'enter_board', 'appear_then_click', 'task.I_RM_TO_BATTLE_MAIN', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/rich_man.py', 'run_rich_man', 'appear_then_click', 'self.I_UI_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_throw_until_dice_count_changes', 'click', 'self.C_RM_RANDOM_CLOSE_SAFE_MAIN', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_throw_until_dice_count_changes', 'appear_then_click', 'self.I_RM_THROW', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_run_throw_task', 'appear_then_click', 'self.I_RM_THROW_FIGHT', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_run_throw_task', 'appear_then_click', 'self.I_UI_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_run_throw_task', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_run_rob_task', 'click', 'choice', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_close_boss_level_up', 'click', 'self.C_RM_RANDOM_CLOSE_SAFE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_click_rich_man_challenge', 'appear_then_click', 'challenge_button', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_sync_rich_man_team_lock', 'ui_click', 'self.I_RM_MAIN_UNLOCK', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_sync_rich_man_team_lock', 'ui_click', 'self.I_RM_MAIN_LOCK', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_wait_for_stable_throw_before_next_round', 'appear_then_click', 'self.I_UI_CONFIRM', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/ActivityShikigami/activities/rich_man.py', '_wait_for_stable_throw_before_next_round', 'appear_then_click', 'self.I_UI_CONFIRM_SAMLL', 'IMMEDIATE', 'KEEP_SPECIAL'),
    ('tasks/KekkaiUtilize/script_task.py', 'check_max_lv', 'ui_click', 'self.I_AUTO_FILL', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'check_and_get_guild_rewards', 'appear_then_click', 'self.I_GUILD_EXPAND', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'check_and_get_guild_rewards', 'appear_then_click', 'self.I_GUILD_ASSETS_RECEIVE', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'check_and_get_guild_rewards', 'appear_then_click', 'self.I_GUILD_ASSETS', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'check_and_get_guild_rewards', 'appear_then_click', 'self.I_GUILD_AP', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'guild_lottery', 'ui_click_until_appear_or_timeout', 'self.I_GUILD_LOTTERY', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'guild_lottery', 'click', 'self.C_UI_REWARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', 'guild_lottery', 'appear_then_click', 'self.I_UI_BACK_YELLOW', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_harvest_ap_box', 'ui_click_until_smt_disappear', 'self.C_UI_REWARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_harvest_ap_box', 'appear_then_click', 'self.I_AP_EXTRACT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_harvest_exp_jug', 'ui_click_until_disappear', 'target_button', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_harvest_exp_jug', 'click', 'self.I_EXP_EXTRACT', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_run_search_pass', 'click', 'self.C_SELECT_CARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/script_task.py', '_select_lazy_resource_card', 'click', 'self.C_SELECT_CARD', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/page.py', '<module>', 'appear_then_click', 'KekkaiUtilizeAssets.I_BOX_EXP', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
    ('tasks/KekkaiUtilize/page.py', '<module>', 'appear_then_click', 'KekkaiUtilizeAssets.I_BOX_EXP_MAX', 'IMMEDIATE', 'KEEP_IMMEDIATE'),
]


def _call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')


def scan_scope():
    rows = []
    for rel in AUDIT_SCOPE:
        text = (_REPO / rel).read_text(encoding='utf-8')

        def visit(node, owner):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, child.name)
                    continue
                if isinstance(child, ast.Call) and _call_name(child) in CLICK_NAMES:
                    is_self_click = not (_call_name(child) == 'click' and not (
                        isinstance(child.func, ast.Attribute) and getattr(child.func.value, 'id', '') == 'self'))
                    if is_self_click:
                        kws = {kw.arg: kw.value for kw in child.keywords}
                        if 'policy' in kws:
                            timing = ast.get_source_segment(text, kws['policy']).replace('InteractionPolicy.', '')
                        elif 'confirm_delay' in kws:
                            timing = 'confirm_delay'
                        else:
                            timing = 'IMMEDIATE'
                        target = ast.get_source_segment(text, child.args[0]) if child.args else '?'
                        rows.append((rel, owner, _call_name(child), ' '.join(target.split()), timing))
                visit(child, owner)

        visit(ast.parse(text), '<module>')
    return rows


def _frames_task(task, frames, events):
    """把 task 的 screenshot / appear 接到帧序列上；目标按 name 取当前帧坐标。"""
    state = {'frame': 0}

    def screenshot():
        state['frame'] += 1
        events.append(('screenshot', state['frame']))

    def appear(target, interval=None, threshold=None):
        return target.name in frames[min(state['frame'], len(frames) - 1)]

    def make(name):
        def coord():
            return frames[min(state['frame'], len(frames) - 1)][name]
        return SimpleNamespace(name=name, coord=coord)

    task.screenshot = screenshot
    task.appear = appear
    task.interval_timer = {}
    task.device = SimpleNamespace(
        image='F', click=Mock(side_effect=lambda x, y, control_name: events.append(('click', control_name, x, y))),
        click_record_clear=Mock())
    return make


class InventoryGuardTest(TestCase):
    def test_every_audited_click_is_classified_and_timing_matches(self):
        actual = scan_scope()
        expected = [tuple(row[:5]) for row in INVENTORY]
        self.assertEqual(actual, expected)

    def test_case1_migrated_consumers_use_declared_policy(self):
        migrated = {(r[1], r[3]): r[4] for r in INVENTORY if r[5] == 'MIGRATE'}
        self.assertEqual(migrated, {
            ('_open_invite_panel_if_needed', 'self.I_ADD_1'): 'NORMAL',
            ('_open_invite_panel_if_needed', 'self.I_ADD_2'): 'NORMAL',
            ('_open_invite_panel_if_needed', 'self.I_ADD_5_4'): 'NORMAL',
            ('_open_invite_panel_if_needed', 'self.I_ADD_SEA'): 'NORMAL',
            ('switch_preset_team', 'self.I_PRESET'): 'NORMAL',
            ('switch_preset_team', 'self.I_PRESET_WIT_NUMBER'): 'NORMAL',
            ('switch_preset_team', 'self.I_PRESET_ENSURE'): 'CONFIRM',
        })

    def test_case2_confirm_decisions_are_not_normal(self):
        confirm_targets = {'self.I_PRESET_ENSURE', 'self.I_FRESH_ENSURE', 'self.I_E_EXIT_CONFIRM'}
        for row in INVENTORY:
            if row[3] in confirm_targets and row[5] in ('MIGRATE', 'ALREADY_L2') and row[4] != 'confirm_delay':
                with self.subTest(row=row):
                    self.assertEqual(row[4], 'CONFIRM')

    def test_case7_8_keep_and_needs_c_paths_stay_without_reaction(self):
        for row in INVENTORY:
            if row[5] in ('KEEP_IMMEDIATE', 'KEEP_SPECIAL', 'NEEDS_C'):
                with self.subTest(row=row):
                    self.assertEqual(row[4], 'IMMEDIATE')

    def test_case6_already_l2_consumers_are_not_restacked(self):
        for row in INVENTORY:
            if row[5] == 'ALREADY_L2':
                with self.subTest(row=row):
                    self.assertIn(row[4], ('FAST', 'NORMAL', 'CONFIRM', 'NAVIGATION', 'DELIBERATE',
                                           'IMMEDIATE', 'confirm_delay', 'policy'))


class NavigatorAndFireOwnershipTest(TestCase):
    def test_case3_navigation_is_not_injected_into_generic_executor(self):
        for rel in ('tasks/GameUi/navigator.py', 'tasks/GameUi/default_pages.py', 'tasks/GameUi/chess_battle.py'):
            text = (_REPO / rel).read_text(encoding='utf-8')
            tree = ast.parse(text)
            with self.subTest(file=rel):
                self.assertNotIn('interaction_policy', text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and _call_name(node) in CLICK_NAMES:
                        self.assertFalse({kw.arg for kw in node.keywords} & {'policy', 'confirm_delay'})

    def test_case4_fire_targets_never_carry_ordinary_policy(self):
        fire_rows = [r for r in INVENTORY if 'FIRE' in r[3] or r[3] in ('target', 'fire_rule', 'button', 'challenge_button')]
        self.assertTrue(fire_rows)
        for row in fire_rows:
            with self.subTest(row=row):
                self.assertEqual(row[4], 'IMMEDIATE')

    def test_case5_settlement_stage_popups_stay_special(self):
        stage_funcs = {'_handle_reward', 'handle_battle_reward_page', 'check_and_invite', '_close_orochi_soul_choice_popup'}
        rows = [r for r in INVENTORY if r[1] in stage_funcs]
        self.assertGreaterEqual(len(rows), 6)
        for row in rows:
            with self.subTest(row=row):
                self.assertEqual((row[4], row[5]), ('IMMEDIATE', 'KEEP_SPECIAL'))


class StaticTimingOwnershipGuardTest(TestCase):
    def test_no_local_random_delay_before_a_policy_click_in_the_same_function(self):
        offenders = []
        for path in (_REPO / 'tasks').rglob('*.py'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            for node in ast.walk(ast.parse(text)):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                calls = sorted((n for n in ast.walk(node) if isinstance(n, ast.Call)), key=lambda n: (n.lineno, n.col_offset))
                first_delay = next((n.lineno for n in calls if _call_name(n) == 'random_delay'), None)
                if first_delay is None:
                    continue
                for n in calls:
                    if _call_name(n) == 'appear_then_click' and n.lineno > first_delay and \
                            any(kw.arg == 'policy' for kw in n.keywords):
                        offenders.append((path.relative_to(_REPO).as_posix(), node.name, n.lineno))
        self.assertEqual(offenders, [])

    def test_lower_layers_do_not_import_interaction_policy(self):
        for rel in ('module/click_pipeline.py', 'module/device/control.py', 'module/device/method/minitouch.py',
                    'module/fatigue.py'):
            with self.subTest(file=rel):
                self.assertNotIn('interaction_policy', (_REPO / rel).read_text(encoding='utf-8'))


@patch('tasks.base_task.random_delay', return_value=0.5)
@patch('tasks.base_task.sleep')
class FreshConfirmBehaviourTest(TestCase):
    """驱动真实迁移函数 + 真实 BaseTask.appear_then_click。"""

    def _invite_task(self, frames, events):
        from tasks.Component.GeneralInvite.general_invite import GeneralInvite
        task = GeneralInvite.__new__(GeneralInvite)
        make = _frames_task(task, frames, events)
        for name in ('I_ADD_1', 'I_ADD_2', 'I_ADD_5_4', 'I_ADD_SEA', 'I_LOAD_FRIEND', 'I_INVITE_ENSURE'):
            setattr(task, name, make(name))
        return task

    def test_invite_panel_click_uses_fresh_frame_position_exactly_once(self, _sleep, delay):
        events = []
        task = self._invite_task([{}, {'I_ADD_1': (100, 100)}, {'I_ADD_1': (140, 120)}, {'I_LOAD_FRIEND': (0, 0)}], events)
        self.assertTrue(task._open_invite_panel_if_needed(True))
        clicks = [e for e in events if e[0] == 'click']
        self.assertEqual(clicks, [('click', 'I_ADD_1', 140, 120)])
        delay.assert_called_once_with(*rp.REACTION_NORMAL)
        self.assertEqual(events[:3], [('screenshot', 1), ('screenshot', 2), ('click', 'I_ADD_1', 140, 120)])

    def test_invite_panel_target_gone_after_reaction_is_not_clicked(self, _sleep, delay):
        events = []
        task = self._invite_task([{}, {'I_ADD_1': (100, 100)}, {}, {'I_LOAD_FRIEND': (0, 0)}], events)
        self.assertTrue(task._open_invite_panel_if_needed(True))
        self.assertEqual([e for e in events if e[0] == 'click'], [])
        delay.assert_called_once_with(*rp.REACTION_NORMAL)

    def _preset_task(self, frames, events):
        from tasks.Component.GeneralBattle.general_battle import GeneralBattle
        task = GeneralBattle.__new__(GeneralBattle)
        make = _frames_task(task, frames, events)
        for name in ('I_PRESET', 'I_PRESET_WIT_NUMBER', 'O_PRESET', 'O_PRESET_FULL', 'I_PRESET_ENSURE',
                     'I_PRESENT_LESS_THAN_5'):
            setattr(task, name, make(name))
        task.click = Mock(side_effect=lambda rule, interval=None: events.append(('rule_click', rule.name)))
        return task

    def _run_preset(self, task):
        from tasks.Component.GeneralBattle import general_battle as gb
        with patch.object(gb, 'get_color', return_value=(0, 0, 0)), \
                patch.object(gb, 'color_similar', return_value=False), \
                patch.object(gb.time, 'sleep'):
            task.switch_preset_team(True, 1, 1)

    def test_preset_open_normal_then_confirm_with_fresh_positions(self, _sleep, delay):
        events = []
        task = self._preset_task([
            {},
            {'I_PRESET': (10, 10)}, {'I_PRESET': (12, 14)},              # 打开预设：NORMAL，点新帧位置
            {'I_PRESET_ENSURE': (500, 600)},                              # 等到预设面板
            {}, {},                                                       # 分组 / 队伍颜色循环各截一帧
            {'I_PRESET_ENSURE': (500, 600)}, {'I_PRESET_ENSURE': (505, 602)},   # 确认：CONFIRM，点新帧位置
            {},
        ], events)
        self._run_preset(task)
        clicks = [e for e in events if e[0] in ('click', 'rule_click')]
        self.assertEqual(clicks, [('click', 'I_PRESET', 12, 14), ('rule_click', 'preset_team_1'),
                                  ('click', 'I_PRESET_ENSURE', 505, 602)])
        self.assertEqual([c.args for c in delay.call_args_list], [rp.REACTION_NORMAL, rp.REACTION_CONFIRM])

    def test_preset_confirm_gone_after_reaction_is_not_clicked(self, _sleep, delay):
        events = []
        task = self._preset_task([
            {},
            {'I_PRESET_ENSURE': (500, 600)},
            {}, {},
            {'I_PRESET_ENSURE': (500, 600)}, {},
            {},
        ], events)
        self._run_preset(task)
        self.assertEqual([e for e in events if e[0] == 'click'], [])
        self.assertEqual([c.args for c in delay.call_args_list], [rp.REACTION_CONFIRM])
