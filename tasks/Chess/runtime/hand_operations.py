"""Chess runtime: hand, deployment, soul, cleanup, and recall operations."""

# This Python file uses the following encoding: utf-8

import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from module.atom.click import RuleClick
from module.atom.image import RuleImage
from module.atom.ocr import RuleOcr
from module.base.utils import save_image
from module.click_pipeline import ClickBounds, execute_single_click
from module.exception import GameStuckError
from module.logger import logger
from module.server.log_service import ERROR_LOG_ROOT, build_error_log_dir_name
from tasks.Chess.runtime.press_and_drag import Press_and_Drag
from tasks.Chess.strategy.grigri import (
    grigri_bond_name,
)
from tasks.Chess.strategy.shikigami_catalog import (
    KNOWN_BONDS,
    SHIKIGAMI_BONDS_BY_ROMAJI,
    SHIKIGAMI_ENTRIES,
    resolve_shikigami,
)


@dataclass
class PrepSliceBudget:
    """准备阶段单次整理时间片共享预算（候选整理 / 替换链 / 找金鱼 / 逐格检查共用）。"""

    deadline: float
    max_inspects: int = 1
    inspects_used: int = 0
    is_before_first_equip: bool = False
    max_chain_steps: int = 4
    chain_steps_used: int = 0
    visited_chain_pairs: set[tuple[str, int]] = field(default_factory=set)
    actions_done: int = 0
    reason_stopped: str | None = None

    def remaining_wall_s(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def wall_exhausted(self) -> bool:
        return time.monotonic() >= self.deadline

    def can_start_inspect(
        self,
        remaining_time: int | None,
        *,
        min_before_equip: int = 8,
        min_after_equip: int = 6,
    ) -> tuple[bool, str]:
        if self.inspects_used >= self.max_inspects:
            self.reason_stopped = self.reason_stopped or 'inspect_budget_exhausted'
            return False, 'inspect_budget_exhausted'
        if self.wall_exhausted():
            self.reason_stopped = self.reason_stopped or 'slice_wall_exhausted'
            return False, 'slice_wall_exhausted'
        if remaining_time is None:
            # 倒计时未知时保守不新开高耗时详情查询，避免无界挤压装备时机。
            self.reason_stopped = self.reason_stopped or 'remaining_time_unavailable'
            return False, 'remaining_time_unavailable'
        min_req = min_after_equip if not self.is_before_first_equip else min_before_equip
        if int(remaining_time) < int(min_req):
            self.reason_stopped = self.reason_stopped or 'insufficient_remaining_for_inspect'
            return False, 'insufficient_remaining_for_inspect'
        return True, 'ok'

    def can_start_action(
        self,
        remaining_time: int | None,
        *,
        min_remaining: int = 3,
    ) -> tuple[bool, str]:
        if self.wall_exhausted():
            self.reason_stopped = self.reason_stopped or 'slice_wall_exhausted'
            return False, 'slice_wall_exhausted'
        if remaining_time is not None and int(remaining_time) < int(min_remaining):
            self.reason_stopped = self.reason_stopped or 'insufficient_remaining_for_action'
            return False, 'insufficient_remaining_for_action'
        return True, 'ok'

    def consume_inspect(self) -> None:
        self.inspects_used += 1


class ChessHandOperationsMixin:
    """Internal mixin; use through ``ScriptTask`` only."""

    # 详情页未打开诊断参数：仅用前后两帧轻量对比右半区面板与模板得分
    SPECIFICS_PANEL_ROI = (900, 30, 1280, 660)
    SPECIFICS_EXPANDED_SEARCH_ROI = (900, 100, 1280, 450)
    SPECIFICS_EVIDENCE_MAX_PER_GAME = 2

    def _shikigami_attributes(
        self,
        name: str,
    ) -> tuple[str | None, str | None, str | None]:
        """返回式神本局属性：(守护之印, 御魂1, 御魂2)。"""
        attributes = getattr(self, '_board_shikigami_attributes', {})
        return attributes.get(name, (None, None, None))

    def _set_shikigami_attributes(
        self,
        name: str,
        values: tuple[str | None, str | None, str | None],
    ) -> None:
        attributes = dict(
            getattr(self, '_board_shikigami_attributes', {})
        )
        attributes[name] = values
        self._board_shikigami_attributes = attributes
        logger.debug(f'Chess shikigami attributes: {name}={values}')

    def _configured_names_at_slot(self, set_index: int) -> set[str]:
        """返回配置目标位等于 set_index 的全部阵容式神名（支持同位多式神）。"""
        slot = int(set_index)
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        return {
            unit_name
            for unit_name, cfg in strategy_shikigami.items()
            if cfg.get('position') is not None and int(cfg['position']) == slot
        }

    def _is_slot_satisfied(
        self,
        set_index: int,
        identity: str | None,
    ) -> bool:
        """仅当单位明确符合该格配置身份时返回 True（任意其他阵容卡均不满足）。"""
        if not identity:
            return False
        slot = int(set_index)
        if identity == 'arakawa_goldfish':
            gf_target = self._arakawa_goldfish_target_position()
            return gf_target is not None and int(gf_target) == slot
        return identity in self._configured_names_at_slot(slot)

    @staticmethod
    def _default_board_slot_record(slot: int) -> dict[str, Any]:
        return {
            'slot': int(slot),
            'occupancy': 'unknown',
            'star': None,
            'identity': None,
            'kind': 'unknown',
            'valid': False,
            'source': 'init',
            'updated_round': None,
            'updated_at': 0.0,
            'verified_round': None,
            'satisfies_config': False,
            'player_deployed': False,
            'empty_streak': 0,
            'star_change_streak': 0,
            'star_candidate': None,
            'suspect_merge': False,
            'stale_reason': None,
        }

    def _board_slots_table(self) -> dict[int, dict[str, Any]]:
        """获取或懒初始化 1..12 格级棋盘主记录；兼容从旧预设测试字段只读引导。"""
        raw = getattr(self, '_board_slots', None)
        if not isinstance(raw, dict):
            raw = {}
            self._board_slots = raw
        was_empty = not raw
        for slot in range(1, 13):
            if slot not in raw or not isinstance(raw[slot], dict):
                raw[slot] = self._default_board_slot_record(slot)
        if was_empty:
            self._seed_board_slots_from_legacy_fields()
            self._last_legacy_sync_round = getattr(self, '_current_round_no', None)
        else:
            self._reconcile_legacy_board_on_round_change()
        return raw

    def _seed_board_slots_from_legacy_fields(self) -> None:
        """当测试夹具仅预设旧字段而未建 board_slots 时，按旧字段引导首份格级视图。"""
        slots_table = self._board_slots
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        deployed_names = set(getattr(self, '_board_lineup_names', ()) or ())
        actual_positions = dict(getattr(self, '_board_actual_positions', {}) or {})
        player_positions = set(getattr(self, '_player_deployed_positions', ()) or ())
        goldfish_pos = getattr(self, '_arakawa_goldfish_current_position', None)
        goldfish_placed = bool(getattr(self, '_arakawa_goldfish_placed', False))
        goldfish_units = (getattr(self, '_board_special_units', {}) or {}).get('arakawa_goldfish', {})
        goldfish_identified = bool(goldfish_units.get('identified', False) or goldfish_placed)
        round_no = getattr(self, '_current_round_no', None)

        for name in sorted(deployed_names):
            pos = actual_positions.get(name)
            if pos is None:
                continue
            slot = int(pos)
            if not 1 <= slot <= 12:
                continue
            if goldfish_pos is not None and int(goldfish_pos) == slot:
                continue
            rec = slots_table[slot]
            if rec.get('identity') is not None:
                continue
            rec.update({
                'occupancy': 'occupied',
                'identity': name,
                'kind': 'lineup' if name in strategy_shikigami else 'non_lineup',
                'valid': True,
                'source': 'legacy_seed',
                'updated_round': round_no,
                'verified_round': round_no,
                'satisfies_config': self._is_slot_satisfied(slot, name),
                'player_deployed': slot in player_positions,
            })

        if goldfish_pos is not None and 1 <= int(goldfish_pos) <= 12:
            gf_slot = int(goldfish_pos)
            rec = slots_table[gf_slot]
            if rec.get('identity') is None:
                rec.update({
                    'occupancy': 'occupied',
                    'identity': 'arakawa_goldfish',
                    'kind': 'goldfish',
                    'valid': goldfish_identified,
                    'source': 'legacy_seed',
                    'updated_round': round_no,
                    'verified_round': round_no if goldfish_identified else None,
                    'satisfies_config': self._is_slot_satisfied(gf_slot, 'arakawa_goldfish') if goldfish_identified else False,
                    'player_deployed': gf_slot in player_positions,
                })

    def _reconcile_legacy_board_on_round_change(self) -> None:
        """切回合时对手动清理旧局面字段的测试替身同步清理对应格缓存，避免旧记录阻塞新回合。"""
        if not isinstance(getattr(self, '_board_slots', None), dict):
            return
        cur_round = getattr(self, '_current_round_no', None)
        if not hasattr(self, '_last_legacy_sync_round'):
            self._last_legacy_sync_round = cur_round
            return
        if self._last_legacy_sync_round == cur_round:
            return
        self._last_legacy_sync_round = cur_round
        legacy_names = set(getattr(self, '_board_lineup_names', ()) or ())
        gf_cleared = (
            getattr(self, '_arakawa_goldfish_current_position', None) is None
            and not getattr(self, '_board_special_units', None)
        )
        for slot_id, rec in self._board_slots.items():
            if not isinstance(rec, dict):
                continue
            if rec.get('valid') and rec.get('kind') == 'lineup' and rec.get('identity') not in legacy_names:
                rec.update(self._default_board_slot_record(int(slot_id)))
            elif gf_cleared and (rec.get('kind') == 'goldfish' or rec.get('identity') == 'arakawa_goldfish'):
                rec.update(self._default_board_slot_record(int(slot_id)))

    def _sync_derived_board_views(self) -> None:
        """从格级主状态单向派生兼容旧字段（允许双格同名；优先绑定已满足配置格）。"""
        self._reconcile_legacy_board_on_round_change()
        slots_table = self._board_slots_table()
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        old_deployed = set(getattr(self, '_board_lineup_names', ()) or ())
        old_positions = dict(getattr(self, '_board_actual_positions', {}) or {})

        # 对每格重算 satisfies_config
        by_name: dict[str, list[tuple[tuple[int, int, int], int]]] = {}
        derived_names: set[str] = set()
        derived_positions: dict[str, int] = {}
        goldfish_slot: int | None = None

        for slot in range(1, 13):
            rec = slots_table[slot]
            ident = rec.get('identity')
            kind = rec.get('kind')
            valid = bool(rec.get('valid', False))
            if valid and ident:
                rec['satisfies_config'] = self._is_slot_satisfied(slot, ident)
            else:
                rec['satisfies_config'] = False
            if valid and ident == 'arakawa_goldfish' and kind == 'goldfish':
                goldfish_slot = slot
            elif valid and kind == 'lineup' and ident in strategy_shikigami:
                derived_names.add(ident)
                sat_rank = 0 if rec['satisfies_config'] else 1
                star_val = int(rec['star']) if rec.get('star') in (1, 2, 3) else 0
                by_name.setdefault(ident, []).append(((sat_rank, -star_val, slot), slot))

        # 兼容夹具中仅传了 deployed_names / actual_positions 或非当前策略测试夹具名（如 unit_occ/unit_unknown）
        for legacy_name in old_deployed:
            if legacy_name not in strategy_shikigami:
                legacy_slot = old_positions.get(legacy_name)
                if legacy_slot is not None and 1 <= int(legacy_slot) <= 12:
                    slot_rec = slots_table[int(legacy_slot)]
                    if slot_rec.get('kind') == 'empty' and slot_rec.get('identity') is None:
                        continue
                    derived_names.add(legacy_name)
                    derived_positions.setdefault(legacy_name, int(legacy_slot))
                else:
                    derived_names.add(legacy_name)
            elif legacy_name not in old_positions and legacy_name not in derived_names:
                derived_names.add(legacy_name)

        derived_positions.update({
            ident: min(ranked, key=lambda item: item[0])[1]
            for ident, ranked in by_name.items()
        })

        self._board_lineup_names = derived_names
        self._board_actual_positions = derived_positions
        if goldfish_slot is not None:
            self._arakawa_goldfish_current_position = goldfish_slot
            gf_target = self._arakawa_goldfish_target_position()
            if gf_target is not None and int(gf_target) == goldfish_slot:
                self._arakawa_goldfish_placed = True

    def _update_board_slot(
        self,
        set_index: int,
        *,
        occupancy: str | None = None,
        star: int | None = ...,
        identity: str | None = ...,
        kind: str | None = None,
        valid: bool | None = None,
        source: str = 'update',
        player_deployed: bool | None = None,
        suspect_merge: bool | None = None,
        stale_reason: str | None = ...,
        verified_round: int | None = ...,
        round_no: int | None = None,
    ) -> dict[str, Any]:
        """更新单格主状态并刷新派生视图。"""
        slot = int(set_index)
        slots_table = self._board_slots_table()
        rec = slots_table[slot]
        cur_round = getattr(self, '_current_round_no', None) if round_no is None else round_no
        if occupancy is not None:
            rec['occupancy'] = occupancy
            if occupancy != 'empty':
                rec['empty_streak'] = 0
        if star is not ...:
            rec['star'] = star
        if identity is not ...:
            rec['identity'] = identity
        if kind is not None:
            rec['kind'] = kind
        if valid is not None:
            rec['valid'] = bool(valid)
        if player_deployed is not None:
            rec['player_deployed'] = bool(player_deployed)
            player_set = set(getattr(self, '_player_deployed_positions', set()))
            if player_deployed:
                player_set.add(slot)
            else:
                player_set.discard(slot)
            self._player_deployed_positions = player_set
        if suspect_merge is not None:
            rec['suspect_merge'] = bool(suspect_merge)
        if stale_reason is not ...:
            rec['stale_reason'] = stale_reason
        if verified_round is not ...:
            rec['verified_round'] = verified_round
        elif valid is True:
            rec['verified_round'] = cur_round
        rec['source'] = source
        rec['updated_round'] = cur_round
        rec['updated_at'] = time.monotonic()
        if rec['valid'] and rec['identity']:
            rec['satisfies_config'] = self._is_slot_satisfied(slot, rec['identity'])
        else:
            rec['satisfies_config'] = False
        self._sync_derived_board_views()
        return rec

    def _invalidate_board_slot(
        self,
        set_index: int,
        reason: str,
        *,
        clear_identity: bool = False,
        suspect_merge: bool = False,
    ) -> dict[str, Any]:
        """失效指定站位身份缓存（不把未确认占格当成非阵容卡）。"""
        slot = int(set_index)
        slots_table = self._board_slots_table()
        rec = slots_table[slot]
        prev_identity = rec.get('identity')
        prev_kind = rec.get('kind')
        if prev_kind == 'goldfish' and (clear_identity or reason in ('empty_confirmed', 'hyakki_empty')):
            self._clear_arakawa_goldfish_position(clear_placed=True)
        update_kwargs: dict[str, Any] = {
            'valid': False,
            'source': f'invalidate:{reason}',
            'suspect_merge': suspect_merge,
            'stale_reason': reason,
        }
        if clear_identity:
            update_kwargs['identity'] = None
            update_kwargs['kind'] = 'empty' if reason in ('empty_confirmed', 'hyakki_empty') else 'unknown'
            update_kwargs['star'] = None if reason in ('empty_confirmed', 'hyakki_empty') else rec.get('star')
            update_kwargs['verified_round'] = None
            if reason in ('empty_confirmed', 'hyakki_empty'):
                update_kwargs['occupancy'] = 'empty'
                update_kwargs['player_deployed'] = False
        rec = self._update_board_slot(slot, **update_kwargs)
        if prev_identity and prev_identity == getattr(self, '_pending_equip_verify_name', None):
            self._pending_equip_verify_name = None
        return rec

    def _record_slot_inspection_result(
        self,
        set_index: int,
        inspection: dict,
        *,
        star: int | None = None,
        round_no: int | None = None,
    ) -> dict[str, Any]:
        """详情核查结束后把实际身份统一写回格级主状态。"""
        slot = int(set_index)
        cur_star = star if star is not None else self._board_set_star(slot)
        if not inspection.get('opened'):
            return self._board_slots_table()[slot]
        obs_name = inspection.get('name')
        cur_round = getattr(self, '_current_round_no', None) if round_no is None else round_no
        if obs_name == 'arakawa_goldfish':
            rec = self._update_board_slot(
                slot,
                occupancy='occupied',
                star=cur_star,
                identity='arakawa_goldfish',
                kind='goldfish',
                valid=True,
                source='specifics_inspect',
                suspect_merge=False,
                stale_reason=None,
                verified_round=cur_round,
                round_no=cur_round,
            )
            self._record_arakawa_goldfish_position(slot, identified=True)
            gf_target = self._arakawa_goldfish_target_position()
            if gf_target is not None and int(gf_target) == slot:
                self._mark_arakawa_goldfish_placed(slot)
            return rec
        if obs_name is None:
            return self._update_board_slot(
                slot,
                occupancy='occupied',
                star=cur_star,
                identity=None,
                kind='unknown',
                valid=False,
                source='specifics_unreadable',
                suspect_merge=False,
                stale_reason=inspection.get('reason', 'name_unreadable'),
                verified_round=None,
                round_no=cur_round,
            )
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        kind = 'lineup' if obs_name in strategy_shikigami else 'non_lineup'
        rec = self._update_board_slot(
            slot,
            occupancy='occupied',
            star=cur_star,
            identity=obs_name,
            kind=kind,
            valid=True,
            source='specifics_inspect',
            suspect_merge=False,
            stale_reason=None,
            verified_round=cur_round,
            round_no=cur_round,
        )
        # 若原本曾登记过另一格（且另一格已不再有效），派生表自动切换；同一式神两格均有效时会同时保留。
        return rec

    def _is_board_slot_cache_valid(self, set_index: int) -> bool:
        """判断指定站位格级身份缓存当前是否有效（未标脏且非空/非疑义合并）。"""
        rec = self._board_slots_table()[int(set_index)]
        return bool(
            rec.get('valid')
            and rec.get('identity')
            and not rec.get('suspect_merge')
            and rec.get('occupancy') != 'empty'
        )

    def _sync_board_slots_with_visual_scan(
        self,
        *,
        slots: list[dict] | None = None,
        round_no: int | None = None,
    ) -> list[dict] | None:
        """非 Boss 备战关店状态下对比视觉快照，防抖处理空占/升星变化并保留 unknown。"""
        if slots is None:
            if not self._is_preparation_mode() or self._is_shop_open():
                return None
            slots = self._board_frame_scan()
        if not slots:
            return None

        boss_mode = bool(
            hasattr(self, '_is_boss_challenge_round') and self._is_boss_challenge_round(round_no)
        )
        slots_table = self._board_slots_table()
        last_snapshot = getattr(self, '_last_board_snapshot', None)
        if not isinstance(last_snapshot, dict):
            last_snapshot = {}
            self._last_board_snapshot = last_snapshot
        cur_round = getattr(self, '_current_round_no', None) if round_no is None else round_no
        now = time.monotonic()
        dirty = False
        empty_confirm_need = int(getattr(self, 'SLOT_EMPTY_CONFIRM_FRAMES', 2))
        star_confirm_need = int(getattr(self, 'SLOT_STAR_CHANGE_CONFIRM_FRAMES', 2))

        for slot_idx, vis in enumerate(slots, 1):
            vis_state = vis.get('state', 'unknown')
            vis_star = vis.get('star')
            prev_snap = last_snapshot.get(slot_idx, {})
            prev_vis_state = prev_snap.get('occupancy', 'unknown')
            rec = slots_table[slot_idx]

            last_snapshot[slot_idx] = {
                'occupancy': vis_state,
                'star': vis_star,
                'round_no': cur_round,
                'observed_at': now,
            }

            if vis_state == 'unknown':
                # unknown 或 anchor 缺失不清除任何已确认身份，也不当成空格。
                continue

            if vis_state == 'empty':
                rec['star_change_streak'] = 0
                rec['star_candidate'] = None
                if boss_mode:
                    continue
                if (
                    rec.get('kind') == 'goldfish'
                    and getattr(self, '_arakawa_goldfish_placed', False)
                    and self._arakawa_goldfish_target_position() == slot_idx
                ):
                    # 已确认站定配置位的金鱼受硬保护，不因局部视觉漏判空格而清位重找。
                    continue
                rec['empty_streak'] = int(rec.get('empty_streak', 0)) + 1
                if not rec.get('valid') or rec.get('identity') is None:
                    if rec.get('kind') != 'empty' or rec.get('occupancy') != 'empty':
                        rec['occupancy'] = 'empty'
                        rec['kind'] = 'empty'
                        rec['star'] = None
                        rec['identity'] = None
                        rec['valid'] = True
                        rec['source'] = 'snapshot_empty'
                        dirty = True
                elif rec['empty_streak'] >= empty_confirm_need:
                    self._invalidate_board_slot(slot_idx, 'empty_confirmed', clear_identity=True)
                    dirty = True
                continue

            # vis_state == 'occupied'
            rec['empty_streak'] = 0
            rec['occupancy'] = 'occupied'

            if not boss_mode and prev_vis_state == 'empty' and rec.get('kind') == 'empty':
                # 原为空格突然变占用：说明发生系统自动上阵/移入，标为待核名占格。
                rec['kind'] = 'unknown'
                rec['identity'] = None
                rec['valid'] = False
                rec['verified_round'] = None
                rec['star'] = vis_star
                rec['source'] = 'visual_empty_to_occupied'
                rec['stale_reason'] = 'occupied_changed'
                dirty = True
                continue

            cached_star = rec.get('star')
            if (
                not boss_mode
                and rec.get('valid')
                and rec.get('identity') is not None
                and cached_star in (1, 2, 3)
                and vis_star in (1, 2, 3)
                and vis_star != cached_star
            ):
                if rec.get('star_candidate') == vis_star:
                    rec['star_change_streak'] = int(rec.get('star_change_streak', 0)) + 1
                else:
                    rec['star_candidate'] = vis_star
                    rec['star_change_streak'] = 1
                if rec['star_change_streak'] >= star_confirm_need:
                    rec['star'] = vis_star
                    rec['star_change_streak'] = 0
                    rec['star_candidate'] = None
                    self._invalidate_board_slot(
                        slot_idx,
                        'star_changed',
                        clear_identity=False,
                        suspect_merge=(vis_star > cached_star),
                    )
                    dirty = True
            else:
                rec['star_change_streak'] = 0
                rec['star_candidate'] = None
                if vis_star in (1, 2, 3) and rec.get('star') is None:
                    rec['star'] = vis_star

        if dirty:
            self._sync_derived_board_views()
        return slots

    def _sync_board_slots_after_hyakki_reconcile(
        self,
        *,
        removed_names: list[str] | tuple[str, ...] = (),
        round_no: int | None = None,
    ) -> None:
        """百鬼/符咒后同步移除格状态并结合当前画面清点视觉变化。"""
        slots_table = self._board_slots_table()
        removed_set = set(removed_names or ())
        for slot in range(1, 13):
            rec = slots_table[slot]
            if rec.get('identity') in removed_set:
                self._invalidate_board_slot(slot, 'hyakki_empty', clear_identity=True)
        self._sync_board_slots_with_visual_scan(round_no=round_no)

    def _is_first_equip_done_this_round(self) -> bool:
        state = getattr(self, 'chess_state', None)
        if state is not None and state.round is not None:
            return bool(state.round.prep_first_equip_done)
        return (
            getattr(self, '_prep_first_equip_done_round', None)
            == getattr(self, '_current_round_no', None)
        )

    def _mark_first_equip_done_this_round(self) -> None:
        self._prep_first_equip_done_round = getattr(self, '_current_round_no', None)
        state = getattr(self, 'chess_state', None)
        if state is not None and state.round is not None:
            state.round.prep_first_equip_done = True

    def _create_prep_slice_budget(
        self,
        *,
        is_before_first_equip: bool | None = None,
        max_inspects: int | None = None,
    ) -> PrepSliceBudget:
        """为一次准备整理或续作时间片创建唯一共享预算（不跨子步叠加）。"""
        if is_before_first_equip is None:
            is_before_first_equip = not self._is_first_equip_done_this_round()
        inspect_limit = (
            int(getattr(self, 'PREP_SLICE_MAX_INSPECTS', 1))
            if max_inspects is None
            else max(1, int(max_inspects))
        )
        return PrepSliceBudget(
            deadline=time.monotonic() + float(getattr(self, 'PREP_SLICE_MAX_WALL_SECONDS', 4.5)),
            max_inspects=inspect_limit,
            is_before_first_equip=bool(is_before_first_equip),
            max_chain_steps=int(getattr(self, 'DISPLACED_CHAIN_MAX_STEPS', 4)),
        )

    @staticmethod
    def _call_with_optional_budget(fn, *args, budget: PrepSliceBudget | None = None, **kwargs):
        """调用运行时方法并兼容未接收 budget/allow_resume 参数的测试替身。"""
        if budget is None:
            return fn(*args, **kwargs)
        try:
            return fn(*args, budget=budget, **kwargs)
        except TypeError:
            clean_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k not in ('budget', 'allow_resume')
            }
            return fn(*args, **clean_kwargs)

    def _invalidate_lineup_after_economy_purchase(
        self,
        purchased_cards: list[str],
    ) -> None:
        """商店买入同名已上阵式神且手牌未见新增或出现升星时，失效对应格缓存。"""
        if not purchased_cards or not hasattr(self, '_board_slots_table'):
            return
        slots_table = self._board_slots_table()
        for name in set(purchased_cards):
            for slot in range(1, 13):
                rec = slots_table[slot]
                if rec.get('valid') and rec.get('identity') == name:
                    cur_star = self._board_set_star(slot)
                    if cur_star in (1, 2, 3) and rec.get('star') in (1, 2, 3) and cur_star > rec['star']:
                        self._invalidate_board_slot(
                            slot,
                            'suspect_merge_after_shop_buy',
                            clear_identity=False,
                            suspect_merge=True,
                        )

    def _preparation_followup_signature(self) -> tuple:
        """采集当前备阶段轻量视觉签名，用于识别无变化空闲等待而不忙循环。"""
        slots = self._board_frame_scan() if hasattr(self, '_board_frame_scan') else []
        board_fp = tuple(
            (slot.get('state', 'unknown'), slot.get('star'))
            for slot in (slots or ())
        )
        cards = self._frame_card_scan('card') if hasattr(self, '_frame_card_scan') else []
        souls = self._soul_hand_cards() if hasattr(self, '_soul_hand_cards') else []
        emblems = self._recognized_emblem_hand_cards() if hasattr(self, '_recognized_emblem_hand_cards') else []
        hand_fp = (
            tuple((c.get('name'), c.get('star')) for c in cards),
            tuple(s.get('name') for s in souls),
            tuple(e.get('name') for e in emblems),
        )
        todos = tuple(sorted((getattr(self, '_displaced_lineup_todos', {}) or {}).keys()))
        pending = tuple(sorted((getattr(self, '_pending_deploys', {}) or {}).keys()))
        return (board_fp, hand_fp, todos, pending, getattr(self, '_arakawa_goldfish_placed', False))

    def _board_equipment_status_map(self) -> dict[Any, dict[str, Any]]:
        status = getattr(self, '_board_equipment_status', None)
        if not isinstance(status, dict):
            status = {}
            self._board_equipment_status = status
        return status

    def _mark_board_unit_returned_to_hand(
        self,
        name: str,
        *,
        from_slot: int | None = None,
        reason: str = 'returned_to_hand',
    ) -> None:
        """换回手牌时精准清过期站位/排除，保留装备历史并置待确认状态，登记高优待办。"""
        slots_table = self._board_slots_table()
        # 保留另一格同名有效副本；仅清除来源格
        if from_slot is not None and 1 <= int(from_slot) <= 12:
            rec = slots_table[int(from_slot)]
            if rec.get('identity') == name or not rec.get('valid'):
                self._invalidate_board_slot(int(from_slot), reason, clear_identity=True)

        still_on_board = any(
            slots_table[s].get('valid') and slots_table[s].get('identity') == name
            for s in range(1, 13)
        )
        main_still_satisfied = any(
            slots_table[s].get('valid')
            and slots_table[s].get('identity') == name
            and slots_table[s].get('satisfies_config')
            for s in range(1, 13)
        )
        if not still_on_board:
            deployed_names = set(getattr(self, '_board_lineup_names', set()))
            deployed_names.discard(name)
            self._board_lineup_names = deployed_names
            actual_positions = dict(getattr(self, '_board_actual_positions', {}))
            actual_positions.pop(name, None)
            self._board_actual_positions = actual_positions
            self._clear_pending_deploy(name)
            round_state = self._ensure_prep_goldfish_round_state()
            round_state['deploy_direct_attempted_names'].discard(name)
            round_state['deploy_deferred_names'].discard(name)
            round_state['deploy_recovery_attempted_names'].discard(name)
            round_state['deploy_recovery_queue'].pop(name, None)

        # 若本体仍在配置位有效站定，不因多余副本回手连带污染本体装备状态或产生反复拖向本体的待办。
        if main_still_satisfied:
            return

        attrs = self._shikigami_attributes(name)
        if any(item is not None for item in attrs):
            status_map = self._board_equipment_status_map()
            status_map[name] = 'uncertain_after_return'
            logger.info(
                'Mark Chess equipment status uncertain after return to hand '
                f'(preserve attributes history): name={name}, attributes={attrs}'
            )

        todos = getattr(self, '_displaced_lineup_todos', None)
        if not isinstance(todos, dict):
            todos = {}
            self._displaced_lineup_todos = todos
        cooldown_s = float(getattr(self, 'DISPLACED_LINEUP_COOLDOWN_SECONDS', 2.0))
        prev_todo = todos.get(name, {})
        todos[name] = {
            'name': name,
            'source_slot': from_slot,
            'reason': reason,
            'round_no': getattr(self, '_current_round_no', None),
            'created_at': prev_todo.get('created_at', time.monotonic()),
            'cooldown_until': 0.0 if reason == 'displaced_by_deploy' else (time.monotonic() + cooldown_s),
            'attempts': int(prev_todo.get('attempts', 0)),
        }

    def _safe_read_remaining_time(self) -> int | None:
        """安全读取剩余时间；当处于禁止 OCR 的纯帧单测上下文时退回 None。"""
        own_dict = getattr(self, '__dict__', {})
        reader = getattr(self, '_read_remaining_time', None)
        if reader is None:
            return None
        if '_read_remaining_time' not in own_dict and getattr(RuleOcr.ocr, '__name__', '') == '_ocr_forbidden':
            return None
        return reader()

    def _unit_equipment_slot_budget(
        self,
        name: str,
        *,
        relax_soul_reserve: bool = False,
    ) -> dict[str, Any]:
        """统一装备槽位预算：保留指定纹章槽与两槽上限，不为未拿到的指定御魂空留槽。"""
        config = self.get_lineup_strategy()['shikigami'].get(name)
        if config is None:
            return {
                'eligible': False,
                'uncertain': False,
                'free_slots': 0,
                'unmet_emblems': 0,
                'unmet_soul_slots': 0,
                'generic_free_slots': 0,
                'occupied': (),
                'can_preferred_emblem': False,
                'can_preferred_soul': False,
                'can_generic_emblem': False,
                'can_generic_soul': False,
                'reason': 'not_in_lineup',
            }

        status_entry = self._board_equipment_status_map().get(name)
        if status_entry == 'uncertain_after_return' or (
            isinstance(status_entry, dict) and status_entry.get('status') == 'uncertain_after_return'
        ):
            return {
                'eligible': False,
                'uncertain': True,
                'free_slots': 0,
                'unmet_emblems': 0,
                'unmet_soul_slots': 0,
                'generic_free_slots': 0,
                'occupied': (),
                'can_preferred_emblem': False,
                'can_preferred_soul': False,
                'can_generic_emblem': False,
                'can_generic_soul': False,
                'reason': 'uncertain_after_return',
            }

        _, soul_1, soul_2 = self._shikigami_attributes(name)
        occupied = tuple(item for item in (soul_1, soul_2) if item is not None)
        free_slots = max(0, 2 - len(occupied))
        pref_emblems = tuple(config.get('preferred_emblems', ()))
        pref_souls = tuple(config.get('preferred_souls', ()))
        unmet_emblems = sum(1 for item in pref_emblems if item not in occupied)
        max_soul_slots = min(max(0, 2 - len(pref_emblems)), len(pref_souls))
        equipped_pref_souls = sum(1 for item in pref_souls if item in occupied)
        unmet_soul_slots = min(
            max(0, free_slots - unmet_emblems),
            max(0, max_soul_slots - equipped_pref_souls),
        )
        # 仅保留必要的指定纹章槽，不为尚未拿到的指定御魂锁住式神空槽。
        generic_free_slots = max(0, free_slots - unmet_emblems)
        return {
            'eligible': free_slots > 0,
            'uncertain': False,
            'free_slots': free_slots,
            'unmet_emblems': unmet_emblems,
            'unmet_soul_slots': unmet_soul_slots,
            'generic_free_slots': generic_free_slots,
            'occupied': occupied,
            'can_preferred_emblem': free_slots > 0,
            'can_preferred_soul': free_slots > unmet_emblems,
            'can_generic_emblem': generic_free_slots >= 1,
            'can_generic_soul': generic_free_slots >= 1,
            'reason': 'ok',
        }

    def _registered_actual_position(self, name: str) -> int | None:
        """返回已确认属于本局阵容且登记了有效实际站位的式神格号（1..12），跳过金鱼格与疑义格。"""
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        if name not in strategy_shikigami:
            return None
        slots_table = self._board_slots_table()
        # 若该式神名在 board_slots 中存在有效占格，以格级主记录为准（优先已满足格）。
        valid_matching = [
            s
            for s in range(1, 13)
            if slots_table[s].get('valid')
            and slots_table[s].get('kind') == 'lineup'
            and slots_table[s].get('identity') == name
            and not slots_table[s].get('suspect_merge')
            and getattr(self, '_arakawa_goldfish_current_position', None) != s
        ]
        if valid_matching:
            satisfied = [s for s in valid_matching if slots_table[s].get('satisfies_config')]
            pool = satisfied or valid_matching
            return min(pool)

        actual_positions = getattr(self, '_board_actual_positions', None)
        if actual_positions is not None:
            raw_position = actual_positions.get(name)
        else:
            # 仅兼容未启用运行期站位表（如纯策略离线单测 Runtime）的调用场景。
            raw_position = strategy_shikigami[name].get('position')
        if raw_position is None:
            return None
        pos = int(raw_position)
        if not 1 <= pos <= 12:
            return None
        if getattr(self, '_arakawa_goldfish_current_position', None) == pos:
            return None
        rec = slots_table[pos]
        if (
            rec.get('source') != 'init'
            and (
                rec.get('suspect_merge')
                or rec.get('occupancy') == 'empty'
                or (rec.get('identity') not in (None, name) and rec.get('valid'))
                or (not rec.get('valid') and rec.get('stale_reason') is not None)
            )
        ):
            return None
        return pos

    def _verified_board_lineup_names(
        self,
        verified_names: set[str] | None = None,
    ) -> set[str]:
        """筛选同时属于本局阵容、已确认上阵且已登记有效站位的式神集合。"""
        board_names = getattr(self, '_board_lineup_names', None)
        if verified_names is None:
            candidates = set(board_names or ())
        elif board_names is not None:
            candidates = set(verified_names) & set(board_names)
        else:
            candidates = set(verified_names)
        return {
            name
            for name in candidates
            if self._registered_actual_position(name) is not None
        }

    def _shikigami_name_at_set(self, set_index: int) -> str | None:
        """按本局实际位置反查指定站位的目标式神。"""
        slot = int(set_index)
        if (
            getattr(self, '_arakawa_goldfish_current_position', None)
            == slot
        ):
            # 荒川金鱼属于特殊单位，不能成为任何装备的目标。
            return None
        rec = self._board_slots_table().get(slot)
        if rec and rec.get('valid') and rec.get('kind') == 'lineup' and rec.get('identity'):
            return rec['identity']
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        return next((
            name
            for name in deployed_names
            if self._registered_actual_position(name) == slot
        ), None)

    def _record_actual_lineup_position(
        self,
        name: str,
        set_index: int,
    ) -> None:
        slot = int(set_index)
        positions = dict(getattr(self, '_board_actual_positions', {}))
        positions[name] = slot
        self._board_actual_positions = positions
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        if 1 <= slot <= 12 and name in strategy_shikigami:
            self._update_board_slot(
                slot,
                occupancy='occupied',
                star=self._board_set_star(slot) or self._board_slots_table()[slot].get('star'),
                identity=name,
                kind='lineup',
                valid=True,
                source='record_actual_position',
                suspect_merge=False,
                stale_reason=None,
            )

    def _record_shikigami_soul(self, name: str, soul_name: str) -> bool:
        """写入普通御魂槽；重复御魂或两槽已满时拒绝写入。"""
        protect, soul_1, soul_2 = self._shikigami_attributes(name)
        if soul_name in (soul_1, soul_2):
            return False
        if soul_1 is None:
            soul_1 = soul_name
        elif soul_2 is None:
            soul_2 = soul_name
        else:
            return False
        self._set_shikigami_attributes(
            name,
            (protect, soul_1, soul_2),
        )
        return True

    @staticmethod
    def _rule_center(rule: RuleImage | RuleClick) -> tuple[int, int]:
        x, y, width, height = rule.roi_back
        return x + width // 2, y + height // 2

    def _set_position(self, set_index: int) -> tuple[int, int]:
        """读取普通/首领 Frame 第 13-24 项的上阵落点。"""
        index = int(set_index)
        if not 1 <= index <= 12:
            raise ValueError(f'Chess board set position is not configured: {set_index}')
        frame = (self.F_BOSS_BOARD_OCCUPANCY if self._is_boss_challenge_round()
                 else self.F_BOARD_OCCUPANCY)
        if not self.appear(frame):
            raise GameStuckError('Chess deployment Frame anchor not found')
        x, y, w, h = frame.matched_ranges[12 + index - 1]
        return int(round(x + w / 2)), int(round(y + h / 2))

    def sell_hand_card(self, source: tuple[int, int]) -> None:
        """统一拖到左侧售卖区，避免出售动作改变商店开关状态。"""
        target_rule = self.I_EXPERIENCE
        Press_and_Drag(
            self.device,
            p1=source,
            p2=self._rule_center(target_rule),
            hold_duration=(0.2, 0.3),
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name='CHESS_SELL_UNKNOWN_HAND_CARD',
        )
        self.close_shikigami_specifics_if_open()

    def _wait_hand_card_removed(self, count_before: int, count_cards) -> bool:
        """按新截图确认手牌数量减少，处理误开的详情页，不固定空等。"""
        def removed():
            if self.close_shikigami_specifics_if_open():
                return False
            return count_cards() < count_before

        return self._wait_chess_action_state(removed)

    def close_shikigami_specifics_if_open(self) -> bool:
        """卖卡/上卡误打开式神详情页时，点击安全区域直到关闭。"""
        if not hasattr(self, 'I_SHIKIGAMI_SPECIFICS'):
            return False
        if not self.appear(self.I_SHIKIGAMI_SPECIFICS):
            return False

        logger.warning(
            'Chess shikigami specifics opened unexpectedly, close it'
        )
        for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
            self.device.click_record_remove(self.C_CLICK_CLOSE_SPECIFICS_AREA)
            self.click(self.C_CLICK_CLOSE_SPECIFICS_AREA)
            if self._wait_chess_action_state(
                lambda: not self.appear(self.I_SHIKIGAMI_SPECIFICS)
            ):
                logger.debug(
                    'Chess shikigami specifics closed: '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}'
                )
                return True
            logger.warning(
                'Chess shikigami specifics still visible after close click: '
                f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
            )
        raise GameStuckError(
            'Chess: failed to close shikigami specifics after 3 attempts'
        )

    def sell_one_lineup_hand_card(self) -> dict | None:
        """紧急清理后仍然手满时，出售最右侧的已识别阵容式神。"""
        hand_cards = self._hand_card_detections()
        if not hand_cards:
            logger.warning(
                'Chess hand is full but no hand-card anchor was detected'
            )
            return None

        lineup_names = set(self.shikigami_deploy_positions)
        candidates = []
        for card in hand_cards:
            identity = self.classify_hand_card(card['roi'])
            if (
                identity['type'] == 'shikigami'
                and identity['name'] in lineup_names
            ):
                candidates.append(identity)
        if not candidates:
            logger.warning(
                'Chess hand remains full but no recognized lineup card '
                'is available for emergency sale'
            )
            return None

        identity = max(
            candidates,
            key=lambda item: item['position'][0],
        )
        position = identity['position']
        sale_key = (identity['type'], identity['name'])
        count_before = self._hand_card_identity_count(*sale_key)
        cap_before = self._hand_capacity_count()
        logger.info(
            f'Sell Chess lineup card after hand remains full: '
            f'name={self._shikigami_display_name(identity["name"])}, '
            f'position={position}, identity_count={count_before}, '
            f'hand_capacity={cap_before}/10'
        )
        self.sell_hand_card(position)
        confirmed = self._wait_hand_card_removed(
            count_before,
            lambda: self._hand_card_identity_count(*sale_key),
        )
        count_after = self._hand_card_identity_count(*sale_key)
        cap_after = self._hand_capacity_count()
        if not confirmed:
            logger.warning(
                'Emergency Chess lineup-card sale not confirmed; '
                f'count={count_before}->{count_after}, '
                f'hand_capacity={cap_before}->{cap_after}/10'
            )
            return None
        logger.info(
            'Emergency Chess lineup-card sale confirmed: '
            f'name={self._shikigami_display_name(identity["name"])}, '
            f'count={count_before}->{count_after}, '
            f'hand_capacity={cap_before}->{cap_after}/10'
        )
        return {
            'type': 'lineup',
            'name': identity['name'],
            'position': position,
            'hand_count_before': cap_before,
            'hand_count_after': cap_after,
        }

    def _hakuzosu_protect_target_position(
        self,
        verified_names: set[str] | None = None,
    ) -> int | None:
        """从阵容级配置读取守护之印目标位置；若传已确认名单则返回实际站位。"""
        strategy = self.get_lineup_strategy()
        if self.HAKUZOSU_NAME not in strategy['shikigami']:
            return None
        verified = (
            self._verified_board_lineup_names(verified_names)
            if verified_names is not None
            else None
        )
        position = strategy.get('hakuzosu_protect_position')
        if position is not None:
            position = int(position)
            target_name = next((
                name
                for name, config in strategy['shikigami'].items()
                if int(config['position']) == position
            ), None)
            if target_name is not None:
                if verified is None:
                    return position
                if target_name in verified:
                    return self._registered_actual_position(target_name)

        # 兼容尚未迁移的第三方四元组阵容配置。
        for name, config in strategy['shikigami'].items():
            if not config.get('equip_hakuzosu_protect', False):
                continue
            if verified is None:
                return int(config['position'])
            if name in verified:
                return self._registered_actual_position(name)
        return None

    def _arakawa_goldfish_target_position(self) -> int | None:
        """返回当前阵容配置的荒川金鱼目标格。"""
        position = self.get_lineup_strategy().get(
            'arakawa_goldfish_position'
        )
        return None if position is None else int(position)

    @staticmethod
    def _to_grayscale(image: np.ndarray) -> np.ndarray:
        """将 RGB/RGBA 图像安全转为单通道灰度图。"""
        if image.ndim == 2:
            return image
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_RGBA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    @staticmethod
    def _ocr_arakawa_sign_count_raw(scaled_image: np.ndarray) -> str:
        """以 Single 模式读取放大后的荒川数量原始文本，绕开 Digit 的 ?->2 等字符修正。"""
        height, width = scaled_image.shape[:2]
        roi = (0, 0, int(width), int(height))
        ocr_rule = RuleOcr(
            name='chess_arakawa_sign_count',
            roi=roi,
            area=roi,
            mode='Single',
            method='Default',
            keyword='',
        )
        raw = ocr_rule.ocr(scaled_image)
        return '' if raw is None else str(raw)

    @staticmethod
    def _parse_arakawa_sign_count(raw_text) -> int | None:
        """仅接受纯 ASCII 数字原始文本；空串、问号或任何杂字均返回 None。"""
        if raw_text is None:
            return None
        text = str(raw_text).strip()
        if not text or not re.fullmatch(r'[0-9]+', text):
            return None
        return int(text)

    def _match_left_arakawa_sign(self, image: np.ndarray) -> dict:
        """在左栏 search ROI 内以 I_C_ARAKAWA_SIGN 做灰度模板匹配。"""
        rule = self.I_C_ARAKAWA_SIGN
        threshold = float(rule.threshold)
        img_h, img_w = image.shape[:2]
        rx, ry, rw, rh = (int(v) for v in rule.roi_back)
        left = max(0, rx)
        top = max(0, ry)
        right = min(img_w, rx + rw)
        bottom = min(img_h, ry + rh)
        search_roi = (left, top, max(0, right - left), max(0, bottom - top))
        if search_roi[2] <= 0 or search_roi[3] <= 0:
            return {
                'matched': False,
                'position': None,
                'score': 0.0,
                'search_roi': search_roi,
                'threshold': threshold,
            }
        front_gray = self._to_grayscale(rule.image)
        region_gray = self._to_grayscale(image[top:bottom, left:right])
        if (
            front_gray.shape[0] > region_gray.shape[0]
            or front_gray.shape[1] > region_gray.shape[1]
        ):
            return {
                'matched': False,
                'position': None,
                'score': 0.0,
                'search_roi': search_roi,
                'threshold': threshold,
            }
        result = cv2.matchTemplate(region_gray, front_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        score = float(max_val) if np.isfinite(max_val) else 0.0
        if score < threshold:
            return {
                'matched': False,
                'position': None,
                'score': score,
                'search_roi': search_roi,
                'threshold': threshold,
            }
        return {
            'matched': True,
            'position': (left + int(max_loc[0]), top + int(max_loc[1])),
            'score': score,
            'search_roi': search_roi,
            'threshold': threshold,
        }

    def _read_left_arakawa_bond_status(self) -> dict:
        """读取并同帧复用左栏荒川标识位置及放大 3 倍后的原始数量 OCR 结果。"""
        image = self.device.image
        key = (getattr(self.device, 'image_frame_id', None), id(image))
        cached = getattr(self, '_left_arakawa_bond_cache', None)
        if cached is not None and cached[0] == key:
            return cached[1]

        match = self._match_left_arakawa_sign(image)
        if not match['matched']:
            status = {
                'qualified': False,
                'reason': 'sign_not_found',
                'sign_matched': False,
                'sign_position': None,
                'sign_score': match['score'],
                'count_roi': None,
                'scaled_size': None,
                'raw_text': '',
                'count': None,
            }
            self._left_arakawa_bond_cache = (key, status)
            logger.debug(
                'Chess left Arakawa sign not found: '
                f'score={match["score"]:.3f} < {match["threshold"]:.2f}, '
                f'search_roi={match["search_roi"]}'
            )
            return status

        sx, sy = match['position']
        off_x, off_y = self.ARAKAWA_SIGN_COUNT_OFFSET
        crop_w, crop_h = self.ARAKAWA_SIGN_COUNT_SIZE
        scale = int(self.ARAKAWA_SIGN_COUNT_UPSCALE)
        cx = sx + int(off_x)
        cy = sy + int(off_y)
        count_roi = (cx, cy, int(crop_w), int(crop_h))
        img_h, img_w = image.shape[:2]
        if cx < 0 or cy < 0 or cx + crop_w > img_w or cy + crop_h > img_h:
            status = {
                'qualified': False,
                'reason': 'count_roi_out_of_bounds',
                'sign_matched': True,
                'sign_position': (sx, sy),
                'sign_score': match['score'],
                'count_roi': count_roi,
                'scaled_size': None,
                'raw_text': '',
                'count': None,
            }
            self._left_arakawa_bond_cache = (key, status)
            return status

        crop = image[cy:cy + crop_h, cx:cx + crop_w]
        scaled_size = (int(crop_w) * scale, int(crop_h) * scale)
        scaled = cv2.resize(crop, scaled_size, interpolation=cv2.INTER_LINEAR)
        raw_text = self._ocr_arakawa_sign_count_raw(scaled)
        count = self._parse_arakawa_sign_count(raw_text)
        if count is None:
            reason = 'count_unreadable'
            qualified = False
        elif count < self.ARAKAWA_GOLDFISH_MIN_COUNT:
            reason = 'count_below_threshold'
            qualified = False
        else:
            reason = 'qualified'
            qualified = True
        status = {
            'qualified': qualified,
            'reason': reason,
            'sign_matched': True,
            'sign_position': (sx, sy),
            'sign_score': match['score'],
            'count_roi': count_roi,
            'scaled_size': scaled_size,
            'raw_text': raw_text,
            'count': count,
        }
        self._left_arakawa_bond_cache = (key, status)
        logger.debug(
            'Chess left Arakawa bond status: '
            f'sign_pos={status["sign_position"]}, score={status["sign_score"]:.3f}, '
            f'roi={status["count_roi"]}, scaled={status["scaled_size"]}, '
            f'raw={status["raw_text"]!r}, count={status["count"]}, '
            f'qualified={status["qualified"]}, reason={status["reason"]}'
        )
        return status

    def _check_arakawa_bond_qualified(self) -> dict:
        """准备阶段且商店收起后，校验左栏荒川标识存在且数量 >= 2。"""
        if not self._is_preparation_mode():
            return {
                'qualified': False,
                'reason': 'not_preparation',
                'sign_matched': False,
                'sign_position': None,
                'sign_score': 0.0,
                'count_roi': None,
                'scaled_size': None,
                'raw_text': '',
                'count': None,
            }
        if self._is_shop_open():
            return {
                'qualified': False,
                'reason': 'shop_open',
                'sign_matched': False,
                'sign_position': None,
                'sign_score': 0.0,
                'count_roi': None,
                'scaled_size': None,
                'raw_text': '',
                'count': None,
            }
        return self._read_left_arakawa_bond_status()

    def _is_confirmed_arakawa_goldfish(self, set_index: int) -> bool:
        """只有详情页已确认「金鱼·助阵」且当前记录位于该格时才允许移动。"""
        set_index = int(set_index)
        if getattr(self, '_arakawa_goldfish_current_position', None) != set_index:
            return False
        units = getattr(self, '_board_special_units', {}) or {}
        goldfish = units.get('arakawa_goldfish', {})
        return bool(
            goldfish.get('identified', False)
            and goldfish.get('position') == set_index
        )

    def _known_deployed_lineup_positions(self) -> set[int]:
        """返回脚本已知且仍在场上的己方阵容式神站位集合。"""
        actual_positions = getattr(self, '_board_actual_positions', {})
        deployed_names = getattr(self, '_board_lineup_names', set())
        known = set()
        for name in deployed_names:
            pos = actual_positions.get(name, self.shikigami_deploy_positions.get(name))
            if pos is not None:
                known.add(int(pos))
        return known

    def _lineup_arakawa_names(self) -> set[str]:
        """返回当前阵容中带有荒川羁绊的式神。"""
        return {
            name
            for name in self.get_lineup_strategy()['shikigami']
            if self.ARAKAWA_BOND_NAME
            in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ())
        }

    def _record_arakawa_goldfish_position(self, set_index: int, identified=False) -> None:
        """登记本局金鱼状态；金鱼不占人口且不能佩戴任何装备。"""
        set_index = int(set_index)
        self._arakawa_goldfish_current_position = set_index
        units = dict(getattr(self, '_board_special_units', {}))
        previous = units.get('arakawa_goldfish', {})
        units['arakawa_goldfish'] = {
            **previous,
            'display_name': '金鱼',
            'position': set_index,
            'counts_toward_capacity': False,
            'can_equip_soul': False,
            'can_equip_emblem': False,
            'can_equip_hakuzosu_protect': False,
        }
        if identified:
            units['arakawa_goldfish'].update(identified=True, detected_position=set_index)
        self._board_special_units = units
        if 1 <= set_index <= 12:
            slots_table = self._board_slots_table()
            for other_slot in range(1, 13):
                if other_slot == set_index:
                    continue
                other_rec = slots_table[other_slot]
                if other_rec.get('kind') == 'goldfish' or other_rec.get('identity') == 'arakawa_goldfish':
                    other_rec.update(self._default_board_slot_record(other_slot))
            self._update_board_slot(
                set_index,
                occupancy='occupied',
                star=self._board_set_star(set_index) or slots_table[set_index].get('star'),
                identity='arakawa_goldfish',
                kind='goldfish',
                valid=bool(identified),
                source='goldfish_record',
                suspect_merge=False,
                stale_reason=None,
            )
        logger.debug(
            'Chess special board unit state: '
            f'arakawa_goldfish={units["arakawa_goldfish"]}'
        )

    def _clear_arakawa_goldfish_position(
        self,
        *,
        clear_placed: bool = False,
    ) -> None:
        """清理未确认或已失效的金鱼位置记录；按需重置放好完成状态。"""
        prev_pos = getattr(self, '_arakawa_goldfish_current_position', None)
        self._arakawa_goldfish_current_position = None
        units = dict(getattr(self, '_board_special_units', {}))
        if 'arakawa_goldfish' in units:
            gf_unit = dict(units['arakawa_goldfish'])
            gf_unit['position'] = None
            gf_unit['identified'] = False
            units['arakawa_goldfish'] = gf_unit
            self._board_special_units = units
        if isinstance(getattr(self, '_board_slots', None), dict):
            cleared_slot = False
            slots_table = self._board_slots_table()
            for slot in range(1, 13):
                rec = slots_table[slot]
                if rec.get('kind') == 'goldfish' or rec.get('identity') == 'arakawa_goldfish':
                    rec.update(self._default_board_slot_record(slot))
                    cleared_slot = True
            if cleared_slot:
                self._sync_derived_board_views()
        self._set_goldfish_relocation_pending(False)
        if clear_placed:
            self._arakawa_goldfish_placed = False

    def _mark_arakawa_goldfish_placed(self, target_position: int) -> None:
        """仅在详情确认金鱼就在配置位，或新画面确认拖入配置位后登记完成。"""
        target_position = int(target_position)
        protected_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        protected_positions.add(target_position)
        self._player_deployed_positions = protected_positions
        self._record_arakawa_goldfish_position(target_position, identified=True)
        self._update_board_slot(
            target_position,
            occupancy='occupied',
            identity='arakawa_goldfish',
            kind='goldfish',
            valid=True,
            player_deployed=True,
            source='goldfish_placed',
            suspect_merge=False,
            stale_reason=None,
        )
        self._set_goldfish_relocation_pending(False)
        self._arakawa_goldfish_placed = True
        self._goldfish_lookup_needed = False
        self._pending_goldfish_probe = None

    def _ensure_prep_goldfish_round_state(self) -> dict:
        """重置单轮去重与本轮预算状态，同时保留跨轮尚未完成的查格进度。"""
        round_key = getattr(self, '_current_round_no', None)
        state = getattr(self, '_prep_goldfish_round_state', None)
        if state is None and isinstance(getattr(self, '_board_slots', None), dict):
            legacy_empty = (
                not getattr(self, '_board_lineup_names', None)
                and not getattr(self, '_board_actual_positions', None)
                and not getattr(self, '_player_deployed_positions', None)
                and not getattr(self, '_board_special_units', None)
                and getattr(self, '_arakawa_goldfish_current_position', None) is None
            )
            if legacy_empty:
                # 兼容测试或外部直接清空旧局面字段并置 _prep_goldfish_round_state=None 来模拟新开一局。
                self._board_slots = {}
                self._last_board_snapshot = {}
                self._board_equipment_status = {}
                self._displaced_lineup_todos = {}
                self._goldfish_search_progress = set()
        self._reconcile_legacy_board_on_round_change()
        persistent_progress = getattr(self, '_goldfish_search_progress', None)
        if not isinstance(persistent_progress, set):
            persistent_progress = set()
            self._goldfish_search_progress = persistent_progress
        if state is None or state.get('round_no') != round_key:
            progress = persistent_progress if state is None else state['search_progress']
            self._goldfish_search_progress = progress
            state = {
                'round_no': round_key,
                'inspected_slots': set(),
                'inspected_slot_results': {},
                'blocked_card_attempts': set(),
                'search_progress': progress,
                'regular_search_started': False,
                'goldfish_round_exhausted': False,
                'inspects_used': 0,
                'slot_inspect_cooldown': set(),
                'equip_failure_verifies': set(),
                'deploy_direct_attempted_names': set(),
                'deploy_recovery_attempted_names': set(),
                'deploy_deferred_names': set(),
                'deploy_recovery_queue': {},
                'pending_reconcile_clicks_used': 0,
            }
            self._prep_goldfish_round_state = state
        else:
            state.setdefault('inspected_slots', set())
            state.setdefault('inspected_slot_results', {})
            state.setdefault('blocked_card_attempts', set())
            state.setdefault('search_progress', set())
            state.setdefault('regular_search_started', False)
            state.setdefault('goldfish_round_exhausted', False)
            state.setdefault('inspects_used', 0)
            state.setdefault('slot_inspect_cooldown', set())
            state.setdefault('equip_failure_verifies', set())
            state.setdefault('deploy_direct_attempted_names', set())
            state.setdefault('deploy_recovery_attempted_names', set())
            state.setdefault('deploy_deferred_names', set())
            state.setdefault('deploy_recovery_queue', {})
            state.setdefault('pending_reconcile_clicks_used', 0)
        return state

    def _reset_prep_goldfish_round_state(self) -> None:
        """重置当前回合备战阶段的金鱼查格与阻塞清理状态。"""
        self._prep_goldfish_round_state = None
        self._goldfish_search_progress = set()

    def _get_pending_deploys(self) -> dict[str, dict]:
        """读取本局待核实上卡记录字典；按式神名索引以便同轮去重与跨回合消费。"""
        pending = getattr(self, '_pending_deploys', None)
        if not isinstance(pending, dict):
            pending = {}
            self._pending_deploys = pending
        return pending

    def _sync_legacy_pending_arakawa_deploy(self) -> None:
        """同步维护兼容旧接口的 `_pending_arakawa_deploy` 视图。"""
        pending = self._get_pending_deploys()
        try:
            arakawa_names = self._lineup_arakawa_names()
        except Exception:
            arakawa_names = set()
        latest = None
        for item in pending.values():
            if item.get('name') in arakawa_names:
                latest = item
        self._pending_arakawa_deploy = latest

    def _record_pending_deploy(
        self,
        name: str,
        set_index: int,
        direct_result: dict,
        *,
        status: str,
        recovery_attempted: bool = False,
    ) -> dict:
        """登记单张式神的跨回合待核实记录；不把配置格误记为实际站位。"""
        pending = self._get_pending_deploys()
        record = self._build_pending_arakawa_deploy(
            name,
            set_index,
            direct_result,
            status=status,
            recovery_attempted=recovery_attempted,
            last_attempt_round=getattr(self, '_current_round_no', None),
        )
        pending[name] = record
        self._sync_legacy_pending_arakawa_deploy()
        return record

    def _clear_pending_deploy(self, name: str) -> None:
        """清除已确认落位或已复位可重上的待核实记录。"""
        pending = self._get_pending_deploys()
        if name in pending:
            pending.pop(name, None)
            self._sync_legacy_pending_arakawa_deploy()

    def _is_placed_goldfish_protected_slot(self, set_index: int) -> bool:
        """已确认金鱼站定在配置金鱼位时强制保护该格，避免候选上卡顶走。"""
        gf_target = self._arakawa_goldfish_target_position()
        if gf_target is None or int(gf_target) != int(set_index):
            return False
        if bool(getattr(self, '_arakawa_goldfish_placed', False)):
            return True
        return self._is_confirmed_arakawa_goldfish(int(set_index))

    def _register_confirmed_lineup_deploy(
        self,
        name: str,
        set_index: int,
        *,
        star: int | None = None,
        goldfish_baseline: dict | None = None,
        trigger_hakuzosu: bool = False,
    ) -> None:
        """统一写入已确认上阵式神的名单、实际站位、己方占用、格级状态与联动标记。"""
        slot = int(set_index)
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        deployed_names.add(name)
        self._board_lineup_names = deployed_names
        resolved_star = star if star in (1, 2, 3) else self._board_set_star(slot)
        self._update_board_slot(
            slot,
            occupancy='occupied',
            star=resolved_star,
            identity=name,
            kind='lineup',
            valid=True,
            player_deployed=True,
            source='confirmed_deploy',
            suspect_merge=False,
            stale_reason=None,
        )
        todos = getattr(self, '_displaced_lineup_todos', None)
        if isinstance(todos, dict):
            todos.pop(name, None)
        logger.debug(
            'Mark Chess player-deployed position: '
            f'set={slot}, name={name}'
        )
        if goldfish_baseline is not None:
            self._pending_goldfish_probe = goldfish_baseline
            self._goldfish_lookup_needed = True
        elif (
            name in self._lineup_arakawa_names()
            and getattr(self, '_arakawa_goldfish_current_position', None) is None
        ):
            self._goldfish_lookup_needed = True
        if trigger_hakuzosu and name == self.HAKUZOSU_NAME:
            self.equip_hakuzosu_protect_after_deploy(self._verified_board_lineup_names())

    def _sort_goldfish_candidate_slots(self, slots) -> list[int]:
        """按 6 -> 5 -> 11 -> 12 优先序排列候选占格，其余未登记占格按编号升序排在后面。"""
        priority = self.GOLDFISH_INSPECT_PRIORITY_POSITIONS
        priority_index = {int(pos): idx for idx, pos in enumerate(priority)}
        return sorted(
            {int(pos) for pos in slots},
            key=lambda pos: (
                (0, priority_index[pos]) if pos in priority_index else (1, pos)
            ),
        )

    def _check_goldfish_target_slot_usable(
        self,
        source_position: int,
    ) -> tuple[bool, str, int | None]:
        """核查配置金鱼位是否可用于避让阻塞：须为空格、且非源格/非保留式神格。"""
        target_position = self._arakawa_goldfish_target_position()
        if target_position is None:
            return False, 'no_goldfish_position_configured', None
        target_position = int(target_position)
        source_position = int(source_position)
        if target_position == source_position:
            return False, 'target_equals_goldfish_position', target_position
        _, registered_positions = self._protected_recall_positions()
        if target_position in registered_positions:
            return False, 'goldfish_slot_held_by_kept_unit', target_position
        target_state = self._board_set_state(target_position)
        if target_state != 'empty':
            return False, f'goldfish_slot_{target_state}', target_position
        return True, 'empty_available', target_position

    def _set_goldfish_relocation_pending(
        self,
        pending: bool,
        *,
        source: str | None = None,
    ) -> None:
        """维护待搬金鱼状态与来源标记；挡位来源在确认完成或清除前不降级为常规。"""
        if not pending:
            self._goldfish_relocation_pending = False
            self._goldfish_relocation_source = None
            return
        existing_source = (
            getattr(self, '_goldfish_relocation_source', None)
            if getattr(self, '_goldfish_relocation_pending', False)
            else None
        )
        self._goldfish_relocation_pending = True
        if source == 'blocking' or existing_source == 'blocking':
            self._goldfish_relocation_source = 'blocking'
        elif source is not None:
            self._goldfish_relocation_source = source
        elif existing_source is not None:
            self._goldfish_relocation_source = existing_source
        else:
            self._goldfish_relocation_source = 'regular'

    def _is_blocking_goldfish_relocation_pending(
        self,
        source_position: int | None = None,
    ) -> bool:
        """判断当前待搬金鱼请求是否来自挡位分支。"""
        if not getattr(self, '_goldfish_relocation_pending', False):
            return False
        if getattr(self, '_goldfish_relocation_source', None) != 'blocking':
            return False
        if source_position is None:
            return True
        current = getattr(self, '_arakawa_goldfish_current_position', None)
        return current is not None and int(current) == int(source_position)

    def _move_arakawa_goldfish(
        self,
        source_position: int,
        *,
        verify_vacated_source: bool = False,
    ) -> bool:
        """发拖前统一校验目标配置位空可用（保护已站位阵容棋子），拖后在新画面确认落位才登记完成。"""
        self._reconcile_legacy_board_on_round_change()
        target_position = self._arakawa_goldfish_target_position()
        if target_position is None:
            return False
        source_position = int(source_position)
        target_position = int(target_position)
        use_blocking_guards = bool(
            verify_vacated_source
            or self._is_blocking_goldfish_relocation_pending(source_position)
        )
        pending_source = 'blocking' if use_blocking_guards else 'regular'
        if not self._is_confirmed_arakawa_goldfish(source_position):
            logger.warning(
                'Skip moving Chess Arakawa unit: goldfish identity '
                f'not confirmed by specifics at set {source_position}'
            )
            return False
        if not self._is_preparation_mode() or self._is_shop_open():
            logger.info(
                'Defer Chess Arakawa goldfish relocation: not preparation or shop open '
                f'(source={source_position}, target={target_position}, '
                f'source_kind={pending_source})'
            )
            self._set_goldfish_relocation_pending(True, source=pending_source)
            return False
        # 发拖前关闭详情并复核模式、关店、目标格可用性、时间门控与左栏计数。
        self.close_shikigami_specifics_if_open()
        if not self._is_preparation_mode() or self._is_shop_open():
            logger.info(
                'Defer Chess Arakawa goldfish relocation after closing specifics: '
                'not preparation or shop open '
                f'(source={source_position}, target={target_position}, '
                f'source_kind={pending_source})'
            )
            self._set_goldfish_relocation_pending(True, source=pending_source)
            return False
        if source_position == target_position:
            # 详情已确认金鱼就在配置位，直接登记完成；挡位调用仍返回 False 避免覆盖自身配置格。
            self._mark_arakawa_goldfish_placed(target_position)
            if use_blocking_guards:
                logger.info(
                    'Defer Chess blocked deploy on goldfish slot: '
                    f'card target {source_position} equals assigned goldfish slot {target_position}'
                )
                return False
            logger.info(
                'Chess identified goldfish already at '
                f'assigned set {target_position}'
            )
            return True

        source_state_before = self._board_set_state(source_position)
        if source_state_before == 'empty':
            self._clear_arakawa_goldfish_position(clear_placed=True)
            logger.warning(
                'Skip Chess Arakawa goldfish relocation: source slot became empty '
                f'(source={source_position}, target={target_position})'
            )
            return False
        if source_state_before != 'occupied':
            self._set_goldfish_relocation_pending(True, source=pending_source)
            logger.info(
                'Defer Chess Arakawa goldfish relocation: '
                f'source={source_position}({source_state_before}), target={target_position}'
            )
            return False

        min_remaining = (
            self.GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING
            if use_blocking_guards
            else self.GOLDFISH_REGULAR_MOVE_MIN_REMAINING
        )
        remaining = self._read_remaining_time()
        if remaining is None or remaining < min_remaining:
            self._set_goldfish_relocation_pending(True, source=pending_source)
            logger.info(
                'Defer Chess Arakawa goldfish relocation by remaining time: '
                f'source={source_position}, target={target_position}, '
                f'source_kind={pending_source}, '
                f'remaining_time={remaining}, required>={min_remaining}'
            )
            return False

        usable, usable_reason, _ = self._check_goldfish_target_slot_usable(
            source_position
        )
        if not usable:
            self._set_goldfish_relocation_pending(True, source=pending_source)
            logger.info(
                'Defer Chess Arakawa goldfish relocation: '
                f'source={source_position}, goldfish_target={target_position}, '
                f'source_kind={pending_source}, reason={usable_reason}'
            )
            return False

        protected_before = set(
            getattr(self, '_player_deployed_positions', set())
        )
        bond_status = self._check_arakawa_bond_qualified()
        if not bond_status['qualified']:
            self._set_goldfish_relocation_pending(True, source=pending_source)
            logger.info(
                'Defer Chess Arakawa goldfish relocation before drag: '
                f'source={source_position}, target={target_position}, '
                f'source_kind={pending_source}, '
                f'reason={bond_status["reason"]}, '
                f'raw={bond_status["raw_text"]!r}, count={bond_status["count"]}'
            )
            return False

        Press_and_Drag(
            self.device,
            p1=self._set_position(source_position),
            p2=self._set_position(target_position),
            hold_duration=(0.2, 0.3),
            point_random=(-2, -2, 2, 2),
            swipe_duration=0.5,
            name=(
                f'CHESS_MOVE_ARAKAWA_GOLDFISH_SET_{source_position}'
                f'_TO_{target_position}'
            ),
        )

        def move_confirmed():
            if not self._is_preparation_mode() or self._is_shop_open():
                return True
            return (
                self._board_set_state(source_position) == 'empty'
                and self._board_set_state(target_position) == 'occupied'
            )

        confirmed = self._wait_chess_action_state(move_confirmed)
        if not self._is_preparation_mode() or self._is_shop_open():
            self._set_goldfish_relocation_pending(True, source=pending_source)
            logger.warning(
                'Abort Chess Arakawa goldfish relocation confirmation: '
                f'source={source_position}, target={target_position}, '
                f'source_kind={pending_source}, left preparation or shop opened'
            )
            return False
        source_state_after = self._board_set_state(source_position)
        target_state_after = self._board_set_state(target_position)
        if not (
            confirmed
            and source_state_after == 'empty'
            and target_state_after == 'occupied'
        ):
            if source_state_after == 'occupied':
                self._record_arakawa_goldfish_position(
                    source_position,
                    identified=True,
                )
                self._set_goldfish_relocation_pending(True, source=pending_source)
            else:
                # 搬运后画面结果不明时不再假定金鱼已经落在目标格。
                self._clear_arakawa_goldfish_position(clear_placed=False)
            logger.warning(
                'Chess goldfish move unconfirmed: '
                f'source_kind={pending_source}, '
                f'source={source_position}({source_state_after}), '
                f'target={target_position}({target_state_after})'
            )
            return False

        self._invalidate_board_slot(
            source_position,
            'goldfish_moved_out',
            clear_identity=True,
        )
        protected_positions = set(protected_before)
        protected_positions.discard(source_position)
        protected_positions.add(target_position)
        self._player_deployed_positions = protected_positions
        self._mark_arakawa_goldfish_placed(target_position)
        logger.info(
            'Move Chess identified Arakawa goldfish: '
            f'{source_position} -> {target_position}, '
            f'source_kind={pending_source}, verified_landing=True'
        )
        return True

    def _active_arakawa_names(self) -> set[str]:
        return {name for name in getattr(self, '_board_lineup_names', set())
                if self.ARAKAWA_BOND_NAME in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ())
                or '荒川纹章' in self._shikigami_attributes(name)[1:]}

    def _goldfish_formation_baseline(self, next_name, emblem=False):
        """只在下一次上阵/纹章装备会形成二荒川时保存占位快照。"""
        active = self._active_arakawa_names()
        if (getattr(self, '_arakawa_goldfish_current_position', None) is not None
                or len(active) != 1 or next_name in active
                or self._arakawa_goldfish_target_position() is None):
            return None
        if not emblem and next_name not in self._lineup_arakawa_names():
            return None
        slots = self._board_frame_scan()
        if not slots:
            return None
        return {'before': {index for index, slot in enumerate(slots, 1) if slot['occupied']},
                'deployed_position': None if emblem else self.shikigami_deploy_positions[next_name]}

    def _inspect_arakawa_goldfish(
        self,
        set_index: int,
        *,
        max_attempts: int | None = 1,
    ) -> bool:
        """共用统一详情核名检查金鱼与式神身份；识别到的非金鱼式神同步写入格级记录。"""
        slot = int(set_index)
        result = self._inspect_board_set_shikigami(
            slot,
            max_attempts=1 if max_attempts is None else max(1, int(max_attempts)),
            click_name=f'chess_inspect_arakawa_goldfish_set_{slot}',
        )
        identified = bool(
            result.get('opened') and result.get('name') == 'arakawa_goldfish'
        )
        logger.info(f'Chess new Arakawa unit identified: set={slot}, goldfish={identified}')
        return identified

    def _run_preparation_regular_goldfish_once(
        self,
        *,
        context: str = 'regular',
        budget: PrepSliceBudget | None = None,
        allow_resume: bool = False,
    ) -> bool:
        """受预算控制执行常规找鱼；因切片预算中止时保留进度供后续续作。"""
        if getattr(self, '_arakawa_goldfish_placed', False):
            self._goldfish_lookup_needed = False
            self._pending_goldfish_probe = None
            return False
        if not self._is_preparation_mode() or self._is_shop_open():
            return False
        round_state = self._ensure_prep_goldfish_round_state()
        if round_state.get('goldfish_round_exhausted', False):
            return False
        if not allow_resume and round_state.get('regular_search_started', False):
            logger.debug(
                'Skip duplicate Chess regular goldfish search in same round: '
                f'round={round_state["round_no"]}, context={context}'
            )
            return False
        bond_status = self._check_arakawa_bond_qualified()
        if not bond_status['qualified']:
            if bond_status['reason'] == 'count_below_threshold':
                round_state['search_progress'].clear()
                self._goldfish_lookup_needed = False
            logger.debug(
                'Skip Chess regular goldfish opportunity until Arakawa >= 2: '
                f'context={context}, reason={bond_status["reason"]}, '
                f'raw={bond_status["raw_text"]!r}, count={bond_status["count"]}'
            )
            return False
        round_state['regular_search_started'] = True
        self._goldfish_lookup_needed = False
        return self._call_detect_pending_goldfish(context=context, budget=budget)

    def _call_detect_pending_goldfish(
        self,
        *,
        context: str = 'regular',
        budget: PrepSliceBudget | None = None,
    ) -> bool:
        """兼容测试替身签名调用 _detect_pending_arakawa_goldfish。"""
        if budget is None:
            return self._detect_pending_arakawa_goldfish(context=context)
        try:
            return self._detect_pending_arakawa_goldfish(
                context=context,
                budget=budget,
            )
        except TypeError:
            return self._detect_pending_arakawa_goldfish(context=context)

    def _detect_pending_arakawa_goldfish(
        self,
        *,
        context: str = 'regular',
        budget: PrepSliceBudget | None = None,
    ) -> bool:
        """在准备阶段关店、左栏「荒川 >= 2」且预算与余时允许时按优先序寻金鱼并搬运。"""
        self._reconcile_legacy_board_on_round_change()
        if getattr(self, '_arakawa_goldfish_placed', False):
            self._goldfish_lookup_needed = False
            self._pending_goldfish_probe = None
            return False
        target_position = self._arakawa_goldfish_target_position()
        if target_position is None:
            return False
        if not self._is_preparation_mode() or self._is_shop_open():
            logger.debug(
                'Skip Chess Arakawa goldfish lookup: not preparation or shop open '
                f'(context={context})'
            )
            return False
        pending_pos = getattr(self, '_arakawa_goldfish_current_position', None)
        if pending_pos is not None:
            pending_pos = int(pending_pos)
            if self._is_confirmed_arakawa_goldfish(pending_pos):
                if pending_pos == int(target_position):
                    self._mark_arakawa_goldfish_placed(pending_pos)
                    return False
                if budget is not None and budget.wall_exhausted():
                    budget.reason_stopped = budget.reason_stopped or 'slice_wall_exhausted'
                    return False
                if (
                    getattr(self, '_goldfish_relocation_pending', False)
                    or pending_pos != int(target_position)
                ):
                    moved = self._move_arakawa_goldfish(
                        pending_pos,
                        verify_vacated_source=self._is_blocking_goldfish_relocation_pending(
                            pending_pos
                        ),
                    )
                    if moved and budget is not None:
                        budget.actions_done += 1
                    return moved
            # 未经详情确认的旧位置记录不能当作已放好，清理后重新搜索。
            self._clear_arakawa_goldfish_position(clear_placed=False)

        bond_status = self._check_arakawa_bond_qualified()
        if not bond_status['qualified']:
            if bond_status['reason'] == 'count_below_threshold':
                self._ensure_prep_goldfish_round_state()['search_progress'].clear()
            logger.debug(
                'Skip Chess Arakawa goldfish lookup: '
                f'context={context}, reason={bond_status["reason"]}, '
                f'raw={bond_status["raw_text"]!r}, count={bond_status["count"]}'
            )
            return False

        remaining = self._read_remaining_time()
        if budget is not None:
            can_inspect, inspect_reason = budget.can_start_inspect(
                remaining,
                min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
            )
            if not can_inspect:
                logger.info(
                    'Defer Chess Arakawa goldfish lookup by slice budget: '
                    f'context={context}, remaining_time={remaining}, reason={inspect_reason}'
                )
                return False
        elif remaining is None or remaining < self.GOLDFISH_REGULAR_SEARCH_MIN_REMAINING:
            logger.info(
                'Skip Chess Arakawa goldfish lookup by remaining time: '
                f'context={context}, remaining_time={remaining}, '
                f'required>={self.GOLDFISH_REGULAR_SEARCH_MIN_REMAINING}'
            )
            return False

        round_state = self._ensure_prep_goldfish_round_state()
        inspected_slots = round_state['inspected_slots']
        player_positions = set(getattr(self, '_player_deployed_positions', set()))
        known_lineup_positions = self._known_deployed_lineup_positions()
        known_excluded = known_lineup_positions | player_positions
        pending = getattr(self, '_pending_goldfish_probe', None)
        latest_slots: list[dict] | None = None

        if pending is not None:
            pending_before = {int(pos) for pos in pending.get('before', set())}
            deployed_pos = (
                {int(pending['deployed_position'])}
                if pending.get('deployed_position') is not None
                else set()
            )
            probe_excluded = known_excluded | pending_before | deployed_pos

            def new_position_visible():
                nonlocal latest_slots
                if not self._is_preparation_mode() or self._is_shop_open():
                    return True
                slots = self._board_frame_scan()
                if not slots:
                    return False
                latest_slots = slots
                occupied = {
                    index for index, slot in enumerate(slots, 1) if slot['occupied']
                }
                return bool(occupied - probe_excluded)

            if not new_position_visible():
                self._wait_chess_action_state(new_position_visible)
            if not self._is_preparation_mode() or self._is_shop_open():
                return False
            if not self._check_arakawa_bond_qualified()['qualified']:
                return False
            slots = latest_slots if latest_slots is not None else self._board_frame_scan()
            extra_excluded = pending_before | deployed_pos
        else:
            slots = self._board_frame_scan()
            pending_before = set()
            deployed_pos = set()
            extra_excluded = set()

        if not slots:
            return False

        occupied = frozenset(
            index for index, slot in enumerate(slots, 1) if slot['occupied']
        )
        board_complete = all(
            slot.get('state') in ('occupied', 'empty') for slot in slots
        )
        ordered_all = self._sort_goldfish_candidate_slots(occupied - known_excluded - extra_excluded)
        search_progress = round_state['search_progress']
        confirmed_empty = {
            index for index, slot in enumerate(slots, 1) if slot.get('state') == 'empty'
        }
        # 已确认清空或登记为阵容位的格子，之后重新成为候选时可以再查。
        search_progress.difference_update(confirmed_empty | known_excluded)
        candidates = [
            pos for pos in ordered_all if pos not in inspected_slots and pos not in search_progress
        ]
        if not candidates and ordered_all and inspected_slots.isdisjoint(ordered_all):
            # 所有当前候选已查过一遍，等到后续回合才允许重查，避免永久跳过之前漏识别的格子。
            search_progress.clear()
            candidates = ordered_all

        if not candidates:
            round_state['goldfish_round_exhausted'] = True

        slot_11_status = slots[10].get('state', 'unknown') if len(slots) >= 11 else 'unknown'
        if 11 in occupied:
            if 11 in known_lineup_positions:
                slot_11_status = 'filtered:known_lineup_position'
            elif 11 in player_positions:
                slot_11_status = 'filtered:player_deployed_position'
            elif 11 in pending_before:
                slot_11_status = 'filtered:pending_before_snapshot'
            elif 11 in deployed_pos:
                slot_11_status = 'filtered:pending_deployed_position'
            elif 11 in inspected_slots:
                slot_11_status = 'filtered:already_inspected_this_round'
            elif 11 in search_progress:
                slot_11_status = 'filtered:already_inspected_in_search'
            else:
                slot_11_status = 'candidate_included'

        logger.info(
            'Chess regular Arakawa goldfish scan plan: '
            f'context={context}, remaining_time={remaining}, '
            f'occupied={sorted(occupied)}, board_complete={board_complete}, '
            f'ordered_all={ordered_all}, '
            f'already_inspected={sorted(inspected_slots)}, '
            f'search_progress={sorted(search_progress)}, '
            f'candidates={candidates}, slot_11={slot_11_status}'
        )

        for position in candidates:
            if not self._is_preparation_mode() or self._is_shop_open():
                logger.info(
                    'Stop Chess Arakawa goldfish lookup: mode left preparation or shop open'
                )
                return False
            if not self._check_arakawa_bond_qualified()['qualified']:
                return False
            remaining_now = self._read_remaining_time()
            if budget is not None:
                can_inspect_now, stop_reason = budget.can_start_inspect(
                    remaining_now,
                    min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                    min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
                )
                if not can_inspect_now:
                    logger.info(
                        'Stop Chess Arakawa goldfish lookup by slice budget before slot: '
                        f'set={position}, remaining_time={remaining_now}, reason={stop_reason}'
                    )
                    return False
            elif (
                remaining_now is None
                or remaining_now < self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING
            ):
                logger.info(
                    'Stop Chess Arakawa goldfish lookup before inspecting slot: '
                    f'set={position}, remaining_time={remaining_now}, '
                    f'required>={self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING}'
                )
                return False
            inspected_slots.add(position)
            search_progress.add(position)
            if budget is not None:
                budget.consume_inspect()
            if not self._inspect_arakawa_goldfish(position, max_attempts=1):
                if budget is not None and budget.inspects_used >= budget.max_inspects:
                    return False
                continue
            search_progress.clear()
            self._record_arakawa_goldfish_position(position, identified=True)
            self._pending_goldfish_probe = None
            self._goldfish_lookup_needed = False
            if budget is not None and budget.wall_exhausted():
                self._set_goldfish_relocation_pending(True, source='regular')
                return False
            moved = self._move_arakawa_goldfish(position)
            if moved and budget is not None:
                budget.actions_done += 1
            return moved
        round_state['goldfish_round_exhausted'] = True
        logger.debug(
            'Chess Arakawa goldfish not confirmed in remaining uninspected slots; '
            f'inspected_this_round={sorted(inspected_slots)}'
        )
        return False

    def _handle_goldfish_after_board_action_failure(self, set_index, action):
        """下阵失败仅处理已登记的金鱼，不再盲点未知式神详情。"""
        if (getattr(self, '_arakawa_goldfish_current_position', None) != int(set_index)
                or not self._is_preparation_mode()):
            return False
        return self._move_arakawa_goldfish(
            set_index,
            verify_vacated_source=self._is_blocking_goldfish_relocation_pending(
                set_index
            ),
        )

    def _find_hakuzosu_protect_hand_card(self) -> dict | None:
        """定位手牌中的守护之印。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(self.HAND_AREA),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'display_name': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def _hakuzosu_protect_hand_count(self) -> int:
        """统计完整手牌区中的守护之印数量。"""
        if self._hakuzosu_protect_target_position() is None:
            return 0
        return len(self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(self.HAND_AREA),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        ))

    def _hakuzosu_protect_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
    ) -> dict | None:
        """确认指定手牌框是否为守护之印，用于卖卡保护。"""
        if self._hakuzosu_protect_target_position() is None:
            return None
        matches = self.hakuzosu_protect_rule.match_all_any(
            self.device.image,
            roi=list(card_roi),
            threshold=self.hakuzosu_protect_rule.threshold,
            nms_threshold=0.3,
            frame_id=self.device.image_frame_id,
        )
        if not matches:
            return None
        score, x, y, width, height = max(matches, key=lambda item: item[0])
        return {
            'name': self.HAKUZOSU_PROTECT_NAME,
            'text': self.HAKUZOSU_PROTECT_DISPLAY_NAME,
            'score': score,
            'position': (x + width // 2, y + height // 2),
        }

    def equip_hakuzosu_protect_after_deploy(
        self,
        verified_names: set[str] | None = None,
    ) -> bool:
        """按阵容专属御魂配置尝试装备守护之印。"""
        target_position = self._hakuzosu_protect_target_position(
            verified_names
        )
        if target_position is None:
            return False
        target_name = self._shikigami_name_at_set(target_position)
        if target_name is None:
            return False
        protect, soul_1, soul_2 = self._shikigami_attributes(target_name)
        if protect is not None:
            return False
        if not self._is_preparation_mode():
            return False
        card = self._find_hakuzosu_protect_hand_card()
        if card is None:
            logger.debug(
                'Chess Hakuzosu protect card is not in hand after '
                'Byakuzou deployment'
            )
            return False
        logger.info(
            f'检测到{card["display_name"]}(功能)，'
            f'移动到{target_position}号位'
        )
        protect_before = self._hakuzosu_protect_hand_count()
        if not self._equip_soul_card(
            source=card['position'],
            set_index=int(target_position),
            operation_name=self.HAKUZOSU_PROTECT_NAME.upper(),
        ):
            return False
        confirmed = self._wait_hand_card_removed(
            protect_before,
            self._hakuzosu_protect_hand_count,
        )
        protect_after = self._hakuzosu_protect_hand_count()
        if not confirmed:
            logger.warning(
                'Chess Hakuzosu protect equip not confirmed: '
                f'{target_name} at set {target_position}, '
                f'hand_count={protect_before}->{protect_after}'
            )
            return False
        self._set_shikigami_attributes(
            target_name,
            (self.HAKUZOSU_PROTECT_DISPLAY_NAME, soul_1, soul_2),
        )
        logger.info(
            'Chess Hakuzosu protect equip confirmed: '
            f'{target_name} at set {target_position}'
        )
        return True

    def _equip_soul_card(
        self,
        source: tuple[int, int],
        set_index: int,
        operation_name: str,
    ) -> bool:
        """御魂及阵容特殊手牌共用入口；拖动前必须关闭商店。"""
        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess soul equipment: shop could not be closed, '
                f'operation={operation_name}'
            )
            return False
        target = self._soul_target_position(set_index)
        logger.debug(
            f'Equip Chess soul-type card {operation_name} to set '
            f'{set_index}: source={source}, target={target}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target,
            hold_duration=(0.2, 0.3),
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_EQUIP_SOUL_{operation_name}_SET_{set_index}',
        )
        return True

    def deploy_shikigami_hand_card(
        self,
        name: str,
        source: tuple[int, int],
    ) -> bool:
        """按当前策略站位拖动式神，并交叉确认是否上阵。"""
        set_index = self.shikigami_deploy_positions.get(name)
        if set_index is None:
            logger.warning(f'Chess shikigami has no deploy position: {name}')
            return False

        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess shikigami deployment: shop is not closed '
                f'before dragging {name}'
            )
            return False
        count_before = self._read_shikigami_count()
        hand_count_before = self._lineup_hand_card_match_count(name)
        hand_stars_before = self._lineup_hand_stars(name)
        actual_position = getattr(self, '_board_actual_positions', {}).get(name, set_index)
        same_board_unit = (name in getattr(self, '_board_lineup_names', set())
                           and actual_position == set_index)
        board_star_before = self._board_set_star(set_index) if same_board_unit else None
        target_occupied_before = self._board_set_has_shikigami(set_index)
        target_position = self._set_position(set_index)
        logger.debug(
            f'Deploy Chess shikigami {name} to set {set_index}, '
            f'source={source}, target={target_position}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target_position,
            hold_duration=(0.2, 0.3),
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_DEPLOY_{name.upper()}_SET_{set_index}',
        )
        self.close_shikigami_specifics_if_open()
        star_confirmations = 0
        confirmed_stars = None
        success_reason = None

        def deployed():
            nonlocal star_confirmations, confirmed_stars, success_reason
            if self.close_shikigami_specifics_if_open():
                star_confirmations = 0
                return False
            if self._lineup_hand_card_match_count(name) < hand_count_before:
                success_reason = 'hand_count_decreased'
                return True
            hand_stars = self._lineup_hand_stars(name)
            board_star = self._board_set_star(set_index) if same_board_unit else None
            hand_upgraded = (hand_stars_before is not None and hand_stars is not None
                             and len(hand_stars_before) == len(hand_stars)
                             and hand_stars > hand_stars_before)
            board_upgraded = (board_star_before is not None and board_star is not None
                              and board_star > board_star_before)
            if not (hand_upgraded or board_upgraded):
                star_confirmations = 0
                confirmed_stars = None
                return False
            current = (hand_stars, board_star)
            star_confirmations = star_confirmations + 1 if current == confirmed_stars else 1
            confirmed_stars = current
            success_reason = 'hand_star_increased' if hand_upgraded else 'board_star_increased'
            return star_confirmations >= 2

        succeeded = self._wait_chess_action_state(deployed)
        count_after = self._read_shikigami_count()
        hand_count_after = self._lineup_hand_card_match_count(name)
        target_occupied_after = self._board_set_has_shikigami(set_index)

        count_increased = False
        if count_before is not None and count_after is not None:
            count_increased = (
                count_after['current'] > count_before['current']
            )
        target_became_occupied = (
            not target_occupied_before and target_occupied_after
        )

        # 手牌减少或连续两帧确认星级提升，均视为本次上卡成功。
        if succeeded:
            logger.info(
                f'Chess shikigami deploy confirmed: {name} -> set {set_index}, '
                f'reason={success_reason}, hand_stars={hand_stars_before}->{self._lineup_hand_stars(name)}, '
                f'board_star={board_star_before}->{confirmed_stars[1] if confirmed_stars else None}, '
                f'board_count={count_before["current"] if count_before else "?"}'
                f'->{count_after["current"] if count_after else "?"}, '
                f'hand_count={hand_count_before}->{hand_count_after}, '
                f'target_occupied={target_occupied_before}'
                f'->{target_occupied_after}'
            )
            return True

        logger.warning(
            f'Chess shikigami deploy not confirmed: {name} -> set {set_index}, '
            f'board_count={count_before["current"] if count_before else "?"}'
            f'->{count_after["current"] if count_after else "?"}, '
            f'hand_count={hand_count_before}->{hand_count_after}, '
            f'target_occupied={target_occupied_before}'
            f'->{target_occupied_after}'
        )
        return False

    def _resolve_specifics_shikigami_name(self, texts: list[str]) -> str | None:
        """将详情页头部 OCR 文本映射到唯一式神罗马音；金鱼单独区分，歧义或不可读返回 None。"""
        cleaned_lines = []
        for raw in texts:
            normalized = self._normalize_ocr_text(raw)
            if not normalized:
                continue
            cleaned = ''.join(re.findall(r'[\u4e00-\u9fffA-Za-z]+', normalized))
            cleaned_lines.append((normalized, cleaned))
            if cleaned in ('金鱼', '金鱼助阵'):
                return 'arakawa_goldfish'

        exact_matches = []
        for normalized, cleaned in cleaned_lines:
            entry = resolve_shikigami(cleaned) or resolve_shikigami(normalized)
            if entry is not None and entry.romaji not in exact_matches:
                exact_matches.append(entry.romaji)
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            return None

        # 精确映射未命中时，仅对 2 字及以上非羁绊文本走编辑距离兜底并要求唯一领先。
        pure_bonds = KNOWN_BONDS - {'荒川之主'}
        fuzzy_best: dict[str, float] = {}
        for _, cleaned in cleaned_lines:
            if len(cleaned) < 2 or cleaned in pure_bonds or cleaned in ('金鱼', '金鱼助阵'):
                continue
            for entry in SHIKIGAMI_ENTRIES:
                if len(entry.chinese_name) < 2:
                    continue
                if abs(len(cleaned) - len(entry.chinese_name)) > 1:
                    continue
                matched, similarity, _ = self._fuzzy_text_match(
                    entry.chinese_name,
                    cleaned,
                )
                if matched and similarity > fuzzy_best.get(entry.romaji, 0.0):
                    fuzzy_best[entry.romaji] = similarity
        if not fuzzy_best:
            return None
        ranked = sorted(fuzzy_best.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 0.10:
            return ranked[0][0]
        return None

    def _extract_detail_name_roi_crop(
        self,
        image,
    ) -> tuple[tuple[int, int, int, int] | None, np.ndarray | None]:
        """安全裁剪 O_DETAIL_NAME 标注区域，无法定位合法 ndarray 区域时返回 (None, None)。"""
        if not hasattr(self, 'O_DETAIL_NAME') or not isinstance(image, np.ndarray) or image.ndim < 3:
            return None, None
        x, y, w, h = (int(v) for v in self.O_DETAIL_NAME.roi)
        img_h, img_w = image.shape[:2]
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > img_w or y + h > img_h:
            return None, None
        return (x, y, w, h), image[y:y + h, x:x + w]

    def _prepare_specifics_detail_name_image(
        self,
        image,
    ) -> tuple[object, np.ndarray | None, np.ndarray | None, bool]:
        """隔离 detail_name 框内纯白前景标题文字，去除半透明底层榜单玩家名与底部标签。"""
        roi, raw_crop = self._extract_detail_name_roi_crop(image)
        if roi is None or raw_crop is None:
            return image, None, None, False
        min_ch = raw_crop.min(axis=2)
        white_mask = (
            min_ch >= int(self.SPECIFICS_DETAIL_NAME_WHITE_MIN_CHANNEL)
        )
        if int(np.count_nonzero(white_mask)) < int(self.SPECIFICS_DETAIL_NAME_WHITE_MIN_PIXELS):
            # 低对比或合成纯噪声测试图保持原图透传，不影响既有 RuleOcr 行为。
            return image, raw_crop.copy(), None, False

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(white_mask.astype(np.uint8) * 255, kernel, iterations=1)
        isolated_crop = np.full_like(raw_crop, (24, 24, 28))
        fg = dilated > 0
        isolated_crop[fg] = raw_crop[fg]

        x, y, w, h = roi
        prepared = image.copy()
        prepared[y:y + h, x:x + w] = isolated_crop
        return prepared, raw_crop.copy(), isolated_crop.copy(), True

    def _are_specifics_detail_frames_stable(
        self,
        prev_image,
        cur_image,
    ) -> tuple[bool, dict]:
        """判断连续两帧的 detail_name 区域亮前景是否已稳定（避开底层低对比动态干扰）。"""
        _, prev_crop = self._extract_detail_name_roi_crop(prev_image)
        _, cur_crop = self._extract_detail_name_roi_crop(cur_image)
        if prev_crop is None or cur_crop is None or prev_crop.shape != cur_crop.shape:
            return True, {'reason': 'no_comparable_crop', 'changed_bright': 0, 'mean_diff': 0.0}

        prev_gray = self._to_grayscale(prev_crop)
        cur_gray = self._to_grayscale(cur_crop)
        bright_floor = int(self.SPECIFICS_DETAIL_NAME_STABLE_BRIGHT_FLOOR)
        bright_mask = np.maximum(prev_gray, cur_gray) >= bright_floor
        abs_diff = np.abs(cur_gray.astype(np.int16) - prev_gray.astype(np.int16))
        changed_bright = int(np.count_nonzero(bright_mask & (abs_diff > 25)))
        mean_diff = float(abs(float(cur_gray.mean()) - float(prev_gray.mean())))
        stable = (
            changed_bright <= int(self.SPECIFICS_DETAIL_NAME_STABLE_MAX_CHANGED_PIXELS)
            and mean_diff <= float(self.SPECIFICS_DETAIL_NAME_STABLE_MAX_MEAN_DIFF)
        )
        return stable, {
            'changed_bright': changed_bright,
            'mean_diff': round(mean_diff, 2),
        }

    def _wait_specifics_detail_name_stable(
        self,
        *,
        deadline: float,
    ) -> dict:
        """在共享确认预算内等待详情标识有效且 detail_name 区域连续新帧稳定。"""
        prev_frame = getattr(self.device, 'image', None)
        can_screenshot = callable(getattr(self, 'screenshot', None))
        if not can_screenshot or not hasattr(self, 'O_DETAIL_NAME'):
            return {
                'stable': True,
                'reason': 'skip_no_screenshot',
                'frames_checked': 1,
                'last_frame': prev_frame,
                'last_frame_id': getattr(self.device, 'image_frame_id', None),
            }
        if time.monotonic() >= deadline:
            return {
                'stable': False,
                'reason': 'detail_name_unstable',
                'frames_checked': 1,
                'last_frame': prev_frame,
                'last_frame_id': getattr(self.device, 'image_frame_id', None),
            }

        frames_checked = 1
        last_stats = {'changed_bright': None, 'mean_diff': None}
        while time.monotonic() < deadline:
            if hasattr(self, '_is_preparation_mode') and not self._is_preparation_mode():
                return {
                    'stable': False,
                    'reason': 'not_preparation',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': prev_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            if hasattr(self, '_is_shop_open') and self._is_shop_open():
                return {
                    'stable': False,
                    'reason': 'shop_open',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': prev_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            if hasattr(self.device, 'stuck_record_clear'):
                self.device.stuck_record_clear()
            self.screenshot()
            cur_frame = getattr(self.device, 'image', None)
            frames_checked += 1
            if hasattr(self, '_is_preparation_mode') and not self._is_preparation_mode():
                return {
                    'stable': False,
                    'reason': 'not_preparation',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': cur_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            if hasattr(self, '_is_shop_open') and self._is_shop_open():
                return {
                    'stable': False,
                    'reason': 'shop_open',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': cur_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            if hasattr(self, 'I_SHIKIGAMI_SPECIFICS') and not self.appear(self.I_SHIKIGAMI_SPECIFICS):
                return {
                    'stable': False,
                    'reason': 'specifics_closed',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': cur_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            stable, last_stats = self._are_specifics_detail_frames_stable(prev_frame, cur_frame)
            if stable:
                return {
                    'stable': True,
                    'reason': 'stable',
                    'frames_checked': frames_checked,
                    'stats': last_stats,
                    'last_frame': cur_frame,
                    'last_frame_id': getattr(self.device, 'image_frame_id', None),
                }
            prev_frame = cur_frame

        return {
            'stable': False,
            'reason': 'detail_name_unstable',
            'frames_checked': frames_checked,
            'stats': last_stats,
            'last_frame': prev_frame,
            'last_frame_id': getattr(self.device, 'image_frame_id', None),
        }

    def _read_specifics_shikigami_identity(
        self,
        *,
        deadline: float | None = None,
        max_reads: int | None = None,
    ) -> tuple[str | None, list[str]]:
        """在详情页已打开的画面上识别身份：金鱼看专属标识，普通式神仅读 detail_name。"""
        if deadline is None:
            deadline = time.monotonic() + float(
                getattr(self, 'ACTION_ICON_WAIT_TIMEOUT', 3.0)
            )
        default_reads = getattr(self, 'SPECIFICS_DETAIL_NAME_MAX_READS', 3)
        read_limit = max(
            1,
            int(default_reads if max_reads is None else max_reads),
        )
        can_screenshot = callable(getattr(self, 'screenshot', None))
        last_texts: list[str] = []
        observed_raw_texts: list[str] = []
        reads_done = 0
        self._last_detail_name_evidence = None

        for attempt in range(1, read_limit + 1):
            if attempt > 1:
                if not can_screenshot or time.monotonic() >= deadline:
                    break
                if (
                    hasattr(self, '_is_preparation_mode')
                    and not self._is_preparation_mode()
                ):
                    break
                if hasattr(self, '_is_shop_open') and self._is_shop_open():
                    break
                self.screenshot()
                if (
                    hasattr(self, '_is_preparation_mode')
                    and not self._is_preparation_mode()
                ):
                    break
                if hasattr(self, '_is_shop_open') and self._is_shop_open():
                    break
                if (
                    hasattr(self, 'I_SHIKIGAMI_SPECIFICS')
                    and not self.appear(self.I_SHIKIGAMI_SPECIFICS)
                ):
                    logger.debug(
                        'Stop Chess detail_name reread: specifics panel closed'
                    )
                    break

            reads_done += 1
            if hasattr(self, 'I_CHECK_GOLDFISH') and self.appear(self.I_CHECK_GOLDFISH):
                logger.info(
                    'Chess specifics identity matched goldfish marker: '
                    f'rule=I_CHECK_GOLDFISH, attempt={attempt}/{read_limit}, '
                    'raw=[\'金鱼·助阵\'], resolved=arakawa_goldfish'
                )
                return 'arakawa_goldfish', ['金鱼·助阵']

            if not hasattr(self, 'O_DETAIL_NAME'):
                logger.warning(
                    'Chess specifics detail_name OCR unavailable: missing O_DETAIL_NAME'
                )
                return None, []

            cur_frame = getattr(self.device, 'image', None)
            cur_frame_id = getattr(self.device, 'image_frame_id', None)
            prepared_img, raw_crop, isolated_crop, isolated_used = (
                self._prepare_specifics_detail_name_image(cur_frame)
            )
            raw_value = self.O_DETAIL_NAME.ocr(prepared_img)
            raw_text = '' if raw_value is None else str(raw_value)
            normalized = self._normalize_ocr_text(raw_text)
            texts = [raw_text] if normalized else []
            last_texts = texts
            if raw_text and raw_text not in observed_raw_texts:
                observed_raw_texts.append(raw_text)

            resolved = self._resolve_specifics_shikigami_name(texts)
            self._last_detail_name_evidence = {
                'frame': cur_frame.copy() if isinstance(cur_frame, np.ndarray) else None,
                'frame_id': cur_frame_id,
                'roi': tuple(self.O_DETAIL_NAME.roi),
                'raw_crop': raw_crop,
                'isolated_crop': isolated_crop,
                'isolated_used': isolated_used,
                'raw_text': raw_text,
                'resolved': resolved,
            }
            if resolved is not None:
                logger.info(
                    'Chess specifics OCR read detail_name: '
                    f'rule=detail_name, roi={tuple(self.O_DETAIL_NAME.roi)}, '
                    f'attempt={attempt}/{read_limit}, isolated={isolated_used}, '
                    f'raw={raw_text!r}, resolved={resolved}'
                )
                return resolved, texts

            logger.debug(
                'Chess specifics OCR detail_name unresolved: '
                f'rule=detail_name, roi={tuple(self.O_DETAIL_NAME.roi)}, '
                f'attempt={attempt}/{read_limit}, isolated={isolated_used}, '
                f'raw={raw_text!r}'
            )

        final_raw_texts = (
            last_texts
            or ([observed_raw_texts[-1]] if observed_raw_texts else [])
        )
        detail_roi = (
            tuple(self.O_DETAIL_NAME.roi)
            if hasattr(self, 'O_DETAIL_NAME')
            else None
        )
        logger.info(
            'Chess specifics OCR read detail_name failed: '
            f'rule=detail_name, roi={detail_roi}, '
            f'frame_id={getattr(self.device, "image_frame_id", None)}, '
            f'attempts={reads_done}/{read_limit}, '
            f'raw={final_raw_texts}, resolved=None'
        )
        return None, final_raw_texts

    def _match_specifics_gray_roi(
        self,
        image: np.ndarray,
        roi_xywh: tuple[int, int, int, int],
    ) -> tuple[float | None, tuple[int, int] | None]:
        """在指定 (x, y, w, h) 区域内对 I_SHIKIGAMI_SPECIFICS 做灰度匹配定位。"""
        spec_rule = getattr(self, 'I_SHIKIGAMI_SPECIFICS', None)
        tpl = getattr(spec_rule, 'image', None)
        if not isinstance(image, np.ndarray) or not isinstance(tpl, np.ndarray):
            return None, None
        img_h, img_w = image.shape[:2]
        x, y, w, h = (int(v) for v in roi_xywh)
        left = max(0, x)
        top = max(0, y)
        right = min(img_w, x + w)
        bottom = min(img_h, y + h)
        if right <= left or bottom <= top:
            return None, None
        tpl_gray = self._to_grayscale(tpl)
        crop_gray = self._to_grayscale(image[top:bottom, left:right])
        if crop_gray.shape[0] < tpl_gray.shape[0] or crop_gray.shape[1] < tpl_gray.shape[1]:
            return None, None
        result = cv2.matchTemplate(crop_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        score = float(max_val) if np.isfinite(max_val) else 0.0
        pos = (left + int(max_loc[0]), top + int(max_loc[1]))
        return score, pos

    def _save_specifics_evidence_bundle(
        self,
        set_index: int,
        *,
        images: dict[str, np.ndarray],
        lines: list[str],
        label: str,
    ) -> Path | None:
        """在原有每局次数上限内按站位去重保存详情取证截图与诊断文本。"""
        save_enabled = bool(
            getattr(
                getattr(getattr(getattr(self, 'config', None), 'script', None), 'error', None),
                'save_error',
                False,
            )
        )
        saved_slots = getattr(self, '_specifics_evidence_saved_slots', None)
        if not isinstance(saved_slots, set):
            saved_slots = set()
            self._specifics_evidence_saved_slots = saved_slots
        save_count = int(getattr(self, '_specifics_evidence_save_count', 0) or 0)
        if not (save_enabled and save_count < self.SPECIFICS_EVIDENCE_MAX_PER_GAME and int(set_index) not in saved_slots):
            return None
        config_name = getattr(getattr(self, 'config', None), 'config_name', 'chess') or 'chess'
        folder = Path(ERROR_LOG_ROOT) / build_error_log_dir_name(
            str(config_name),
            int(time.time() * 1000),
        )
        folder.mkdir(parents=True, exist_ok=True)
        for filename, mat in images.items():
            if isinstance(mat, np.ndarray):
                save_image(np.asarray(mat), str(folder / filename))
        (folder / 'log.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        saved_slots.add(int(set_index))
        self._specifics_evidence_save_count = save_count + 1
        logger.warning(
            f'Chess {label} evidence saved to {folder} (set={set_index})'
        )
        return folder

    def _record_detail_name_failure_evidence(
        self,
        set_index: int,
        *,
        reason: str,
        raw_texts: list[str],
        resolved: str | None,
        frame_override=None,
        frame_id_override=None,
    ) -> None:
        """记录 detail_name 读取或稳定性失败的诊断字段，并在 save_error 开启时有界落盘裁剪与原图。"""
        evidence = getattr(self, '_last_detail_name_evidence', None) or {}
        frame = frame_override if isinstance(frame_override, np.ndarray) else evidence.get('frame')
        frame_id = frame_id_override if frame_id_override is not None else evidence.get('frame_id')
        roi = evidence.get('roi') or (
            tuple(self.O_DETAIL_NAME.roi) if hasattr(self, 'O_DETAIL_NAME') else None
        )
        raw_crop = evidence.get('raw_crop')
        if raw_crop is None and isinstance(frame, np.ndarray):
            _, extracted = self._extract_detail_name_roi_crop(frame)
            if extracted is not None:
                raw_crop = extracted.copy()
        isolated_crop = evidence.get('isolated_crop')
        spec_score = None
        if isinstance(frame, np.ndarray) and hasattr(self, 'I_SHIKIGAMI_SPECIFICS'):
            rx, ry, rw, rh = (int(v) for v in self.I_SHIKIGAMI_SPECIFICS.roi_back)
            spec_score, _ = self._match_specifics_gray_roi(frame, (rx, ry, rw, rh))
        score_txt = f'{spec_score:.3f}' if spec_score is not None else 'None'
        logger.warning(
            'Chess detail_name diagnosis: '
            f'set={set_index}, reason={reason}, frame_id={frame_id}, roi={roi}, '
            f'specifics_score={score_txt}, isolated={evidence.get("isolated_used")}, '
            f'raw={raw_texts}, resolved={resolved}'
        )
        try:
            images = {}
            if isinstance(frame, np.ndarray):
                images['chess_detail_name_1_full.png'] = frame
            if isinstance(raw_crop, np.ndarray):
                images['chess_detail_name_2_raw_crop.png'] = raw_crop
            if isinstance(isolated_crop, np.ndarray):
                images['chess_detail_name_3_isolated_crop.png'] = isolated_crop
            if not images:
                return
            round_no = getattr(self, '_current_round_no', None)
            lines = [
                f'百鬼棋局 detail_name OCR 诊断：站位 {set_index} 号，回合 {round_no}',
                f'失败原因：{reason}',
                f'帧标识：{frame_id}',
                f'detail_name ROI：{roi}',
                f'I_SHIKIGAMI_SPECIFICS 匹配得分：{score_txt}',
                f'白字隔离生效：{evidence.get("isolated_used")}',
                f'原始 OCR：{raw_texts}',
                f'解析结果：{resolved}',
            ]
            self._save_specifics_evidence_bundle(
                set_index, images=images, lines=lines, label='detail_name failure',
            )
        except Exception as exc:
            logger.warning(f'Chess detail_name evidence save failed (set={set_index}): {exc!r}')

    def _diagnose_and_save_specifics_failure(
        self,
        set_index: int,
        *,
        click_point: tuple[int, int],
        before_frame,
        after_frame,
    ) -> dict:
        """详情未识别时轻量记录面板变化与模板得分；save_error 开启时有界留存点击前后原图。"""
        diag = {
            'panel_diff_mean': None,
            'panel_diff_ratio': None,
            'roi_score': None,
            'expanded_score': None,
            'expanded_pos': None,
            'goldfish_visible': False,
        }
        try:
            valid_before = isinstance(before_frame, np.ndarray) and before_frame.ndim >= 2
            valid_after = isinstance(after_frame, np.ndarray) and after_frame.ndim >= 2
            if valid_before and valid_after:
                px1, py1, px2, py2 = self.SPECIFICS_PANEL_ROI
                max_h = min(before_frame.shape[0], after_frame.shape[0], int(py2))
                max_w = min(before_frame.shape[1], after_frame.shape[1], int(px2))
                x1, y1 = max(0, int(px1)), max(0, int(py1))
                if max_h > y1 and max_w > x1:
                    b_crop = before_frame[y1:max_h, x1:max_w].astype(np.int16)
                    a_crop = after_frame[y1:max_h, x1:max_w].astype(np.int16)
                    diff = np.abs(a_crop - b_crop)
                    max_ch = diff.max(axis=2) if diff.ndim == 3 else diff
                    diag['panel_diff_mean'] = float(np.mean(max_ch))
                    diag['panel_diff_ratio'] = float(np.mean(max_ch > 15))
            if valid_after and hasattr(self, 'I_SHIKIGAMI_SPECIFICS'):
                spec_rule = self.I_SHIKIGAMI_SPECIFICS
                rx, ry, rw, rh = (int(v) for v in spec_rule.roi_back)
                diag['roi_score'], _ = self._match_specifics_gray_roi(after_frame, (rx, ry, rw, rh))
                ex1, ey1, ex2, ey2 = self.SPECIFICS_EXPANDED_SEARCH_ROI
                diag['expanded_score'], diag['expanded_pos'] = self._match_specifics_gray_roi(
                    after_frame,
                    (ex1, ey1, ex2 - ex1, ey2 - ey1),
                )
            if hasattr(self, 'I_CHECK_GOLDFISH'):
                diag['goldfish_visible'] = bool(self.appear(self.I_CHECK_GOLDFISH))
        except Exception as exc:
            logger.debug(f'Chess specifics failure diagnostics skipped: {exc!r}')

        mean_txt = f'{diag["panel_diff_mean"]:.2f}' if diag['panel_diff_mean'] is not None else 'None'
        ratio_txt = f'{diag["panel_diff_ratio"]:.4f}' if diag['panel_diff_ratio'] is not None else 'None'
        roi_txt = f'{diag["roi_score"]:.3f}' if diag['roi_score'] is not None else 'None'
        exp_txt = f'{diag["expanded_score"]:.3f}' if diag['expanded_score'] is not None else 'None'
        logger.warning(
            'Chess board slot specifics could not be opened: '
            f'set={set_index}, click={click_point}, '
            f'panel_diff_mean={mean_txt}, panel_diff_ratio={ratio_txt}, '
            f'roi_score={roi_txt}, expanded_best=({exp_txt}, {diag["expanded_pos"]}), '
            f'goldfish_visible={diag["goldfish_visible"]}'
        )

        try:
            if isinstance(before_frame, np.ndarray) and isinstance(after_frame, np.ndarray):
                round_no = getattr(self, '_current_round_no', None)
                spec_roi = (
                    tuple(self.I_SHIKIGAMI_SPECIFICS.roi_back)
                    if hasattr(self, 'I_SHIKIGAMI_SPECIFICS')
                    else None
                )
                lines = [
                    f'百鬼棋局详情页未打开诊断：站位 {set_index} 号，回合 {round_no}',
                    f'点击坐标：{click_point}',
                    f'右半区面板变化 {self.SPECIFICS_PANEL_ROI}：mean={mean_txt}，ratio(>15)={ratio_txt}',
                    f'原模板区域 {spec_roi} 灰度得分：roi_score={roi_txt}',
                    f'扩大区域 {self.SPECIFICS_EXPANDED_SEARCH_ROI} 最佳命中：score={exp_txt}，pos={diag["expanded_pos"]}',
                    f'金鱼标志可见：{diag["goldfish_visible"]}',
                    '截图文件：chess_specifics_1_before_click.png（点击前），chess_specifics_2_after_click.png（等待超时末帧）',
                ]
                self._save_specifics_evidence_bundle(
                    set_index,
                    images={
                        'chess_specifics_1_before_click.png': before_frame,
                        'chess_specifics_2_after_click.png': after_frame,
                    },
                    lines=lines,
                    label='specifics failure',
                )
        except Exception as exc:
            logger.warning(f'Chess specifics evidence save failed (set={set_index}): {exc!r}')
        return diag

    def _inspect_board_set_shikigami(
        self,
        set_index: int,
        *,
        max_attempts: int | None = None,
        click_name: str | None = None,
    ) -> dict:
        """打开目标站位详情页并核对式神身份，默认最多点 1 次，读完后确保关闭并同步格级记录。"""
        if not self._is_preparation_mode():
            return {
                'opened': False,
                'name': None,
                'raw_texts': [],
                'reason': 'not_preparation',
                'clicked': False,
            }
        if self._is_shop_open():
            return {
                'opened': False,
                'name': None,
                'raw_texts': [],
                'reason': 'shop_open',
                'clicked': False,
            }
        try:
            x, y = self._set_position(set_index)
        except GameStuckError:
            logger.warning(
                f'Chess board slot specifics skipped: anchor missing for set {set_index}'
            )
            return {
                'opened': False,
                'name': None,
                'raw_texts': [],
                'reason': 'anchor_missing',
                'clicked': False,
            }
        rule = RuleClick(
            roi_front=(x - 8, y - 8, 16, 16),
            roi_back=(x - 8, y - 8, 16, 16),
            name=click_name or f'chess_inspect_board_set_{set_index}',
        )
        attempts = 1 if max_attempts is None else max(1, int(max_attempts))
        before_frame = None
        any_clicked = False
        for _ in range(attempts):
            if not self._is_preparation_mode():
                self.close_shikigami_specifics_if_open()
                return {
                    'opened': False,
                    'name': None,
                    'raw_texts': [],
                    'reason': 'not_preparation',
                    'clicked': any_clicked,
                }
            if self._is_shop_open():
                self.close_shikigami_specifics_if_open()
                return {
                    'opened': False,
                    'name': None,
                    'raw_texts': [],
                    'reason': 'shop_open',
                    'clicked': any_clicked,
                }
            # 若前序详情页仍未关闭，先关闭再点击目标站位，避免直接读到旧面板或切换过渡帧。
            if hasattr(self, 'I_SHIKIGAMI_SPECIFICS') and self.appear(self.I_SHIKIGAMI_SPECIFICS):
                if not self.close_shikigami_specifics_if_open():
                    return {
                        'opened': False,
                        'name': None,
                        'raw_texts': [],
                        'reason': 'previous_specifics_not_closed',
                        'clicked': any_clicked,
                    }
            cur_img = getattr(self.device, 'image', None)
            before_frame = cur_img.copy() if isinstance(cur_img, np.ndarray) else None
            self.device.click_record_remove(rule)
            self.click(rule)
            any_clicked = True
            attempt_deadline = time.monotonic() + float(
                getattr(self, 'ACTION_ICON_WAIT_TIMEOUT', 3.0)
            )
            if not self._wait_chess_action_state(
                lambda: self.appear(self.I_SHIKIGAMI_SPECIFICS)
            ):
                if not self._is_preparation_mode():
                    self.close_shikigami_specifics_if_open()
                    return {
                        'opened': False,
                        'name': None,
                        'raw_texts': [],
                        'reason': 'not_preparation',
                        'clicked': any_clicked,
                    }
                if self._is_shop_open():
                    self.close_shikigami_specifics_if_open()
                    return {
                        'opened': False,
                        'name': None,
                        'raw_texts': [],
                        'reason': 'shop_open',
                        'clicked': any_clicked,
                    }
                continue
            try:
                stability = self._wait_specifics_detail_name_stable(
                    deadline=attempt_deadline,
                )
                if not stability['stable']:
                    stab_reason = stability['reason']
                    if stab_reason in ('not_preparation', 'shop_open'):
                        return {
                            'opened': False,
                            'name': None,
                            'raw_texts': [],
                            'reason': stab_reason,
                            'clicked': any_clicked,
                        }
                    self._record_detail_name_failure_evidence(
                        set_index,
                        reason=stab_reason,
                        raw_texts=[],
                        resolved=None,
                        frame_override=stability.get('last_frame'),
                        frame_id_override=stability.get('last_frame_id'),
                    )
                    return {
                        'opened': stab_reason != 'specifics_closed',
                        'name': None,
                        'raw_texts': [],
                        'reason': stab_reason,
                        'clicked': any_clicked,
                    }
                identified, raw_texts = self._read_specifics_shikigami_identity(
                    deadline=attempt_deadline,
                )
            finally:
                self.close_shikigami_specifics_if_open()
            if identified is None:
                self._record_detail_name_failure_evidence(
                    set_index,
                    reason='name_unreadable',
                    raw_texts=raw_texts,
                    resolved=None,
                )
            used_rule = (
                'I_CHECK_GOLDFISH'
                if identified == 'arakawa_goldfish' and raw_texts == ['金鱼·助阵']
                else 'detail_name'
            )
            logger.info(
                f'Chess board slot specifics inspected: set={set_index}, '
                f'rule={used_rule}, identified={identified or "未识别"}, '
                f'raw={raw_texts}'
            )
            inspect_result = {
                'opened': True,
                'name': identified,
                'raw_texts': raw_texts,
                'reason': 'identified' if identified else 'name_unreadable',
                'clicked': any_clicked,
            }
            self._record_slot_inspection_result(set_index, inspect_result)
            return inspect_result
        after_frame = getattr(self.device, 'image', None)
        self._diagnose_and_save_specifics_failure(
            set_index,
            click_point=(x, y),
            before_frame=before_frame,
            after_frame=after_frame,
        )
        self.close_shikigami_specifics_if_open()
        return {
            'opened': False,
            'name': None,
            'raw_texts': [],
            'reason': 'specifics_not_opened',
            'clicked': any_clicked,
        }

    def _snapshot_lineup_hand_cards(self) -> dict[str, dict[str, Any]]:
        """快照全手牌阵容卡（张数、已知星级序列与仅全星已知时可用的 1 星等效 copy_units）。"""
        grouped: dict[str, list[int | None]] = {}
        for card in self._frame_card_scan('card'):
            grouped.setdefault(card['name'], []).append(card.get('star'))
        snapshot: dict[str, dict[str, Any]] = {}
        for unit_name, stars in grouped.items():
            all_known = all(star in (1, 2, 3) for star in stars)
            copy_units = (
                sum(3 ** (int(star) - 1) for star in stars)
                if all_known
                else None
            )
            snapshot[unit_name] = {
                'count': len(stars),
                'stars': tuple(sorted(int(s) for s in stars)) if all_known else None,
                'copy_units': copy_units,
            }
        return snapshot

    @staticmethod
    def _hand_snapshot_returned_or_upgraded(
        prev_snap: dict[str, Any] | None,
        after_snap: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        """对比前后端全手牌快照，安全判定他卡是否回手或回手自动三合一升星。"""
        before = prev_snap or {}
        after = after_snap or {}
        cnt_before = int(before.get('count', 0) or 0)
        cnt_after = int(after.get('count', 0) or 0)
        if cnt_after > cnt_before:
            return True, f'hand_count_{cnt_before}_to_{cnt_after}'
        cu_before = before.get('copy_units')
        cu_after = after.get('copy_units')
        if cu_before is not None and cu_after is not None and cu_after > cu_before:
            return True, f'copy_units_{cu_before}_to_{cu_after}'
        stars_before = before.get('stars')
        stars_after = after.get('stars')
        if (
            stars_before is not None
            and stars_after is not None
            and max(stars_after, default=0) > max(stars_before, default=0)
        ):
            return True, f'returned_star_upgrade_{stars_before}_to_{stars_after}'
        return False, 'unchanged_or_uncertain'

    def _reconcile_displaced_slot_occupants(
        self,
        set_index: int,
        deployed_name: str,
        previous_occupants: list[str],
        prev_hand_counts_before: dict[str, int],
        count_before: dict | None,
        count_after: dict | None,
        *,
        hand_snapshot_before: dict[str, dict[str, Any]] | None = None,
        hand_snapshot_after: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        """确认新式神占领目标格后，结合全手牌快照精准处理原格棋子去向并登记高优回手待办。"""
        dispositions: dict[str, str] = {}
        slots_table = self._board_slots_table()
        newly_occupied = self._compute_newly_occupied_slots(
            count_before,
            count_after,
            exclude_slot=set_index,
        )
        snap_before = hand_snapshot_before or {}
        snap_after = (
            hand_snapshot_after
            if hand_snapshot_after is not None
            else self._snapshot_lineup_hand_cards()
        )
        # 优先并入同一目标格有效的旧阵容占格记录
        rec_at_slot = slots_table[int(set_index)]
        occupants = list(previous_occupants)
        prev_slot_ident = rec_at_slot.get('identity')
        if (
            rec_at_slot.get('kind') == 'lineup'
            and prev_slot_ident
            and prev_slot_ident != deployed_name
            and prev_slot_ident not in occupants
        ):
            occupants.append(prev_slot_ident)

        for prev_name in occupants:
            if prev_name == deployed_name:
                continue
            hand_before = int(
                (snap_before.get(prev_name) or {}).get(
                    'count',
                    prev_hand_counts_before.get(prev_name, 0),
                )
                or 0
            )
            hand_after = int(
                (snap_after.get(prev_name) or {}).get(
                    'count',
                    self._lineup_hand_card_match_count(prev_name),
                )
                or 0
            )
            returned, return_reason = self._hand_snapshot_returned_or_upgraded(
                snap_before.get(prev_name, {'count': hand_before, 'stars': None, 'copy_units': None}),
                snap_after.get(prev_name, {'count': hand_after, 'stars': None, 'copy_units': None}),
            )
            if returned:
                self._mark_board_unit_returned_to_hand(
                    prev_name,
                    from_slot=int(set_index),
                    reason='displaced_by_deploy',
                )
                dispositions[prev_name] = 'returned_to_hand'
                logger.info(
                    'Chess displaced occupant confirmed back in hand: '
                    f'name={prev_name}, previous_set={set_index}, '
                    f'evidence={return_reason}, hand_count={hand_before}->{hand_after}'
                )
                continue

            moved_to = None
            if len(newly_occupied) == 1:
                candidate_pos = newly_occupied[0]
                round_state = self._ensure_prep_goldfish_round_state()
                round_state['inspected_slots'].add(int(candidate_pos))
                probe = self._inspect_board_set_shikigami(
                    candidate_pos,
                    max_attempts=1,
                )
                if probe['opened']:
                    round_state['inspected_slot_results'][int(candidate_pos)] = probe['name']
                if probe['opened'] and probe['name'] == prev_name:
                    moved_to = candidate_pos
            if moved_to is not None:
                self._update_board_slot(
                    moved_to,
                    occupancy='occupied',
                    star=self._board_set_star(moved_to),
                    identity=prev_name,
                    kind='lineup',
                    valid=True,
                    player_deployed=True,
                    source='displaced_moved',
                    suspect_merge=False,
                    stale_reason=None,
                )
                dispositions[prev_name] = f'moved_to_set_{moved_to}'
                logger.info(
                    'Chess displaced occupant confirmed at new board slot: '
                    f'name={prev_name}, {set_index}->{moved_to}'
                )
            else:
                # 画面无法唯一确认原棋子的新去向时，精准清理其在该格的旧占用，保留同名他格有效副本。
                still_other = any(
                    s != int(set_index)
                    and slots_table[s].get('valid')
                    and slots_table[s].get('identity') == prev_name
                    for s in range(1, 13)
                )
                if not still_other:
                    deployed_names = set(getattr(self, '_board_lineup_names', set()))
                    deployed_names.discard(prev_name)
                    self._board_lineup_names = deployed_names
                    actual_positions = dict(getattr(self, '_board_actual_positions', {}))
                    if actual_positions.get(prev_name) == int(set_index):
                        actual_positions.pop(prev_name, None)
                    self._board_actual_positions = actual_positions
                dispositions[prev_name] = 'unverified_cleared_from_slot'
                logger.warning(
                    'Chess displaced occupant destination unverified; clear '
                    f'previous slot record to avoid duplicate occupancy: '
                    f'name={prev_name}, previous_set={set_index}, '
                    f'newly_occupied={newly_occupied}'
                )

        if (
            getattr(self, '_arakawa_goldfish_current_position', None)
            == set_index
            and deployed_name != 'arakawa_goldfish'
        ):
            self._clear_arakawa_goldfish_position(clear_placed=True)
            dispositions['arakawa_goldfish'] = 'cleared_from_slot'
            logger.warning(
                'Chess goldfish record cleared from slot occupied by '
                f'confirmed shikigami {deployed_name}: set={set_index}'
            )

        return dispositions

    @staticmethod
    def _compute_newly_occupied_slots(
        count_before: dict | None,
        count_after: dict | None,
        *,
        exclude_slot: int | None = None,
    ) -> list[int]:
        """对比拖前后占格集合，提取除目标格外的新增占格列表。"""
        if count_before is None or count_after is None:
            return []
        occupied_before = set(count_before['occupied_positions'])
        occupied_after = set(count_after['occupied_positions'])
        diff = occupied_after - occupied_before
        if exclude_slot is not None:
            diff.discard(int(exclude_slot))
        return sorted(diff)

    def _confirm_deploy_settled_state(
        self,
        name: str,
        set_index: int,
        *,
        hand_count_before: int | None = None,
        hand_stars_before: tuple | None = None,
    ) -> dict[str, Any]:
        """有界等待拖卡动画落地与手牌回弹稳定（至少连续 2 帧一致，避免单帧浮空误判）。"""
        needed_frames = max(1, int(getattr(self, 'DEPLOY_CONFIRM_STABLE_FRAMES', 2)))
        max_wait = float(getattr(self, 'DEPLOY_SETTLE_WAIT_TIMEOUT', 1.6))
        deadline = time.monotonic() + max_wait
        last_sig: tuple[Any, ...] | None = None
        last_frame_id = getattr(self.device, 'image_frame_id', None)
        streak = 0
        settled = False

        for step in range(8):
            if not self._is_preparation_mode() or self._is_shop_open():
                break
            hand_count = self._lineup_hand_card_match_count(name)
            hand_stars = self._lineup_hand_stars(name)
            target_state = self._board_set_state(set_index)
            target_star = self._board_set_star(set_index)
            if (
                step == 0
                and hand_count_before is not None
                and hand_count >= hand_count_before
                and target_state == 'empty'
                and hand_stars == hand_stars_before
            ):
                # 首次等待后目标格仍为空、手牌与星级均未下跌/浮空，可直接确认未消耗回弹，避免多耗一帧。
                settled = True
                break
            sig = (hand_count, hand_stars, target_state, target_star)
            if sig == last_sig:
                streak += 1
            else:
                last_sig = sig
                streak = 1
            if streak >= needed_frames:
                settled = True
                break
            if time.monotonic() >= deadline:
                break
            if callable(getattr(self, 'screenshot', None)):
                cur_frame_id = getattr(self.device, 'image_frame_id', None)
                if cur_frame_id is not None and cur_frame_id == last_frame_id and step > 0:
                    time.sleep(min(0.15, max(0.0, deadline - time.monotonic())))
                self.screenshot()
                last_frame_id = getattr(self.device, 'image_frame_id', None)
            else:
                break

        hand_count = self._lineup_hand_card_match_count(name)
        hand_stars = self._lineup_hand_stars(name)
        target_state = self._board_set_state(set_index)
        target_star = self._board_set_star(set_index)
        count_after = self._read_shikigami_count()
        hand_snapshot_after = self._snapshot_lineup_hand_cards()
        return {
            'settled': settled,
            'hand_count': hand_count,
            'hand_stars': hand_stars,
            'target_state': target_state,
            'target_star': target_star,
            'count_after': count_after,
            'hand_snapshot_after': hand_snapshot_after,
        }

    def _deploy_lineup_hand_card_direct(
        self,
        name: str,
        source: tuple[int, int],
        set_index: int,
        *,
        budget: PrepSliceBudget | None = None,
        expect_replace: bool = False,
    ) -> dict:
        """统一候选上卡直拖路径：多帧防回弹稳定、详情后用最新帧重算、区分五类结果。"""
        set_index = int(set_index)
        if not self._is_preparation_mode():
            return {
                'status': 'ambiguous',
                'position_confirmed': False,
                'reason': 'not_preparation',
                'set_index': set_index,
                'expected_name': name,
                'observed_name': None,
                'raw_texts': [],
                'clue_reason': None,
                'hand_consumed': False,
                'hand_count_before': 0,
                'hand_count_after': 0,
                'hand_stars_before': None,
                'hand_stars_after': None,
                'hand_star_upgraded': False,
                'board_star_upgraded': False,
                'board_star_before': None,
                'board_star_after': None,
                'target_state_before': None,
                'target_state_after': None,
                'newly_occupied_slots': [],
                'displaced': {},
            }
        if not self._ensure_shop_closed():
            logger.warning(
                f'Abort Chess direct deploy: shop is not closed before dragging {name}'
            )
            return {
                'status': 'ambiguous',
                'position_confirmed': False,
                'reason': 'shop_not_closed',
                'set_index': set_index,
                'expected_name': name,
                'observed_name': None,
                'raw_texts': [],
                'clue_reason': None,
                'hand_consumed': False,
                'hand_count_before': 0,
                'hand_count_after': 0,
                'hand_stars_before': None,
                'hand_stars_after': None,
                'hand_star_upgraded': False,
                'board_star_upgraded': False,
                'board_star_before': None,
                'board_star_after': None,
                'target_state_before': None,
                'target_state_after': None,
                'newly_occupied_slots': [],
                'displaced': {},
            }

        round_state = self._ensure_prep_goldfish_round_state()
        hand_snapshot_before = self._snapshot_lineup_hand_cards()
        count_before = self._read_shikigami_count()
        hand_count_before = self._lineup_hand_card_match_count(name)
        hand_stars_before = self._lineup_hand_stars(name)
        board_star_before = self._board_set_star(set_index)
        target_state_before = self._board_set_state(set_index)
        goldfish_pos_before = getattr(self, '_arakawa_goldfish_current_position', None)
        goldfish_at_target_before = (
            goldfish_pos_before is not None and int(goldfish_pos_before) == set_index
        )
        actual_positions_before = dict(getattr(self, '_board_actual_positions', {}))
        slots_table = self._board_slots_table()
        previous_occupants_set = {
            unit_name
            for unit_name in getattr(self, '_board_lineup_names', set())
            if unit_name != name
            and actual_positions_before.get(
                unit_name,
                self.shikigami_deploy_positions.get(unit_name),
            ) == set_index
        }
        slot_rec_before = slots_table[set_index]
        if (
            slot_rec_before.get('kind') == 'lineup'
            and slot_rec_before.get('identity')
            and slot_rec_before.get('identity') != name
        ):
            previous_occupants_set.add(slot_rec_before['identity'])
        previous_occupants = sorted(previous_occupants_set)
        same_unit_at_target_before = (
            (
                slot_rec_before.get('valid')
                and slot_rec_before.get('identity') == name
            )
            or (
                name in getattr(self, '_board_lineup_names', set())
                and actual_positions_before.get(
                    name,
                    self.shikigami_deploy_positions.get(name),
                ) == set_index
            )
        )
        prev_hand_counts_before = {
            unit_name: int((hand_snapshot_before.get(unit_name) or {}).get('count', self._lineup_hand_card_match_count(unit_name)) or 0)
            for unit_name in previous_occupants
        }
        target_position = self._set_position(set_index)
        logger.info(
            f'Chess direct deploy attempt: {self._shikigami_display_name(name)} '
            f'-> set {set_index}, target_state_before={target_state_before}, '
            f'source={source}, target={target_position}'
        )
        Press_and_Drag(
            self.device,
            p1=source,
            p2=target_position,
            hold_duration=(0.2, 0.3),
            point_random=(-3, -3, 3, 3),
            swipe_duration=0.5,
            name=f'CHESS_DEPLOY_{name.upper()}_SET_{set_index}',
        )
        # 对该格发送过新的上阵拖拽后，失效该格本轮旧查格缓存与格级缓存。
        round_state['inspected_slots'].discard(set_index)
        round_state['inspected_slot_results'].pop(set_index, None)
        self.close_shikigami_specifics_if_open()

        star_confirmations = 0
        confirmed_stars = None
        clue_reason = None

        def action_clue_observed():
            nonlocal star_confirmations, confirmed_stars, clue_reason
            if not self._is_preparation_mode() or self._is_shop_open():
                return True
            if self.close_shikigami_specifics_if_open():
                star_confirmations = 0
                return False
            if self._lineup_hand_card_match_count(name) < hand_count_before:
                clue_reason = 'hand_count_decreased'
                return True
            hand_stars = self._lineup_hand_stars(name)
            board_star = self._board_set_star(set_index)
            hand_upgraded = (
                hand_stars_before is not None
                and hand_stars is not None
                and len(hand_stars_before) == len(hand_stars)
                and hand_stars > hand_stars_before
            )
            board_upgraded = (
                board_star_before is not None
                and board_star is not None
                and board_star > board_star_before
            )
            if not (hand_upgraded or board_upgraded):
                star_confirmations = 0
                confirmed_stars = None
                return False
            current = (hand_stars, board_star)
            star_confirmations = star_confirmations + 1 if current == confirmed_stars else 1
            confirmed_stars = current
            clue_reason = 'hand_star_increased' if hand_upgraded else 'board_star_increased'
            return star_confirmations >= 2

        self._wait_chess_action_state(action_clue_observed)

        def _recompute_latest_post_state(settled_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
            if settled_snapshot is not None:
                hc_after = settled_snapshot['hand_count']
                hs_after = settled_snapshot['hand_stars']
                bs_after = settled_snapshot['target_star']
                ts_after = settled_snapshot['target_state']
                c_after = settled_snapshot['count_after']
                snap_after = settled_snapshot['hand_snapshot_after']
                settled_flag = settled_snapshot['settled']
            else:
                hc_after = self._lineup_hand_card_match_count(name)
                hs_after = self._lineup_hand_stars(name)
                bs_after = self._board_set_star(set_index)
                ts_after = self._board_set_state(set_index)
                c_after = self._read_shikigami_count()
                snap_after = self._snapshot_lineup_hand_cards()
                settled_flag = True

            cu_before = (hand_snapshot_before.get(name) or {}).get('copy_units')
            cu_after = (snap_after.get(name) or {}).get('copy_units')
            copy_decreased = (
                cu_before is not None and cu_after is not None and cu_after < cu_before
            )
            h_consumed = (hc_after < hand_count_before) or copy_decreased
            h_upgraded = (
                hand_stars_before is not None
                and hs_after is not None
                and len(hand_stars_before) == len(hs_after)
                and hs_after > hand_stars_before
            )
            b_upgraded = (
                board_star_before is not None
                and bs_after is not None
                and bs_after > board_star_before
            )
            newly_occ = self._compute_newly_occupied_slots(
                count_before,
                c_after,
                exclude_slot=set_index,
            )
            vac = (
                set(count_before['occupied_positions']) - set(c_after['occupied_positions'])
                if count_before is not None and c_after is not None
                else set()
            )
            vac.discard(set_index)
            return {
                'settled': settled_flag,
                'hand_count_after': hc_after,
                'hand_stars_after': hs_after,
                'board_star_after': bs_after,
                'target_state_after': ts_after,
                'count_after': c_after,
                'hand_snapshot_after': snap_after,
                'hand_consumed': h_consumed,
                'hand_star_upgraded': h_upgraded,
                'board_star_upgraded': b_upgraded,
                'newly_occupied_slots': newly_occ,
                'vacated_slots': vac,
            }

        settled_snap = self._confirm_deploy_settled_state(
            name,
            set_index,
            hand_count_before=hand_count_before,
            hand_stars_before=hand_stars_before,
        )
        latest = _recompute_latest_post_state(settled_snap)

        observed_name = None
        raw_texts: list[str] = []
        displaced: dict[str, str] = {}
        position_confirmed = False

        # 确认项 1：空位变占用、稳态手牌消耗且无冲突/升星歧义时，免点详情直接登记成功。
        fast_confirm = (
            self._is_preparation_mode()
            and not self._is_shop_open()
            and latest['settled']
            and target_state_before == 'empty'
            and latest['target_state_after'] == 'occupied'
            and latest['hand_consumed']
            and not latest['hand_star_upgraded']
            and not latest['board_star_upgraded']
            and not previous_occupants
            and not goldfish_at_target_before
            and not same_unit_at_target_before
            and not latest['vacated_slots']
        )
        if fast_confirm:
            status = 'confirmed_at_target'
            position_confirmed = True
            observed_name = name
            reason = 'empty_slot_filled_confirmed'
            logger.info(
                f'Chess deploy confirmed without specifics (empty->occupied): {name} -> '
                f'set {set_index}, hand_consumed=True ({hand_count_before}->{latest["hand_count_after"]}), '
                f'newly_occupied={latest["newly_occupied_slots"]}'
            )
        elif latest['target_state_after'] == 'empty':
            # 目标格确认仍空：若稳定确认手牌恢复（包括首帧浮空回弹后恢复），必须记 hand_consumed=False。
            if not latest['hand_consumed'] and not latest['hand_star_upgraded'] and not latest['board_star_upgraded']:
                status = 'confirmed_not_deployed'
                reason = 'target_empty_not_deployed'
            else:
                status = 'merged_position_unknown'
                reason = 'target_empty_after_hand_consumed'
            logger.warning(
                f'Chess deploy left target empty: {name} -> set {set_index}, '
                f'status={status}, reason={reason}, '
                f'hand_consumed={latest["hand_consumed"]} ({hand_count_before}->{latest["hand_count_after"]}), '
                f'newly_occupied={latest["newly_occupied_slots"]}'
            )
        else:
            if not self._is_preparation_mode():
                inspection = {
                    'opened': False,
                    'name': None,
                    'raw_texts': [],
                    'reason': 'not_preparation',
                }
            elif self._is_shop_open():
                inspection = {
                    'opened': False,
                    'name': None,
                    'raw_texts': [],
                    'reason': 'shop_open',
                }
            else:
                remaining = self._read_remaining_time()
                if budget is not None:
                    can_insp, insp_reason = budget.can_start_inspect(
                        remaining,
                        min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                        min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
                    )
                    if not can_insp:
                        inspection = {
                            'opened': False,
                            'name': None,
                            'raw_texts': [],
                            'reason': insp_reason,
                        }
                    else:
                        round_state['inspected_slots'].add(set_index)
                        budget.consume_inspect()
                        inspection = self._inspect_board_set_shikigami(
                            set_index,
                            max_attempts=1,
                        )
                        if inspection['opened']:
                            round_state['inspected_slot_results'][set_index] = inspection['name']
                        # 详情结束（无论打开成功还是超时）后重新采样最新画面重算手牌与星级！
                        latest = _recompute_latest_post_state(None)
                elif (
                    remaining is not None
                    and remaining < self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING
                ):
                    inspection = {
                        'opened': False,
                        'name': None,
                        'raw_texts': [],
                        'reason': 'insufficient_time_for_inspect',
                    }
                else:
                    round_state['inspected_slots'].add(set_index)
                    inspection = self._inspect_board_set_shikigami(
                        set_index,
                        max_attempts=1,
                    )
                    if inspection['opened']:
                        round_state['inspected_slot_results'][set_index] = inspection['name']
                    # 详情结束（无论打开成功还是超时）后重新采样最新画面重算手牌与星级！
                    latest = _recompute_latest_post_state(None)

            observed_name = inspection['name']
            raw_texts = list(inspection['raw_texts'])
            same_name_before = bool(
                same_unit_at_target_before
                or slot_rec_before.get('identity') == name
            )
            star_decreased = (
                board_star_before in (1, 2, 3)
                and latest['board_star_after'] in (1, 2, 3)
                and int(latest['board_star_after']) < int(board_star_before)
            )
            same_name_star_drop = (
                inspection['opened']
                and observed_name == name
                and star_decreased
                and (
                    same_name_before
                    or not previous_occupants
                    or latest['hand_star_upgraded']
                    or not latest['hand_consumed']
                )
            )
            replace_star_missing = (
                expect_replace
                and board_star_before in (1, 2, 3)
                and latest['board_star_after'] not in (1, 2, 3)
            )
            replace_unconfirmed = (
                expect_replace
                and not latest['board_star_upgraded']
                and not latest['hand_star_upgraded']
                and not (
                    latest['hand_consumed']
                    and latest['board_star_after'] in (1, 2, 3)
                    and int(latest['board_star_after']) > int(board_star_before or 0)
                )
            )
            if same_name_star_drop:
                status = 'ambiguous'
                position_confirmed = False
                reason = 'same_name_board_star_decreased'
                self._invalidate_board_slot(
                    set_index,
                    'same_name_board_star_decreased',
                    clear_identity=False,
                )
                if latest['board_star_after'] in (1, 2, 3):
                    self._board_slots_table()[set_index]['star'] = int(latest['board_star_after'])
                logger.warning(
                    'Chess same-name deploy resulted in board star drop; reject success and invalidate cache: '
                    f'expected={name}, set={set_index}, board_star={board_star_before}->{latest["board_star_after"]}, '
                    f'hand_consumed={latest["hand_consumed"]} ({hand_count_before}->{latest["hand_count_after"]}), '
                    f'hand_stars={hand_stars_before}->{latest["hand_stars_after"]}'
                )
                try:
                    cur_frame = getattr(self.device, 'image', None)
                    if isinstance(cur_frame, np.ndarray):
                        self._save_specifics_evidence_bundle(
                            set_index,
                            images={'chess_same_name_star_drop.png': cur_frame},
                            lines=[
                                f'百鬼棋局同名上阵星级下降异常：式神={name}，站位={set_index}',
                                f'场上星级变化：{board_star_before} -> {latest["board_star_after"]}',
                                f'手牌变化：{hand_count_before} -> {latest["hand_count_after"]}，stars={hand_stars_before} -> {latest["hand_stars_after"]}',
                            ],
                            label='same-name star drop',
                        )
                except Exception as exc:
                    logger.debug(f'Skip Chess same-name star drop evidence save: {exc!r}')
            elif inspection['opened'] and observed_name == name and expect_replace and (replace_star_missing or replace_unconfirmed):
                position_confirmed = False
                if (
                    not replace_star_missing
                    and not latest['hand_consumed']
                    and not latest['hand_star_upgraded']
                    and latest['board_star_after'] == board_star_before
                ):
                    status = 'confirmed_not_deployed'
                    reason = 'same_name_replace_not_confirmed'
                else:
                    status = 'ambiguous'
                    reason = 'same_name_replace_star_unconfirmed'
                    self._invalidate_board_slot(
                        set_index,
                        reason,
                        clear_identity=False,
                    )
                logger.warning(
                    'Chess higher-star replacement unconfirmed despite matching name: '
                    f'expected={name}, set={set_index}, status={status}, reason={reason}, '
                    f'board_star={board_star_before}->{latest["board_star_after"]}, '
                    f'hand_consumed={latest["hand_consumed"]} ({hand_count_before}->{latest["hand_count_after"]}), '
                    f'hand_stars={hand_stars_before}->{latest["hand_stars_after"]}'
                )
            elif inspection['opened'] and observed_name == name:
                status = 'confirmed_at_target'
                position_confirmed = True
                reason = (
                    'higher_star_replace_confirmed'
                    if (same_unit_at_target_before and (expect_replace or latest['board_star_upgraded']))
                    else 'target_identity_confirmed'
                )
                displaced = self._reconcile_displaced_slot_occupants(
                    set_index=set_index,
                    deployed_name=name,
                    previous_occupants=previous_occupants,
                    prev_hand_counts_before=prev_hand_counts_before,
                    count_before=count_before,
                    count_after=latest['count_after'],
                    hand_snapshot_before=hand_snapshot_before,
                    hand_snapshot_after=latest['hand_snapshot_after'],
                )
                logger.info(
                    f'Chess deploy position confirmed by single specifics: {name} -> '
                    f'set {set_index}, clue={clue_reason}, '
                    f'hand_consumed={latest["hand_consumed"]} ({hand_count_before}->{latest["hand_count_after"]}), '
                    f'hand_stars={hand_stars_before}->{latest["hand_stars_after"]}, '
                    f'board_star={board_star_before}->{latest["board_star_after"]}, '
                    f'displaced={displaced}'
                )
            else:
                if inspection['opened'] and observed_name == 'arakawa_goldfish':
                    self._record_arakawa_goldfish_position(set_index, identified=True)
                    gf_target = self._arakawa_goldfish_target_position()
                    if gf_target is not None and int(gf_target) == set_index:
                        self._mark_arakawa_goldfish_placed(set_index)

                if not inspection['opened']:
                    reason = inspection['reason']
                elif observed_name is None:
                    reason = 'name_unreadable'
                else:
                    reason = 'target_occupied_by_other'

                merge_clue = bool(
                    latest['hand_star_upgraded']
                    or latest['board_star_upgraded']
                    or (latest['hand_consumed'] and target_state_before != 'empty')
                )
                if merge_clue:
                    status = 'merged_position_unknown'
                elif (
                    (
                        reason == 'target_occupied_by_other'
                        or not latest['hand_consumed']
                    )
                    and not latest['hand_consumed']
                    and not latest['hand_star_upgraded']
                    and not latest['board_star_upgraded']
                    and latest['target_state_after'] in ('empty', 'occupied')
                ):
                    status = 'confirmed_not_deployed' if reason == 'target_occupied_by_other' else (
                        'confirmed_not_deployed' if latest['target_state_after'] == 'empty' else 'ambiguous'
                    )
                    if reason == 'specifics_not_opened' and not latest['hand_consumed'] and latest['hand_count_after'] >= hand_count_before and latest['target_state_after'] != 'unknown':
                        # 详情超时或回手后最新帧已确认手牌完整未减且非升星：按未上阵未消耗记录，不永久封锁同名候选。
                        status = 'confirmed_not_deployed'
                else:
                    status = 'ambiguous'

                if (
                    status in ('ambiguous', 'merged_position_unknown')
                    and slot_rec_before.get('valid')
                    and (not inspection['opened'] or observed_name is None)
                ):
                    self._invalidate_board_slot(
                        set_index,
                        f'post_deploy_{reason}',
                        clear_identity=False,
                        suspect_merge=bool(latest['board_star_upgraded']),
                    )

                logger.warning(
                    f'Chess deploy position unconfirmed: '
                    f'expected={name}, set={set_index}, status={status}, reason={reason}, '
                    f'observed={observed_name or "未识别"}, raw={raw_texts}, '
                    f'hand_consumed={latest["hand_consumed"]} ({hand_count_before}->{latest["hand_count_after"]}), '
                    f'hand_stars={hand_stars_before}->{latest["hand_stars_after"]}, '
                    f'board_star={board_star_before}->{latest["board_star_after"]}, '
                    f'newly_occupied={latest["newly_occupied_slots"]}'
                )

        result = {
            'status': status,
            'position_confirmed': position_confirmed,
            'reason': reason,
            'set_index': set_index,
            'expected_name': name,
            'observed_name': observed_name,
            'raw_texts': raw_texts,
            'clue_reason': clue_reason,
            'hand_consumed': latest['hand_consumed'],
            'hand_count_before': hand_count_before,
            'hand_count_after': latest['hand_count_after'],
            'hand_stars_before': hand_stars_before,
            'hand_stars_after': latest['hand_stars_after'],
            'hand_star_upgraded': latest['hand_star_upgraded'],
            'board_star_upgraded': latest['board_star_upgraded'],
            'board_star_before': board_star_before,
            'board_star_after': latest['board_star_after'],
            'target_state_before': target_state_before,
            'target_state_after': latest['target_state_after'],
            'newly_occupied_slots': latest['newly_occupied_slots'],
            'displaced': displaced,
            'hand_snapshot_before': hand_snapshot_before,
            'hand_snapshot_after': latest['hand_snapshot_after'],
        }
        self._last_arakawa_direct_deploy_result = result
        return result

    def _deploy_arakawa_hand_card_direct(
        self,
        name: str,
        source: tuple[int, int],
        set_index: int,
    ) -> dict:
        """保留旧直拖辅助接口名，实际统一复用单卡直拖逻辑。"""
        return self._deploy_lineup_hand_card_direct(name, source, set_index)

    @staticmethod
    def _classify_lineup_capacity_state(capacity: dict | None) -> str:
        """区分确认满员（含局部 unknown 下可靠 occupied >= expected）、确认未满与人口不明确。"""
        if not capacity:
            return 'unknown'
        if capacity.get('full') or capacity.get('visual_state') == 'full':
            return 'full'
        # 存在个别 unknown 格时 round_state 会回退 runtime_state_fallback(full=False)；
        # 若非 Boss 布局且已有可信 occupied 达到可读 expected_occupied（不自行猜测），仍视为已占满。
        if capacity.get('visual_reason') != 'boss_round':
            board_occupied = capacity.get('board_occupied')
            expected_occupied = capacity.get('expected_occupied')
            if (
                board_occupied is not None
                and expected_occupied is not None
                and int(expected_occupied) > 0
                and int(board_occupied) >= int(expected_occupied)
            ):
                return 'full'
        if (
            capacity.get('visual_state') == 'unknown'
            or capacity.get('source') == 'runtime_state_fallback'
        ):
            return 'unknown'
        return 'not_full'

    def _protected_recall_positions(self) -> tuple[set[int], set[int]]:
        """返回脚本已登记的棋盘站位与金鱼占用站位。"""
        goldfish_positions: set[int] = set()
        goldfish_pos = getattr(self, '_arakawa_goldfish_current_position', None)
        if goldfish_pos is not None:
            goldfish_positions.add(int(goldfish_pos))
        special_units = getattr(self, '_board_special_units', {}) or {}
        gf_unit_pos = special_units.get('arakawa_goldfish', {}).get('position')
        if gf_unit_pos is not None:
            goldfish_positions.add(int(gf_unit_pos))
        registered_positions = (
            set(getattr(self, '_player_deployed_positions', set()))
            | self._known_deployed_lineup_positions()
        )
        return goldfish_positions, registered_positions

    def _has_other_satisfied_copy(
        self,
        name: str,
        *,
        exclude_slot: int,
    ) -> dict[str, Any] | None:
        """检查该式神在除 exclude_slot 外的配置格是否已有有效确认、星级明确且非金鱼的本体。"""
        configured_slot = self.shikigami_deploy_positions.get(name)
        if configured_slot is None:
            return None
        main_slot = int(configured_slot)
        if main_slot == int(exclude_slot):
            return None
        slots_table = self._board_slots_table()
        main_rec = slots_table.get(main_slot, {})
        if (
            not main_rec.get('valid')
            or main_rec.get('occupancy') != 'occupied'
            or main_rec.get('kind') != 'lineup'
            or main_rec.get('suspect_merge')
            or main_rec.get('identity') != name
            or not self._is_slot_satisfied(main_slot, name)
        ):
            return None
        if getattr(self, '_arakawa_goldfish_current_position', None) == main_slot:
            return None
        if self._board_set_state(main_slot) != 'occupied':
            return None
        cached_star = main_rec.get('star')
        live_star = self._board_set_star(main_slot)
        if (
            cached_star not in (1, 2, 3)
            or live_star not in (1, 2, 3)
            or int(live_star) != int(cached_star)
        ):
            return None
        return {
            'slot': main_slot,
            'star': int(live_star),
            'identity': name,
        }

    def _is_recallable_duplicate_slot(self, dup_slot: int) -> dict[str, Any]:
        """判断格位是否为可回收重复阵容副本（本体在配置格有效且星级 >= 副本）。"""
        slot = int(dup_slot)
        if not self._is_preparation_mode():
            return {'recallable': False, 'reason': 'not_preparation', 'name': None}
        if self._is_shop_open():
            return {'recallable': False, 'reason': 'shop_open', 'name': None}
        goldfish_positions, _ = self._protected_recall_positions()
        if (
            slot in goldfish_positions
            or self._is_placed_goldfish_protected_slot(slot)
            or self._is_confirmed_arakawa_goldfish(slot)
        ):
            return {'recallable': False, 'reason': 'protected_goldfish', 'name': 'arakawa_goldfish'}

        dup_rec = self._board_slots_table().get(slot, {})
        dup_ident = dup_rec.get('identity')
        if (
            not dup_rec.get('valid')
            or dup_rec.get('occupancy') != 'occupied'
            or dup_rec.get('kind') != 'lineup'
            or dup_rec.get('suspect_merge')
            or not dup_ident
            or dup_ident not in self.shikigami_deploy_positions
        ):
            return {'recallable': False, 'reason': 'duplicate_slot_unconfirmed', 'name': dup_ident}

        if self._is_slot_satisfied(slot, dup_ident):
            return {'recallable': False, 'reason': 'duplicate_at_configured_slot', 'name': dup_ident}

        if self._board_set_state(slot) != 'occupied':
            return {'recallable': False, 'reason': 'duplicate_slot_not_occupied', 'name': dup_ident}

        dup_cached_star = dup_rec.get('star')
        live_dup_star = self._board_set_star(slot)
        if (
            dup_cached_star not in (1, 2, 3)
            or live_dup_star not in (1, 2, 3)
            or int(live_dup_star) != int(dup_cached_star)
        ):
            return {'recallable': False, 'reason': 'duplicate_star_unknown_or_changed', 'name': dup_ident}

        main_info = self._has_other_satisfied_copy(dup_ident, exclude_slot=slot)
        if main_info is None:
            return {'recallable': False, 'reason': 'main_copy_not_confirmed_at_configured_slot', 'name': dup_ident}

        if int(main_info['star']) < int(live_dup_star):
            return {
                'recallable': False,
                'reason': 'duplicate_higher_star_than_main',
                'name': dup_ident,
                'dup_star': int(live_dup_star),
                'main_slot': main_info['slot'],
                'main_star': main_info['star'],
            }

        return {
            'recallable': True,
            'reason': 'verified_duplicate_lineup_copy',
            'name': dup_ident,
            'dup_star': int(live_dup_star),
            'main_slot': main_info['slot'],
            'main_star': main_info['star'],
        }

    def _find_verified_duplicate_recall_slot(
        self,
        *,
        target_slot: int | None = None,
    ) -> dict[str, Any] | None:
        """查找已确认可回收的重复副本格；优先检查受阻目标格，再按系统回收序及全盘升序。"""
        ordered: list[int] = []
        if target_slot is not None and 1 <= int(target_slot) <= 12:
            ordered.append(int(target_slot))
        for pos in tuple(self.BOARD_RECALL_POSITIONS) + tuple(range(1, 13)):
            if pos not in ordered:
                ordered.append(int(pos))
        for pos in ordered:
            verdict = self._is_recallable_duplicate_slot(pos)
            if verdict['recallable']:
                return {'slot': pos, **verdict}
        return None

    def _classify_inspected_recall_occupant(
        self,
        slot_index: int,
        observed_name: str | None,
    ) -> dict:
        """核实详情识别出的站位单位：保护金鱼、唯一本体及未知身份；允许已确认低/同星重复副本让位。"""
        if observed_name is None:
            return {
                'recallable': False,
                'reason': 'identity_unknown',
                'name': None,
            }
        if observed_name == 'arakawa_goldfish':
            return {
                'recallable': False,
                'reason': 'protected_goldfish',
                'name': observed_name,
            }
        if observed_name in set(self.shikigami_deploy_positions):
            dup_verdict = self._is_recallable_duplicate_slot(slot_index)
            if dup_verdict['recallable']:
                return {
                    'recallable': True,
                    'reason': dup_verdict['reason'],
                    'name': observed_name,
                    'is_duplicate': True,
                    'main_slot': dup_verdict['main_slot'],
                }
            return {
                'recallable': False,
                'reason': 'protected_lineup_unit',
                'name': observed_name,
            }
        return {
            'recallable': True,
            'reason': 'verified_non_lineup_system_unit',
            'name': observed_name,
            'is_duplicate': False,
        }

    def _verify_arakawa_recall_candidate(
        self,
        slot_index: int,
        *,
        pre_inspection: dict | None = None,
        budget: PrepSliceBudget | None = None,
    ) -> dict:
        """回收前核实单个占格是否为可安全回收的非阵容系统棋子或已确认重复阵容副本。"""
        if not self._is_preparation_mode():
            return {
                'recallable': False,
                'reason': 'not_preparation',
                'name': None,
                'slot_state': None,
            }
        if not self._ensure_shop_closed():
            return {
                'recallable': False,
                'reason': 'shop_open',
                'name': None,
                'slot_state': None,
            }
        slot_state = self._board_set_state(slot_index)
        if slot_state != 'occupied':
            return {
                'recallable': False,
                'reason': f'slot_{slot_state}',
                'name': None,
                'slot_state': slot_state,
            }
        goldfish_positions, registered_positions = (
            self._protected_recall_positions()
        )
        if slot_index in goldfish_positions:
            return {
                'recallable': False,
                'reason': 'protected_goldfish',
                'name': 'arakawa_goldfish',
                'slot_state': slot_state,
            }
        slot_rec = self._board_slots_table().get(int(slot_index), {})
        if slot_rec.get('valid') and slot_rec.get('kind') == 'lineup':
            dup_verdict = self._is_recallable_duplicate_slot(slot_index)
            if dup_verdict['recallable']:
                return {
                    'recallable': True,
                    'reason': dup_verdict['reason'],
                    'name': dup_verdict['name'],
                    'slot_state': slot_state,
                    'is_duplicate': True,
                    'main_slot': dup_verdict['main_slot'],
                }
            return {
                'recallable': False,
                'reason': 'protected_registered',
                'name': slot_rec.get('identity'),
                'slot_state': slot_state,
            }
        if slot_rec.get('valid') and slot_rec.get('kind') == 'non_lineup' and slot_rec.get('identity'):
            verdict = self._classify_inspected_recall_occupant(
                slot_index,
                slot_rec.get('identity'),
            )
            return {**verdict, 'slot_state': slot_state}
        if slot_index in registered_positions:
            return {
                'recallable': False,
                'reason': 'protected_registered',
                'name': None,
                'slot_state': slot_state,
            }

        slot_int = int(slot_index)
        round_state = self._ensure_prep_goldfish_round_state()
        if pre_inspection is not None:
            verdict = self._classify_inspected_recall_occupant(
                slot_index,
                pre_inspection.get('name'),
            )
            return {**verdict, 'slot_state': slot_state}

        if slot_int in round_state['inspected_slots']:
            if slot_int in round_state['inspected_slot_results']:
                cached_name = round_state['inspected_slot_results'][slot_int]
                verdict = self._classify_inspected_recall_occupant(
                    slot_index,
                    cached_name,
                )
                return {**verdict, 'slot_state': slot_state}
            return {
                'recallable': False,
                'reason': 'already_inspected_this_round',
                'name': None,
                'slot_state': slot_state,
            }

        if budget is not None:
            can_insp, insp_reason = budget.can_start_inspect(
                self._safe_read_remaining_time(),
                min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
            )
            if not can_insp:
                return {
                    'recallable': False,
                    'reason': insp_reason,
                    'name': None,
                    'slot_state': slot_state,
                }
            budget.consume_inspect()
        else:
            rem_now = self._safe_read_remaining_time()
            if rem_now is not None and rem_now < int(self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING):
                return {
                    'recallable': False,
                    'reason': 'insufficient_time_for_inspect',
                    'name': None,
                    'slot_state': slot_state,
                }

        round_state['inspected_slots'].add(slot_int)
        inspection = self._inspect_board_set_shikigami(slot_index, max_attempts=1)
        if not inspection['opened']:
            round_state.setdefault('slot_inspect_cooldown', set()).add(slot_int)
            return {
                'recallable': False,
                'reason': inspection['reason'],
                'name': None,
                'slot_state': slot_state,
            }
        round_state['inspected_slot_results'][slot_int] = inspection['name']
        self._record_slot_inspection_result(slot_index, inspection)
        if inspection['name'] is None:
            round_state.setdefault('slot_inspect_cooldown', set()).add(slot_int)
        if inspection['name'] == 'arakawa_goldfish':
            self._record_arakawa_goldfish_position(slot_index, identified=True)
            gf_target = self._arakawa_goldfish_target_position()
            if gf_target is not None and int(gf_target) == slot_int:
                self._mark_arakawa_goldfish_placed(slot_index)
        verdict = self._classify_inspected_recall_occupant(
            slot_index,
            inspection['name'],
        )
        return {**verdict, 'slot_state': slot_state}

    def _find_verified_arakawa_recall_slot(
        self,
        target_set_index: int,
        *,
        target_state: str,
        pre_inspection: dict | None = None,
        budget: PrepSliceBudget | None = None,
        allow_population_relief: bool = False,
        allow_active_inspect: bool = True,
    ) -> dict:
        """全盘（1..12，含 1 号位）寻找唯一已核实可回收占位者：先已确认 non_lineup/重复副本，再有界核查至多 1 格。"""
        if not self._is_preparation_mode():
            return {
                'status': 'stop',
                'slot': None,
                'reason': 'not_preparation',
                'candidate_name': None,
                'is_duplicate': False,
            }

        if target_state == 'occupied':
            check = self._verify_arakawa_recall_candidate(
                target_set_index,
                pre_inspection=pre_inspection,
                budget=budget,
            )
            if check['reason'] == 'not_preparation' or not self._is_preparation_mode():
                return {
                    'status': 'stop',
                    'slot': None,
                    'reason': 'not_preparation',
                    'candidate_name': None,
                    'is_duplicate': False,
                }
            if not check['recallable']:
                # 目标格由需保留单位或身份不明棋子占据：只腾其他人口无法解决占用，本轮暂缓。
                return {
                    'status': 'defer',
                    'slot': None,
                    'reason': f'target_unrecallable:{check["reason"]}',
                    'candidate_name': check['name'],
                    'is_duplicate': False,
                }
            if self._hand_capacity_count() >= 10:
                return {
                    'status': 'defer',
                    'slot': None,
                    'reason': 'hand_full',
                    'candidate_name': check['name'],
                    'is_duplicate': bool(check.get('is_duplicate', False)),
                }
            return {
                'status': 'ready',
                'slot': target_set_index,
                'reason': 'target_occupied_by_recallable_duplicate_unit' if check.get('is_duplicate') else 'target_occupied_by_recallable_system_unit',
                'candidate_name': check['name'],
                'is_duplicate': bool(check.get('is_duplicate', False)),
            }

        if target_state != 'empty' and not (allow_population_relief and target_state == 'unknown'):
            return {
                'status': 'defer',
                'slot': None,
                'reason': f'target_state_{target_state}',
                'candidate_name': None,
                'is_duplicate': False,
            }

        if self._hand_capacity_count() >= 10:
            return {
                'status': 'defer',
                'slot': None,
                'reason': 'hand_full',
                'candidate_name': None,
                'is_duplicate': False,
            }

        ordered_slots = [
            s
            for s in dict.fromkeys(tuple(self.BOARD_RECALL_POSITIONS) + tuple(range(1, 13)))
            if int(s) != int(target_set_index)
        ]
        slots_table = self._board_slots_table()
        round_state = self._ensure_prep_goldfish_round_state()
        goldfish_positions, registered_positions = self._protected_recall_positions()

        # Pass 1a（0 点击）：全盘 1..12 优先寻找已确认非阵容占位单位
        for slot in ordered_slots:
            if slot in goldfish_positions or self._is_placed_goldfish_protected_slot(slot):
                continue
            if self._board_set_state(slot) != 'occupied':
                continue
            rec = slots_table[slot]
            obs_ident = None
            if rec.get('valid') and rec.get('kind') == 'non_lineup' and rec.get('identity'):
                obs_ident = rec.get('identity')
            elif slot in round_state['inspected_slot_results'] and rec.get('kind') != 'lineup':
                obs_ident = round_state['inspected_slot_results'][slot]
            if not obs_ident:
                continue
            verdict = self._classify_inspected_recall_occupant(slot, obs_ident)
            if verdict['recallable'] and not verdict.get('is_duplicate'):
                return {
                    'status': 'ready',
                    'slot': slot,
                    'reason': 'alternate_recallable_system_unit',
                    'candidate_name': verdict['name'],
                    'is_duplicate': False,
                }

        # Pass 1b（0 点击）：全盘 1..12（含 1 号位）寻找已确认可回收重复阵容副本
        dup_fallback = self._find_verified_duplicate_recall_slot(target_slot=target_set_index)
        if dup_fallback is not None and int(dup_fallback['slot']) != int(target_set_index):
            return {
                'status': 'ready',
                'slot': dup_fallback['slot'],
                'reason': 'alternate_recallable_duplicate_unit',
                'candidate_name': dup_fallback['name'],
                'is_duplicate': True,
            }

        if not allow_active_inspect:
            return {
                'status': 'defer',
                'slot': None,
                'reason': 'no_verified_recallable_unit',
                'candidate_name': None,
                'is_duplicate': False,
            }

        # Pass 2（有界核名）：从 6/12/5/11 + 1..12 找未查明占格核查；切片模式下最多主动点 1 次避免阻塞装备或长循环
        inspected_slots = round_state['inspected_slots']
        cooldown_slots = round_state.get('slot_inspect_cooldown', set())
        for slot in ordered_slots:
            if slot in goldfish_positions or self._is_placed_goldfish_protected_slot(slot):
                continue
            if self._board_set_state(slot) != 'occupied':
                continue
            rec = slots_table[slot]
            if rec.get('valid') or slot in registered_positions:
                continue
            if slot in inspected_slots or slot in cooldown_slots:
                continue
            if not self._is_preparation_mode():
                return {
                    'status': 'stop',
                    'slot': None,
                    'reason': 'not_preparation',
                    'candidate_name': None,
                    'is_duplicate': False,
                }
            check = self._verify_arakawa_recall_candidate(slot, budget=budget)
            if check['reason'] == 'not_preparation' or not self._is_preparation_mode():
                return {
                    'status': 'stop',
                    'slot': None,
                    'reason': 'not_preparation',
                    'candidate_name': None,
                    'is_duplicate': False,
                }
            if check['recallable']:
                return {
                    'status': 'ready',
                    'slot': slot,
                    'reason': 'alternate_recallable_duplicate_unit' if check.get('is_duplicate') else 'alternate_recallable_system_unit',
                    'candidate_name': check['name'],
                    'is_duplicate': bool(check.get('is_duplicate', False)),
                }
            logger.debug(
                'Skip Chess Arakawa recall candidate: '
                f'slot={slot}, reason={check["reason"]}, name={check["name"]}'
            )
            if check['reason'] in (
                'inspect_budget_exhausted',
                'slice_wall_exhausted',
                'remaining_time_unavailable',
                'insufficient_remaining_for_inspect',
                'insufficient_time_for_inspect',
            ):
                return {
                    'status': 'defer',
                    'slot': None,
                    'reason': check['reason'],
                    'candidate_name': None,
                    'is_duplicate': False,
                }
            if budget is not None:
                # 切片预算下每切片至多消耗 1 次主动详情查格，不连续遍历全盘拖慢备战。
                return {
                    'status': 'defer',
                    'slot': None,
                    'reason': f'slice_inspect_cap_after_slot_{slot}:{check["reason"]}',
                    'candidate_name': check['name'],
                    'is_duplicate': False,
                }

        return {
            'status': 'defer',
            'slot': None,
            'reason': 'no_recallable_system_card',
            'candidate_name': None,
            'is_duplicate': False,
        }

    def _execute_verified_blocker_recall_and_rescan(
        self,
        name: str,
        set_index: int,
        recall_plan: dict[str, Any],
        *,
        budget: PrepSliceBudget | None,
        slots_table: dict[int, dict[str, Any]],
        todo_reason_prefix: str = 'population_recall',
    ) -> dict[str, Any]:
        """执行单次占位回收、确认腾格、重截重扫候选手牌新坐标（余时不足存待办且不复用旧坐标）。"""
        if self._hand_capacity_count() >= 10:
            return {'status': 'defer', 'reason': 'hand_full'}

        is_dup = bool(recall_plan.get('is_duplicate', False))
        min_rem = int(
            getattr(
                self,
                'DUPLICATE_RECALL_MIN_REMAINING' if is_dup else 'GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING',
                getattr(self, 'GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING', 6),
            )
        )
        rem_now = self._safe_read_remaining_time()
        can_act = (
            (rem_now is None or rem_now >= min_rem)
            and (
                budget is None
                or (
                    not budget.wall_exhausted()
                    and budget.can_start_action(rem_now, min_remaining=min_rem)[0]
                )
            )
        )
        recall_slot = int(recall_plan['slot'])
        if not can_act:
            self._record_await_deploy_todo(
                name,
                set_index,
                reason=f'insufficient_time_for_{todo_reason_prefix}',
                recall_slot=recall_slot,
            )
            logger.info(
                f'Defer Chess blocked recall for {name} -> set {set_index}: '
                f'recall_slot={recall_slot}, remaining={rem_now}, required>={min_rem}'
            )
            return {'status': 'defer', 'reason': 'insufficient_time_for_recall'}

        recalled = self._recall_one_system_board_card(
            preferred_set_index=recall_slot,
            candidate_positions=(recall_slot,),
            raise_on_failure=False,
            allow_verified_duplicate=is_dup,
        )
        if not self._is_preparation_mode() or self._is_shop_open():
            return {'status': 'stop', 'reason': 'not_preparation_or_shop_open'}
        if recalled != recall_slot:
            # 回收失败立即停止本次恢复，不接着回收第二只。
            self._chess_deploy_needs_refresh = True
            return {'status': 'defer', 'reason': 'recall_unconfirmed'}
        if budget is not None:
            budget.actions_done += 1

        self.screenshot()
        if not self._is_preparation_mode() or self._is_shop_open():
            return {'status': 'stop', 'reason': 'not_preparation_after_recall'}

        min_after_rem = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
        rem_after = self._safe_read_remaining_time()
        can_follow = (
            (rem_after is None or rem_after >= min_after_rem)
            and (
                budget is None
                or (
                    not budget.wall_exhausted()
                    and budget.can_start_action(rem_after, min_remaining=min_after_rem)[0]
                )
            )
        )
        if not can_follow:
            follow_reason = (
                'insufficient_time_after_duplicate_recall'
                if is_dup
                else f'insufficient_time_after_{todo_reason_prefix}'
            )
            self._record_await_deploy_todo(
                name,
                set_index,
                reason=follow_reason,
                recall_slot=recall_slot,
            )
            self._chess_deploy_needs_refresh = True
            logger.info(
                f'Record todo after blocker recall at set {recall_slot}: '
                f'insufficient remaining time for {name} -> set {set_index} '
                f'(remaining={rem_after}, required>={min_after_rem})'
            )
            return {'status': 'defer', 'reason': follow_reason}

        refreshed_candidate = self._find_best_shikigami_hand_card(
            excluded_names=(set(self.shikigami_deploy_positions) - {name}),
        )
        if refreshed_candidate is None or refreshed_candidate['name'] != name:
            self._record_await_deploy_todo(
                name,
                set_index,
                reason=f'candidate_missing_after_{todo_reason_prefix}',
                recall_slot=recall_slot,
            )
            self._chess_deploy_needs_refresh = True
            return {'status': 'defer', 'reason': 'candidate_missing_after_recall'}

        return {
            'status': 'ready',
            'candidate': refreshed_candidate,
            'rec_at_target': slots_table[set_index],
            'target_state_now': self._board_set_state(set_index),
            'recall_slot': recall_slot,
        }

    def _recall_and_relocate_arakawa_card(
        self,
        name: str,
        set_index: int,
        recall_slot: int,
        *,
        capacity_source: str,
        recall_reason: str,
        identified_occupant: str | None,
        allow_verified_duplicate: bool = False,
    ) -> dict:
        """只回收已核实的单个站位，重截确认腾空并重定位候选手牌后再拖。"""
        if not self._is_preparation_mode() or not self._ensure_shop_closed():
            return {
                'status': 'stop',
                'candidate': None,
                'reason': 'not_preparation_or_shop_open',
                'needs_refresh': False,
            }
        if self._hand_capacity_count() >= 10:
            return {
                'status': 'defer',
                'candidate': None,
                'reason': 'hand_full',
                'needs_refresh': False,
            }

        logger.info(
            'Chess Arakawa verified recall before deploy: '
            f'card={self._shikigami_display_name(name)}({name}), '
            f'target_set={set_index}, recall_set={recall_slot}, '
            f'occupant={identified_occupant}, capacity_source={capacity_source}, '
            f'reason={recall_reason}'
        )
        self._last_system_recall_outcome = None
        recalled_set = self._recall_one_system_board_card(
            preferred_set_index=recall_slot,
            candidate_positions=(recall_slot,),
            raise_on_failure=False,
            allow_verified_duplicate=allow_verified_duplicate,
        )
        outcome = getattr(self, '_last_system_recall_outcome', None)
        if outcome == 'unknown_after_drag':
            return {
                'status': 'defer',
                'candidate': None,
                'reason': 'recall_result_unknown_after_drag',
                'needs_refresh': True,
            }
        if recalled_set != recall_slot:
            status = (
                'stop'
                if outcome == 'not_preparation' or not self._is_preparation_mode()
                else 'defer'
            )
            return {
                'status': status,
                'candidate': None,
                'reason': outcome or 'recall_unconfirmed',
                'needs_refresh': outcome not in ('not_found', 'hand_full', 'not_preparation'),
            }

        # 回收后重新截图确认格子确实腾出，并重扫候选区定位同一个式神，禁用回收前坐标。
        round_state = self._ensure_prep_goldfish_round_state()
        round_state['inspected_slots'].discard(int(recall_slot))
        round_state['inspected_slot_results'].pop(int(recall_slot), None)
        self.screenshot()
        if not self._is_preparation_mode() or not self._ensure_shop_closed():
            return {
                'status': 'stop',
                'candidate': None,
                'reason': 'not_preparation_after_recall',
                'needs_refresh': True,
            }
        post_recall_state = self._board_set_state(recall_slot)
        if post_recall_state != 'empty':
            return {
                'status': 'defer',
                'candidate': None,
                'reason': f'recalled_slot_not_empty:{post_recall_state}',
                'needs_refresh': True,
            }

        refreshed_candidate = self._find_best_shikigami_hand_card(
            excluded_names=(set(self.shikigami_deploy_positions) - {name}),
        )
        if refreshed_candidate is None or refreshed_candidate['name'] != name:
            return {
                'status': 'defer',
                'candidate': None,
                'reason': 'candidate_missing_after_recall',
                'needs_refresh': True,
            }
        logger.info(
            f'Recall Chess system card at set {recall_slot} '
            f'(occupant={identified_occupant}), then deploy Arakawa '
            f'{self._shikigami_display_name(name)} to set {set_index}, '
            f'refreshed_position={refreshed_candidate["position"]}, '
            f'capacity_source={capacity_source}, reason={recall_reason}'
        )
        return {
            'status': 'ready',
            'candidate': refreshed_candidate,
            'reason': 'recalled_and_relocated',
            'needs_refresh': False,
        }

    def _evaluate_deploy_recovery_evidence(
        self,
        name: str,
        set_index: int,
        direct_result: dict,
    ) -> dict:
        """首次直拖未确认时，核查是否具备“未消耗、无升星且有清晰阻挡/未落位证据”的恢复依据。"""
        if direct_result.get('reason') in ('shop_not_closed', 'shop_open', 'not_preparation', 'anchor_missing'):
            return {
                'allow_recall': False,
                'recovery_kind': None,
                'reason': direct_result.get('reason'),
                'target_state': None,
                'pre_inspection': None,
            }

        self.close_shikigami_specifics_if_open()
        self.screenshot()
        if (
            not self._is_preparation_mode()
            or self._is_shop_open()
            or not self._ensure_shop_closed()
        ):
            return {
                'allow_recall': False,
                'recovery_kind': None,
                'reason': 'not_preparation_or_shop_open',
                'target_state': None,
                'pre_inspection': None,
            }

        hand_count_before = int(direct_result.get('hand_count_before') or 0)
        hand_count_now = self._lineup_hand_card_match_count(name)
        if (
            hand_count_before <= 0
            or direct_result.get('hand_consumed')
            or hand_count_now < hand_count_before
        ):
            return {
                'allow_recall': False,
                'recovery_kind': None,
                'reason': 'hand_consumed_or_count_dropped',
                'target_state': None,
                'pre_inspection': None,
            }

        hand_stars_before = direct_result.get('hand_stars_before')
        hand_stars_after = direct_result.get('hand_stars_after')
        hand_stars_now = self._lineup_hand_stars(name)
        if (
            direct_result.get('hand_star_upgraded')
            or direct_result.get('board_star_upgraded')
            or hand_stars_before is None
            or hand_stars_after is None
            or hand_stars_now is None
            or hand_stars_after != hand_stars_before
            or hand_stars_now != hand_stars_before
        ):
            return {
                'allow_recall': False,
                'recovery_kind': None,
                'reason': 'star_upgrade_or_ambiguous',
                'target_state': None,
                'pre_inspection': None,
            }

        still_in_hand = self._find_best_shikigami_hand_card(
            excluded_names=(set(self.shikigami_deploy_positions) - {name}),
        )
        if still_in_hand is None or still_in_hand['name'] != name:
            return {
                'allow_recall': False,
                'recovery_kind': None,
                'reason': 'candidate_not_found_after_drag',
                'target_state': None,
                'pre_inspection': None,
            }

        reason = direct_result.get('reason')
        target_state_now = self._board_set_state(set_index)
        board_star_before = direct_result.get('board_star_before')
        board_star_after = direct_result.get('board_star_after')
        board_star_now = self._board_set_star(set_index)

        if reason in ('target_empty_not_deployed', 'specifics_not_opened'):
            # specifics_not_opened 单独出现不算失败证据，必须同时在新画面确认目标格仍为空着且无任何星级信号。
            if target_state_now != 'empty':
                return {
                    'allow_recall': False,
                    'recovery_kind': None,
                    'reason': f'specifics_not_opened_without_empty_target:{target_state_now}',
                    'target_state': target_state_now,
                    'pre_inspection': None,
                }
            if (
                board_star_before is not None
                or board_star_after is not None
                or board_star_now is not None
            ):
                return {
                    'allow_recall': False,
                    'recovery_kind': None,
                    'reason': 'board_star_present_on_empty_target',
                    'target_state': target_state_now,
                    'pre_inspection': None,
                }
            return {
                'allow_recall': True,
                'recovery_kind': 'recall_system',
                'reason': 'target_empty_and_hand_card_unconsumed',
                'target_state': 'empty',
                'pre_inspection': None,
            }

        if reason == 'target_occupied_by_other':
            observed_name = direct_result.get('observed_name')
            if (
                target_state_now != 'occupied'
                or board_star_before is None
                or board_star_after != board_star_before
                or board_star_now != board_star_before
            ):
                return {
                    'allow_recall': False,
                    'recovery_kind': None,
                    'reason': 'target_board_star_ambiguous_or_changed',
                    'target_state': target_state_now,
                    'pre_inspection': None,
                }
            if observed_name == 'arakawa_goldfish':
                if self._is_placed_goldfish_protected_slot(set_index):
                    return {
                        'allow_recall': False,
                        'recovery_kind': None,
                        'reason': 'protected_placed_goldfish',
                        'target_state': target_state_now,
                        'pre_inspection': {'name': observed_name},
                    }
                return {
                    'allow_recall': True,
                    'recovery_kind': 'move_goldfish',
                    'reason': 'target_occupied_by_misplaced_goldfish',
                    'target_state': 'occupied',
                    'pre_inspection': {'name': observed_name},
                }

            verdict = self._classify_inspected_recall_occupant(
                set_index,
                observed_name,
            )
            if not verdict['recallable']:
                return {
                    'allow_recall': False,
                    'recovery_kind': None,
                    'reason': f'target_protected:{verdict["reason"]}',
                    'target_state': target_state_now,
                    'pre_inspection': None,
                }
            return {
                'allow_recall': True,
                'recovery_kind': 'recall_system',
                'reason': 'target_occupied_by_recallable_system_unit',
                'target_state': 'occupied',
                'pre_inspection': {'name': observed_name},
            }

        return {
            'allow_recall': False,
            'recovery_kind': None,
            'reason': f'ambiguous_direct_result:{reason}',
            'target_state': target_state_now,
            'pre_inspection': None,
        }

    def _evaluate_unknown_capacity_arakawa_retry(
        self,
        name: str,
        set_index: int,
        direct_result: dict,
    ) -> dict:
        """保留兼容辅助名，统一委托至通用恢复证据核查。"""
        return self._evaluate_deploy_recovery_evidence(name, set_index, direct_result)

    def _recover_after_confirmed_not_deployed(
        self,
        name: str,
        set_index: int,
        direct_result: dict,
        *,
        capacity: dict | None,
        round_state: dict,
        budget: PrepSliceBudget | None = None,
    ) -> dict:
        """在确认未上阵且余时充足后，至多执行 1 次安全恢复（搬离错位金鱼或核实回收系统卡）。"""
        set_index = int(set_index)
        round_state['deploy_recovery_attempted_names'].add(name)
        retry_eval = self._evaluate_deploy_recovery_evidence(name, set_index, direct_result)
        if not self._is_preparation_mode() or self._is_shop_open():
            return {'status': 'stop', 'candidate': None, 'reason': 'not_preparation_or_shop_open'}
        if not retry_eval['allow_recall']:
            logger.info(
                'Skip Chess deploy recovery after unconfirmed drag: '
                f'card={name}, set={set_index}, reason={retry_eval["reason"]}'
            )
            return {'status': 'defer', 'candidate': None, 'reason': retry_eval['reason']}

        recovery_kind = retry_eval['recovery_kind']
        if recovery_kind == 'move_goldfish':
            bond_status = self._check_arakawa_bond_qualified()
            if not bond_status['qualified']:
                self._set_goldfish_relocation_pending(True, source='blocking')
                logger.info(
                    'Defer Chess recovery goldfish move: '
                    f'card={name}, set={set_index}, reason={bond_status["reason"]}'
                )
                return {'status': 'defer', 'candidate': None, 'reason': bond_status['reason']}
            remaining = self._read_remaining_time()
            if (
                remaining is None
                or remaining < self.GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING
            ):
                self._set_goldfish_relocation_pending(True, source='blocking')
                logger.info(
                    'Defer Chess recovery goldfish move by remaining time: '
                    f'card={name}, set={set_index}, remaining_time={remaining}, '
                    f'required>={self.GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING}'
                )
                return {'status': 'defer', 'candidate': None, 'reason': 'insufficient_time_goldfish'}
            usable, usable_reason, gf_target = self._check_goldfish_target_slot_usable(set_index)
            if not usable:
                self._set_goldfish_relocation_pending(
                    gf_target is not None and int(gf_target) != set_index,
                    source='blocking',
                )
                logger.info(
                    'Defer Chess recovery goldfish move: '
                    f'card={name}, set={set_index}, goldfish_target={gf_target}, '
                    f'reason={usable_reason}'
                )
                return {'status': 'defer', 'candidate': None, 'reason': usable_reason}
            moved = self._move_arakawa_goldfish(set_index, verify_vacated_source=True)
            if not self._is_preparation_mode() or self._is_shop_open():
                return {'status': 'stop', 'candidate': None, 'reason': 'not_preparation_or_shop_open'}
            if not moved:
                return {'status': 'defer', 'candidate': None, 'reason': 'goldfish_move_unconfirmed'}
            round_state['inspected_slots'].discard(set_index)
            round_state['inspected_slot_results'].pop(set_index, None)
            if gf_target is not None:
                round_state['inspected_slots'].discard(int(gf_target))
                round_state['inspected_slot_results'].pop(int(gf_target), None)
            self.screenshot()
            relocated = self._find_best_shikigami_hand_card(
                excluded_names=(set(self.shikigami_deploy_positions) - {name}),
            )
            if relocated is None or relocated['name'] != name:
                self._chess_deploy_needs_refresh = True
                return {'status': 'defer', 'candidate': None, 'reason': 'candidate_missing_after_goldfish_move'}
            logger.info(
                'Cleared blocking goldfish after direct deploy probe; rescan and retry once: '
                f'card={name}, freed_set={set_index}, goldfish_target={gf_target}, '
                f'refreshed_position={relocated["position"]}'
            )
            return {'status': 'ready', 'candidate': relocated, 'reason': 'goldfish_moved_and_relocated'}

        # 系统卡回收涉及人口上限判断，等级 OCR 失败（capacity=None）时不执行回收，等待人口信息恢复。
        if capacity is None:
            logger.info(
                'Defer Chess deploy system recall: lineup capacity unavailable '
                f'(card={name}, set={set_index})'
            )
            return {'status': 'defer', 'candidate': None, 'reason': 'capacity_unavailable'}

        if (
            retry_eval['target_state'] == 'empty'
            and self._classify_lineup_capacity_state(capacity) == 'not_full'
        ):
            logger.info(
                'Skip Chess alternate system recall: board capacity confirmed not full '
                f'(card={name}, set={set_index}, capacity={capacity})'
            )
            return {'status': 'defer', 'candidate': None, 'reason': 'capacity_not_full_no_recall'}

        remaining = self._read_remaining_time()
        if (
            remaining is not None
            and remaining < self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING
        ):
            logger.info(
                'Defer Chess deploy system recall by remaining time: '
                f'card={name}, set={set_index}, remaining_time={remaining}, '
                f'required>={self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING}'
            )
            return {'status': 'defer', 'candidate': None, 'reason': 'insufficient_time_for_recall'}

        if self._hand_capacity_count() >= 10:
            return {'status': 'defer', 'candidate': None, 'reason': 'hand_full'}

        capacity_source = capacity.get('source', 'unknown')
        recall_plan = self._find_verified_arakawa_recall_slot(
            set_index,
            target_state=retry_eval['target_state'],
            pre_inspection=retry_eval['pre_inspection'],
            budget=budget,
        )
        if recall_plan['status'] == 'stop':
            return {'status': 'stop', 'candidate': None, 'reason': recall_plan['reason']}
        if recall_plan['status'] != 'ready':
            logger.info(
                'Skip Chess system recall after confirmed-not-deployed direct drag: '
                f'card={name}, set={set_index}, reason={recall_plan["reason"]}, '
                f'capacity_source={capacity_source}'
            )
            return {'status': 'defer', 'candidate': None, 'reason': recall_plan['reason']}

        prep_result = self._recall_and_relocate_arakawa_card(
            name,
            set_index,
            recall_plan['slot'],
            capacity_source=capacity_source,
            recall_reason=f'post_direct_recovery:{direct_result["reason"]}',
            identified_occupant=recall_plan['candidate_name'],
            allow_verified_duplicate=bool(recall_plan.get('is_duplicate', False)),
        )
        if prep_result['needs_refresh']:
            self._chess_deploy_needs_refresh = True
        if prep_result['status'] != 'ready':
            logger.warning(
                'Defer Chess deploy recovery without second drag: '
                f'card={name}, set={set_index}, recall_set={recall_plan["slot"]}, '
                f'reason={prep_result["reason"]}'
            )
            return {
                'status': 'stop' if prep_result['status'] == 'stop' else 'defer',
                'candidate': None,
                'reason': prep_result['reason'],
            }
        return {'status': 'ready', 'candidate': prep_result['candidate'], 'reason': 'recalled_and_relocated'}

    @staticmethod
    def _build_pending_arakawa_deploy(
        name: str,
        set_index: int,
        direct_result: dict,
        *,
        status: str = 'unverified',
        recovery_attempted: bool = False,
        last_attempt_round: int | None = None,
    ) -> dict:
        return {
            'name': name,
            'set_index': int(set_index),
            'status': status,
            'reason': direct_result.get('reason'),
            'observed_name': direct_result.get('observed_name'),
            'hand_consumed': bool(direct_result.get('hand_consumed', False)),
            'hand_count_before': int(direct_result.get('hand_count_before', 0) or 0),
            'hand_count_after': int(direct_result.get('hand_count_after', 0) or 0),
            'hand_stars_before': direct_result.get('hand_stars_before'),
            'hand_stars_after': direct_result.get('hand_stars_after'),
            'hand_star_upgraded': bool(direct_result.get('hand_star_upgraded', False)),
            'board_star_upgraded': bool(direct_result.get('board_star_upgraded', False)),
            'board_star_before': direct_result.get('board_star_before'),
            'board_star_after': direct_result.get('board_star_after'),
            'target_state_before': direct_result.get('target_state_before'),
            'target_state_after': direct_result.get('target_state_after'),
            'newly_occupied_slots': list(direct_result.get('newly_occupied_slots') or ()),
            'last_attempt_round': last_attempt_round,
            'recovery_attempted': bool(recovery_attempted),
        }

    def _lineup_hand_card_match_count(self, name: str) -> int:
        """Count identities from this screenshot's shared Frame scan."""
        return sum(card['name'] == name for card in self._frame_card_scan('card'))

    def _lineup_hand_stars(self, name: str) -> tuple | None:
        cards = [card for card in self._frame_card_scan('card') if card['name'] == name]
        if not cards or any(card.get('star') not in (1, 2, 3) for card in cards):
            return None
        return tuple(sorted(card['star'] for card in cards))

    def _board_set_star(self, set_index: int) -> int | None:
        """从普通或首领棋盘 Frame 读取星级；歧义结果不参与确认。"""
        index = int(set_index)
        if not 1 <= index <= 12:
            raise ValueError(f'Chess board set position is not configured: {set_index}')
        slots = self._board_frame_scan()
        return slots[index - 1]['star'] if slots else None

    def _find_best_shikigami_hand_card(
        self,
        excluded_names: set[str] | None = None,
    ) -> dict | None:
        """让阵容头像模板直接扫描整个手牌区，返回最左侧命中卡。"""
        excluded_names = excluded_names or set()
        frame_candidates = []
        for frame_index in range(1, self.HAND_DEPLOY_CONFIRM_FRAMES + 1):
            if frame_index > 1:
                self.screenshot()
            frame_candidates.append(
                self._scan_lineup_hand_card_candidates_once(excluded_names)
            )

        merged = {}
        for candidates in frame_candidates:
            for candidate in candidates:
                key = (
                    candidate['name'],
                    round(candidate['position'][0] / 12),
                )
                item = merged.setdefault(key, {
                    **candidate,
                    'scores': [],
                    'frames': 0,
                })
                item['scores'].append(candidate['score'])
                item['frames'] += 1

        candidates = []
        for item in merged.values():
            if item['frames'] < self.HAND_DEPLOY_CONFIRM_FRAMES:
                logger.debug(
                    'Skip Chess lineup hand card candidate: '
                    f'name={item["name"]}, frames={item["frames"]}/'
                    f'{self.HAND_DEPLOY_CONFIRM_FRAMES}'
                )
                continue
            avg_score = sum(item['scores']) / len(item['scores'])
            item['score'] = avg_score
            if avg_score < self.HAND_DEPLOY_TEMPLATE_THRESHOLD:
                logger.debug(
                    'Skip Chess lineup hand card candidate below threshold: '
                    f'name={item["name"]}, avg_score={avg_score:.3f}, '
                    f'threshold={self.HAND_DEPLOY_TEMPLATE_THRESHOLD}'
                )
                continue
            candidates.append(item)
            logger.debug(
                'Chess lineup hand card candidate confirmed: '
                f'name={item["name"]}, '
                f'avg_score={avg_score:.3f}, '
                f'position={item["position"]}'
            )

        if not candidates:
            logger.debug('No deployable Chess lineup hand card detected')
            return None

        # 同名多张时先保留最左侧。不同式神先按阵容配置的上阵权重
        # 排序（数值越低越优先），同权重再保持原有的从左到右顺序。
        return self._pick_weighted_deploy_candidate(candidates)

    def _pick_weighted_deploy_candidate(
        self,
        candidates: list[dict],
    ) -> dict | None:
        """同式神优先高星（未知星排后、同星最左），不同式神按阵容 deploy_weight 及左到右选卡。"""
        if not candidates:
            return None
        selected_by_name = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (
                -(int(item['star']) if item.get('star') in (1, 2, 3) else 0),
                item['position'][0],
                -item['score'],
            ),
        ):
            selected_by_name.setdefault(candidate['name'], candidate)
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        selected = min(
            selected_by_name.values(),
            key=lambda item: (
                int(
                    strategy_shikigami[item['name']].get(
                        'deploy_weight', 1
                    )
                ),
                item['position'][0],
            ),
        )
        selected['deploy_weight'] = int(
            strategy_shikigami[selected['name']].get('deploy_weight', 1)
        )
        return selected

    @staticmethod
    def _runtime_exclusion_reasons_for_card(
        name: str,
        runtime_snapshot: dict | None,
    ) -> tuple[bool, list[str]]:
        """按 deploy_shikigami_from_hand 的真实集合语义解析某式神的运行期排除原因。"""
        if not isinstance(runtime_snapshot, dict) or not runtime_snapshot:
            return False, []
        deployed_names = set(
            runtime_snapshot.get('board_lineup_names')
            or runtime_snapshot.get('deployed_names')
            or ()
        )
        raw_pending = runtime_snapshot.get('pending_deploys')
        if isinstance(raw_pending, dict):
            pending_blocked = set(raw_pending.keys())
        elif isinstance(raw_pending, (list, tuple, set)):
            pending_blocked = set(raw_pending)
        else:
            pending_blocked = set()
        direct_done = set(runtime_snapshot.get('deploy_direct_attempted_names') or ())
        raw_queue = runtime_snapshot.get('deploy_recovery_queue')
        recovery_queue_names = set(raw_queue.keys()) if isinstance(raw_queue, dict) else set(raw_queue or ())
        recovery_done = set(runtime_snapshot.get('deploy_recovery_attempted_names') or ())
        round_deferred = set(runtime_snapshot.get('deploy_deferred_names') or ())
        direct_only = bool(runtime_snapshot.get('direct_only', False))

        reasons = []
        if name in deployed_names:
            reasons.append('已在场（board_lineup_names）')
        if name in pending_blocked:
            pending_entry = raw_pending.get(name, {}) if isinstance(raw_pending, dict) else {}
            detail = pending_entry.get('reason') if isinstance(pending_entry, dict) else None
            reasons.append(f'待核实阻塞（pending_deploys: {detail or "pending"}）')
        if name in round_deferred:
            reasons.append('本轮已暂缓（deploy_deferred_names）')
        if direct_only:
            if name in direct_done:
                reasons.append('本轮 direct_only 已直拖尝试（deploy_direct_attempted_names）')
        else:
            if name in recovery_done:
                reasons.append('本轮已做过空位/清格恢复（deploy_recovery_attempted_names）')
            if name in (direct_done - recovery_queue_names):
                reasons.append('本轮已直拖尝试且未入恢复队列')
        return True, reasons

    def evaluate_hand_card_deploy_candidates(
        self,
        scanned_cards: list[dict],
        *,
        deploy_threshold: float | None = None,
        runtime_snapshot: dict | None = None,
    ) -> dict:
        """按手牌上阵筛选规则补充每张识别卡的阵容归属、权重、目标格、阈值与运行时排除判断。"""
        strategy = self.get_lineup_strategy()
        strategy_shikigami = strategy['shikigami']
        eff_deploy_threshold = float(
            self.HAND_DEPLOY_TEMPLATE_THRESHOLD
            if deploy_threshold is None
            else deploy_threshold
        )
        confirm_frames = int(self.HAND_DEPLOY_CONFIRM_FRAMES)
        has_snapshot = isinstance(runtime_snapshot, dict) and bool(runtime_snapshot)
        capacity = runtime_snapshot.get('capacity') if has_snapshot else None
        occupied_slots = set(runtime_snapshot.get('board_occupied_slots') or ()) if has_snapshot else None
        goldfish_slot = runtime_snapshot.get('goldfish_placed_slot') if has_snapshot else None

        eligible_pool = []
        evaluated_cards = []
        for card in scanned_cards:
            name = card.get('name')
            in_lineup = bool(name and name in strategy_shikigami)
            unit_cfg = strategy_shikigami.get(name, {}) if in_lineup else {}
            deploy_weight = int(unit_cfg.get('deploy_weight', 1)) if in_lineup else None
            target_slot = int(unit_cfg['position']) if in_lineup else None
            score = float(card.get('score', 0.0) or 0.0)
            meets_deploy_threshold = bool(name and in_lineup and score >= eff_deploy_threshold)

            if not name:
                runtime_known = False
                exclusion_status = '式神身份未识别（低于头像阈值或羁绊歧义）'
                excluded = True
                exclusion_reasons = ['未识别身份']
            elif not in_lineup:
                runtime_known = has_snapshot
                exclusion_status = '不在当前选定配置阵容中'
                excluded = True
                exclusion_reasons = [f'非当前阵容({strategy["display_name"]})式神']
            elif not has_snapshot:
                runtime_known = False
                exclusion_status = '运行时排除状态未知'
                excluded = None
                exclusion_reasons = []
            else:
                runtime_known, exclusion_reasons = self._runtime_exclusion_reasons_for_card(
                    name, runtime_snapshot,
                )
                excluded = bool(exclusion_reasons)
                exclusion_status = (
                    '；'.join(exclusion_reasons)
                    if exclusion_reasons
                    else '未被运行时状态排除'
                )

            direct_deploy_ready = None
            if has_snapshot and in_lineup and target_slot is not None:
                full_flag = bool(capacity.get('full')) if isinstance(capacity, dict) else False
                protected_goldfish = (goldfish_slot is not None and int(goldfish_slot) == int(target_slot))
                slot_empty = (target_slot not in occupied_slots) if occupied_slots is not None else None
                if full_flag:
                    direct_deploy_ready = False
                elif protected_goldfish:
                    direct_deploy_ready = False
                elif slot_empty is not None:
                    direct_deploy_ready = slot_empty

            deploy_eligible_static = bool(in_lineup and meets_deploy_threshold)
            deploy_eligible_with_state = (
                bool(deploy_eligible_static and not excluded)
                if has_snapshot
                else deploy_eligible_static
            )
            item = {
                **card,
                'in_lineup': in_lineup,
                'deploy_weight': deploy_weight,
                'target_slot': target_slot,
                'deploy_threshold': eff_deploy_threshold,
                'confirm_frames': confirm_frames,
                'meets_deploy_threshold': meets_deploy_threshold,
                'deploy_eligible_static': deploy_eligible_static,
                'runtime_state_known': runtime_known,
                'runtime_excluded': excluded,
                'runtime_exclusion_status': exclusion_status,
                'runtime_exclusion_reasons': exclusion_reasons,
                'direct_deploy_ready': direct_deploy_ready,
            }
            evaluated_cards.append(item)
            if deploy_eligible_with_state:
                eligible_pool.append(dict(item))

        selected = self._pick_weighted_deploy_candidate(eligible_pool)
        selected_position = tuple(selected['position']) if selected else None
        for item in evaluated_cards:
            item['would_be_selected_next'] = bool(
                selected is not None
                and item.get('name') == selected.get('name')
                and tuple(item.get('position') or ()) == selected_position
            )

        return {
            'lineup_key': strategy['key'],
            'lineup_display_name': strategy['display_name'],
            'deploy_threshold': eff_deploy_threshold,
            'confirm_frames': confirm_frames,
            'runtime_state_known': has_snapshot,
            'runtime_exclusion_status': (
                '已载入运行时状态快照' if has_snapshot else '运行时排除状态未知'
            ),
            'selected_candidate': (
                {
                    'index': next(
                        (i['index'] for i in evaluated_cards if i['would_be_selected_next']),
                        None,
                    ),
                    'name': selected['name'],
                    'cn_name': strategy_shikigami[selected['name']].get('display_name', selected['name']),
                    'deploy_weight': selected['deploy_weight'],
                    'target_slot': int(strategy_shikigami[selected['name']]['position']),
                    'score': round(float(selected['score']), 4),
                    'position': list(selected['position']),
                }
                if selected is not None
                else None
            ),
            'cards': evaluated_cards,
        }

    def _scan_lineup_hand_card_candidates_once(
        self,
        excluded_names: set[str],
    ) -> list[dict]:
        """Return recognized Frame cards allowed by the active lineup."""
        allowed = self.get_lineup_strategy()['shikigami']
        return [dict(card) for card in self._frame_card_scan('card')
                if card['name'] in allowed and card['name'] not in excluded_names]

    def _soul_category(self, name: str) -> str | None:
        if name in self.ATTACK_SOUL_NAMES:
            return 'attack'
        if name in self.FUNCTIONAL_SOUL_NAMES:
            return 'functional'
        return None

    def _soul_target_position(self, set_index: int) -> tuple[int, int]:
        """返回御魂类卡牌的投放位置；前排 1-6 号位统一向北偏移 5 像素。"""
        x, y = self._set_position(set_index)
        if set_index <= 6:
            y += self.SOUL_FRONT_ROW_Y_OFFSET
        return x, y

    def _can_equip_soul_on_unit(self, name: str, soul_name: str) -> bool:
        """按策略 A 判断指定式神是否仍可佩戴该指定御魂（禁重复、留够纹章槽、回手待确认屏蔽）。"""
        budget = self._unit_equipment_slot_budget(name)
        if not budget['can_preferred_soul']:
            return False
        return soul_name not in budget['occupied']

    def _soul_preferred_needing_units(self, soul_name: str) -> list[str]:
        """返回配置了该指定御魂且当前仍可继续佩戴的全部式神名。"""
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        return [
            name
            for name, config in strategy_shikigami.items()
            if soul_name in config.get('preferred_souls', ())
            and self._can_equip_soul_on_unit(name, soul_name)
        ]

    def _soul_hand_reserve_info(
        self,
        soul_cards: list[dict] | None = None,
    ) -> tuple[dict[str, int], dict[str, set[str]]]:
        """按手牌现存御魂与每名式神剩余需求槽位（unmet_soul_slots）有界计算预留，不按候选列表长度机械锁死。"""
        cards = self._soul_hand_cards() if soul_cards is None else list(soul_cards)
        remaining_hand = Counter(card['name'] for card in cards)
        reserve_counts: dict[str, int] = {}
        reserve_owners: dict[str, set[str]] = {}
        if not remaining_hand:
            return reserve_counts, reserve_owners

        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        unit_demands: list[tuple[str, int, list[str]]] = []
        for unit_name, config in strategy_shikigami.items():
            budget = self._unit_equipment_slot_budget(unit_name)
            cap = int(budget.get('unmet_soul_slots', 0) or 0)
            if not budget.get('can_preferred_soul') or cap <= 0:
                continue
            seen_souls: set[str] = set()
            matching_in_hand: list[str] = []
            for soul_name in config.get('preferred_souls', ()):
                if soul_name in seen_souls or soul_name in budget['occupied']:
                    continue
                seen_souls.add(soul_name)
                if remaining_hand.get(soul_name, 0) > 0:
                    matching_in_hand.append(soul_name)
            if matching_in_hand:
                unit_demands.append((unit_name, cap, matching_in_hand))

        # 候选更窄/余地更少的单位先匹配，再按配置顺序在 unmet_soul_slots 上限内占用现存御魂。
        unit_demands.sort(key=lambda item: (len(item[2]) - item[1], len(item[2]), item[0]))
        for unit_name, cap, matching in unit_demands:
            rem_cap = cap
            for soul_name in matching:
                if rem_cap <= 0:
                    break
                if remaining_hand.get(soul_name, 0) <= 0:
                    continue
                remaining_hand[soul_name] -= 1
                reserve_counts[soul_name] = reserve_counts.get(soul_name, 0) + 1
                reserve_owners.setdefault(soul_name, set()).add(unit_name)
                rem_cap -= 1
        return reserve_counts, reserve_owners

    def _soul_reserve_count(self, soul_name: str) -> int:
        """返回需要为尚未满足的指定配置预留的同名御魂张数（受手牌与式神需求上限约束）。"""
        hand_cards = self._soul_hand_cards()
        if any(card['name'] == soul_name for card in hand_cards):
            reserve_counts, _ = self._soul_hand_reserve_info(hand_cards)
            return int(reserve_counts.get(soul_name, 0))
        return len(self._soul_preferred_needing_units(soul_name))

    def _soul_generic_target_entries(
        self,
        soul_name: str,
        category: str,
        verified_names: set[str],
        *,
        relax_soul_reserve: bool = False,
    ) -> list[tuple[str, int, tuple[int, int]]]:
        """策略 A 通用御魂目标：按配置位置判前后排（功能 1..6、输出 7..12），按有效实际位投放。"""
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        wanted_front = category != 'attack'
        targets = []
        for name in self._verified_board_lineup_names(verified_names):
            config = strategy_shikigami.get(name)
            if config is None or config.get('position') is None:
                continue
            configured_pos = int(config['position'])
            if (configured_pos <= 6) != wanted_front:
                continue
            budget = self._unit_equipment_slot_budget(
                name,
                relax_soul_reserve=relax_soul_reserve,
            )
            if not budget['can_generic_soul'] or soul_name in budget['occupied']:
                continue
            actual_pos = self._registered_actual_position(name)
            if actual_pos is None:
                continue
            targets.append((name, actual_pos, self._soul_target_position(actual_pos)))
        return sorted(targets, key=lambda item: (item[1], item[0]))

    def _soul_target_entries(
        self,
        soul_name: str,
        category: str,
        verified_names: set[str],
        *,
        hand_count: int | None = None,
        relax_soul_reserve: bool = False,
    ) -> list[tuple[str, int, tuple[int, int], bool]]:
        """返回 (target_name, actual_pos, drop_point, is_preferred)；未上阵先留够需要数，满仓释放可走通用。"""
        verified = self._verified_board_lineup_names(verified_names)
        needing = self._soul_preferred_needing_units(soul_name)
        deployed_preferred = []
        for name in needing:
            if name not in verified:
                continue
            actual_pos = self._registered_actual_position(name)
            if actual_pos is not None:
                deployed_preferred.append((name, actual_pos))
        if deployed_preferred:
            # 指定御魂优先给已上阵的指定对象，使用实际站位，不受通用前后排限制。
            deployed_preferred.sort(key=lambda item: (item[1], item[0]))
            return [
                (name, pos, self._soul_target_position(pos), True)
                for name, pos in deployed_preferred
            ]

        reserve_count = 0 if relax_soul_reserve else self._soul_reserve_count(soul_name)
        available_count = 1 if hand_count is None else int(hand_count)
        if available_count <= reserve_count:
            return []
        return [
            (name, pos, point, False)
            for name, pos, point in self._soul_generic_target_entries(
                soul_name,
                category,
                verified,
                relax_soul_reserve=relax_soul_reserve,
            )
        ]

    def _soul_targets(
        self,
        soul_name: str,
        category: str,
        verified_names: set[str],
        *,
        hand_count: int | None = None,
        relax_soul_reserve: bool = False,
    ) -> list[tuple[int, tuple[int, int]]]:
        """优先返回阵容专属御魂目标（按实际站位），超额部分再走通用配置前后排+实际落点规则。"""
        return [
            (set_index, point)
            for _, set_index, point, _ in self._soul_target_entries(
                soul_name,
                category,
                verified_names,
                hand_count=hand_count,
                relax_soul_reserve=relax_soul_reserve,
            )
        ]

    def _is_lineup_preferred_soul(self, soul_name: str) -> bool:
        """判断御魂是否被当前阵容任一式神列为专属御魂。"""
        return any(
            soul_name in config.get('preferred_souls', ())
            for config in self.get_lineup_strategy()['shikigami'].values()
        )

    def _template_soul_hand_cards(self) -> list[dict]:
        """在手牌区对 soul 模板执行多尺度匹配。"""
        candidates = []
        roi_x, roi_y, roi_width, roi_height = self.HAND_AREA
        source = self.device.image[
            roi_y:roi_y + roi_height,
            roi_x:roi_x + roi_width,
        ]
        for name, rule in self.soul_hand_rules:
            category = self._soul_category(name)
            if category is None:
                continue
            matches = []
            template = rule.image
            for scale in self.SOUL_TEMPLATE_SCALES:
                width = max(1, int(template.shape[1] * scale))
                height = max(1, int(template.shape[0] * scale))
                if width > source.shape[1] or height > source.shape[0]:
                    continue
                scaled = cv2.resize(
                    template,
                    (width, height),
                    interpolation=(
                        cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
                    ),
                )
                result = cv2.matchTemplate(
                    source,
                    scaled,
                    cv2.TM_CCOEFF_NORMED,
                )
                locations = np.where(
                    result >= self.SOUL_TEMPLATE_THRESHOLD
                )
                for point_x, point_y in zip(*locations[::-1]):
                    matches.append((
                        float(result[point_y, point_x]),
                        roi_x + int(point_x),
                        roi_y + int(point_y),
                        width,
                        height,
                    ))
            if matches:
                boxes = [list(match[1:]) for match in matches]
                scores = [match[0] for match in matches]
                indices = cv2.dnn.NMSBoxes(
                    boxes,
                    scores,
                    score_threshold=self.SOUL_TEMPLATE_THRESHOLD,
                    nms_threshold=0.3,
                )
                matches = [
                    matches[int(index)]
                    for index in np.array(indices).reshape(-1).tolist()
                ] if len(indices) else []
            for score, x, y, width, height in matches:
                candidates.append({
                    'name': name,
                    'text': self.SOUL_DISPLAY_NAMES[name],
                    'position': (x + width // 2, y + height // 2),
                    'score': score,
                    'source': 'template',
                    'category': category,
                })
                logger.debug(
                    f'Chess soul image matched: {self.SOUL_DISPLAY_NAMES[name]}, '
                    f'score={score:.3f}, box={(x, y, width, height)}'
                )
        return candidates

    def _soul_hand_cards(self) -> list[dict]:
        """仅使用 soul 文件夹图片识别御魂，按手牌横坐标去重并同帧缓存结果。"""
        image = self.device.image
        key = (getattr(self.device, 'image_frame_id', None), id(image))
        cached = getattr(self, '_soul_hand_cards_cache', None)
        if cached is not None and cached[0] == key:
            return [dict(item) for item in cached[1]]
        merged = []
        candidates = self._template_soul_hand_cards()
        for candidate in sorted(
            candidates,
            key=lambda item: (
                item['position'][0],
                -item['score'],
            ),
        ):
            existing = next((
                item
                for item in merged
                if abs(item['position'][0] - candidate['position'][0]) <= 24
            ), None)
            if existing is None:
                merged.append(candidate)
            elif candidate['score'] > existing['score']:
                merged.remove(existing)
                merged.append(candidate)
        result = sorted(merged, key=lambda item: item['position'][0])
        self._soul_hand_cards_cache = (key, result)
        return [dict(item) for item in result]

    def _soul_match_in_card(
        self,
        card_roi: tuple[int, int, int, int],
        soul_cards: list[dict] | None = None,
    ) -> dict | None:
        """返回落在指定手牌框内的最佳御魂图片匹配。"""
        x, _, width, _ = card_roi
        soul_cards = (
            self._soul_hand_cards() if soul_cards is None else soul_cards
        )
        matches = [
            item
            for item in soul_cards
            if x - 8 <= item['position'][0] <= x + width + 8
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item['score'])

    def _discover_named_hand_cards(self, expected_text: str) -> list[dict]:
        """共用灰度 badge 定位；只接受 OCR 完整命中的发现卡名称。"""
        if any(self.appear(rule) for rule in
               (self.I_SELECT_SOUL_1, self.I_SELECT_SOUL_2, self.I_SELECT_SOUL_3)):
            return []  # 三选一弹窗后的手牌仍可能可见，不操作被遮挡的背景卡。
        return [dict(card) for card in self._frame_card_scan('emblem')
                if card['type'] == 'discovery' and card['kind'] == expected_text]

    def _discover_soul_hand_cards(self) -> list[dict]:
        return self._discover_named_hand_cards('发现御魂')

    def _discover_badge_hand_cards(self) -> list[dict]:
        return self._discover_named_hand_cards('发现纹章')

    def _wait_for_discover_soul_choices(self) -> list[RuleImage]:
        """等待发现御魂三选一界面，并返回本帧实际出现的选项。"""
        deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
        rules = (
            self.I_SELECT_SOUL_1,
            self.I_SELECT_SOUL_2,
            self.I_SELECT_SOUL_3,
        )
        while time.monotonic() < deadline:
            self.screenshot()
            options = [rule for rule in rules if self.appear(rule)]
            if options:
                return options
        return []

    def discover_souls_from_hand(self) -> int:
        """优先使用所有“发现御魂/发现纹章”卡并随机选择。"""
        used = 0
        for _ in range(self.DISCOVER_SOUL_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop using Chess discover-soul cards: preparation was '
                    'interrupted or has ended'
                )
                break
            cards = sorted(
                self._discover_badge_hand_cards()
                + self._discover_soul_hand_cards(),
                key=lambda item: item['position'][0],
            )
            if not cards:
                break

            card = cards[0]
            logger.debug(
                f'Use Chess {card["kind"]} hand card: '
                f'text={card["text"]}, '
                f'similarity={card["similarity"]:.3f}, '
                f'position={card["position"]}'
            )
            # 上游直接点 card['position']（卡片中心）。本地走 L1：在手牌可点区域内统一采样一次。
            # Frame 卡片的 roi 就是 Frame 里 Click 范围（整张手牌可点区域），取代旧 OCR 卡名框 bounds。
            execute_single_click(
                self.device,
                ClickBounds(card['roi'], 'CHESS_DISCOVER_CARD'),
            )

            use_deadline = time.monotonic() + self.DISCOVER_SOUL_UI_TIMEOUT
            while time.monotonic() < use_deadline:
                self.screenshot()
                if not self._is_preparation_mode():
                    logger.debug(
                        'Stop using Chess discover-soul card: preparation was '
                        'interrupted or has ended'
                    )
                    return used
                if self.appear_then_click(
                    self.I_USE_SOUL,
                    interval=self.ACTION_SETTLE_INTERVAL,
                ):
                    break
            else:
                logger.warning(
                    f'Chess {card["kind"]} card selected, but use button '
                    'did not appear; keep the card and stop this pass'
                )
                break

            options = self._wait_for_discover_soul_choices()
            if not options:
                logger.warning(
                    'Chess discover-soul selection did not appear; '
                    'stop this pass'
                )
                break

            selected = random.choice(options)
            logger.debug(
                f'Random Chess {card["kind"]} option: '
                f'{selected.name}, available={[rule.name for rule in options]}'
            )
            select_rules = (
                self.I_SELECT_SOUL_1,
                self.I_SELECT_SOUL_2,
                self.I_SELECT_SOUL_3,
            )
            for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
                self.device.click_record_remove(selected)
                self.click(selected)
                if self._wait_chess_action_state(
                    lambda: not any(
                        self.appear(rule) for rule in select_rules
                    )
                ):
                    used += 1
                    logger.debug(
                        'Chess discover-soul option confirmed: '
                        f'{selected.name}, '
                        f'attempt={attempt}/'
                        f'{self.ACTION_ICON_MAX_ATTEMPTS}'
                    )
                    break
                logger.warning(
                    'Chess discover-soul selection remained open after click: '
                    f'{selected.name}, '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                    f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
                )
            else:
                raise GameStuckError(
                    'Chess: discover-soul option selection failed after '
                    '3 attempts'
                )
        else:
            logger.warning(
                'Stop using Chess discover-soul cards at safety limit '
                f'{self.DISCOVER_SOUL_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess discover-soul handling complete, used={used}')
        return used

    def _select_next_equipment_action(
        self,
        verified_names: set[str],
        *,
        repeated_attempts: dict | None = None,
        max_attempts: int = 2,
        relax_soul_reserve: bool = False,
    ) -> dict | None:
        """按「指定装备（纹章/御魂）-> 通用装备（纹章/御魂）」返回下一笔可装配动作。"""
        attempts = {} if repeated_attempts is None else repeated_attempts
        emblem_cards = sorted(
            self._recognized_emblem_hand_cards(),
            key=lambda item: item['position'][0],
        )
        soul_cards = self._soul_hand_cards()
        emblem_counts = Counter(card['name'] for card in emblem_cards)
        soul_counts = Counter(card['name'] for card in soul_cards)

        def _pick_emblem(want_preferred: bool, tier: str) -> dict | None:
            for card in emblem_cards:
                entries = self._emblem_target_entries(
                    card['name'],
                    verified_names,
                    hand_count=emblem_counts[card['name']],
                    relax_soul_reserve=relax_soul_reserve,
                )
                for target_name, set_index, is_preferred in entries:
                    if is_preferred != want_preferred:
                        continue
                    attempt_key = (
                        'emblem',
                        card['name'],
                        card['position'][0] // 20,
                        set_index,
                    )
                    if attempts.get(attempt_key, 0) >= max_attempts:
                        continue
                    return {
                        'kind': 'emblem',
                        'tier': tier,
                        'card': card,
                        'target_name': target_name,
                        'set_index': set_index,
                        'attempt_key': attempt_key,
                    }
            return None

        def _pick_soul(want_preferred: bool, tier: str) -> dict | None:
            for card in soul_cards:
                entries = self._soul_target_entries(
                    card['name'],
                    card['category'],
                    verified_names,
                    hand_count=soul_counts[card['name']],
                    relax_soul_reserve=relax_soul_reserve,
                )
                for target_name, set_index, _, is_preferred in entries:
                    if is_preferred != want_preferred:
                        continue
                    attempt_key = (
                        'soul',
                        card['name'],
                        card['position'][0] // 20,
                        set_index,
                    )
                    if attempts.get(attempt_key, 0) >= max_attempts:
                        continue
                    return {
                        'kind': 'soul',
                        'tier': tier,
                        'card': card,
                        'target_name': target_name,
                        'set_index': set_index,
                        'attempt_key': attempt_key,
                    }
            return None

        for picker in (
            lambda: _pick_emblem(True, 'preferred_emblem'),
            lambda: _pick_soul(True, 'preferred_soul'),
            lambda: _pick_emblem(False, 'generic_emblem'),
            lambda: _pick_soul(False, 'generic_soul'),
        ):
            action = picker()
            if action is not None:
                return action
        return None

    def _equip_selected_hand_equipment(self, action: dict) -> dict:
        """执行单张御魂或纹章装配，并仅凭同名手牌数减少确认后才登记装备槽。"""
        kind = action['kind']
        tier = action['tier']
        card = action['card']
        name = card['name']
        target_name = action['target_name']
        set_index = int(action['set_index'])
        target_display = self._shikigami_display_name(target_name)
        display_equip = (
            name
            if kind == 'emblem'
            else card.get('text', self.SOUL_DISPLAY_NAMES.get(name, name))
        )
        operation_name = (
            f'EMBLEM_{name}' if kind == 'emblem' else name.upper()
        )
        goldfish_baseline = (
            self._goldfish_formation_baseline(target_name, emblem=True)
            if (kind == 'emblem' and name == '荒川纹章')
            else None
        )
        before = self._hand_card_identity_count(kind, name)
        logger.info(
            f'检测到{display_equip}({tier})，'
            f'准备移动到{target_display}({target_name})的实际{set_index}号位，'
            f'手牌同名数={before}'
        )
        if not self._equip_soul_card(
            source=card['position'],
            set_index=set_index,
            operation_name=operation_name,
        ):
            return {
                'confirmed': False,
                'aborted': True,
                'before': before,
                'after': before,
                'name': name,
                'kind': kind,
                'target_name': target_name,
                'set_index': set_index,
            }

        confirmed = self._wait_hand_card_removed(
            before,
            lambda: self._hand_card_identity_count(kind, name),
        )
        after = self._hand_card_identity_count(kind, name)
        if not confirmed:
            # 单次拖动未确认时保留式神站位与装备记录并复查画面，禁止据此认定槽位已满或下阵。
            logger.warning(
                f'Chess equipment equip not confirmed: {display_equip} -> '
                f'{target_display}({target_name}) at actual set {set_index}, '
                f'hand_count={before}->{after}; preserve records and recheck screen'
            )
            return {
                'confirmed': False,
                'aborted': False,
                'before': before,
                'after': after,
                'name': name,
                'kind': kind,
                'target_name': target_name,
                'set_index': set_index,
            }

        recorded = self._record_shikigami_soul(target_name, name)
        if not recorded:
            logger.warning(
                f'Chess equipment disappeared from hand but attributes '
                f'rejected it: {display_equip} -> {target_display}({target_name})'
            )
            return {
                'confirmed': False,
                'aborted': False,
                'before': before,
                'after': after,
                'name': name,
                'kind': kind,
                'target_name': target_name,
                'set_index': set_index,
            }

        if kind == 'emblem' and name == '荒川纹章':
            if goldfish_baseline is not None:
                self._pending_goldfish_probe = goldfish_baseline
            if goldfish_baseline is not None or (
                getattr(self, '_arakawa_goldfish_current_position', None)
                is None
            ):
                self._goldfish_lookup_needed = True
                logger.debug(
                    'Mark pending Chess Arakawa goldfish lookup after emblem equip; '
                    'defer regular board scan until preparation tail'
                )

        logger.info(
            f'Chess equipment equip confirmed: {display_equip} -> '
            f'{target_display}({target_name}) at actual set {set_index}, '
            f'hand_count={before}->{after}'
        )
        return {
            'confirmed': True,
            'aborted': False,
            'before': before,
            'after': after,
            'name': name,
            'kind': kind,
            'target_name': target_name,
            'set_index': set_index,
        }

    def equip_souls_from_hand(
        self,
        verified_names: set[str] | None = None,
        *,
        max_actions: int | None = None,
        include_special: bool = True,
        repeated_attempts: dict | None = None,
        stop_on_unconfirmed: bool = False,
        relax_soul_reserve: bool = False,
    ) -> list[str]:
        """在备战阶段按策略 A 与实际站位分配御魂和纹章，受余时与失败复核有界保护。"""
        if not self._is_preparation_mode():
            logger.debug(
                'Skip equipping Chess souls: preparation was interrupted or '
                'has ended'
            )
            return []
        start_wall = time.monotonic()
        unknown_budget_s = float(getattr(self, 'PREP_UNKNOWN_TIME_SLICE_BUDGET_S', 8.0))
        min_action_s = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
        remaining = self._safe_read_remaining_time()
        if remaining is not None and remaining < min_action_s:
            logger.info(
                'Skip equipping Chess souls by remaining time: '
                f'remaining_time={remaining} < {min_action_s}'
            )
            return []

        if include_special:
            # “发现御魂/发现纹章”会生成普通装备，先全部使用再进入装备分配。
            self.discover_souls_from_hand()
        verified_names = self._verified_board_lineup_names(verified_names)
        if include_special:
            self.use_golden_copies_from_hand(verified_names)
        if not verified_names:
            logger.debug(
                'Keep Chess souls in hand: no shikigami with verified '
                'lineup membership and registered board position'
            )
            return []

        equipped = []
        if include_special:
            # 守护之印使用独立模板与独立流程，沿用既有前置位置。
            if self.equip_hakuzosu_protect_after_deploy(verified_names):
                equipped.append(self.HAKUZOSU_PROTECT_NAME)

        attempts = {} if repeated_attempts is None else repeated_attempts
        slot_failures: dict[int, int] = {}
        reverify_threshold = int(getattr(self, 'EQUIP_FAILURE_REVERIFY_THRESHOLD', 2))
        cooled_slots: set[int] = set()
        for _ in range(self.SOUL_EQUIP_SAFETY_LIMIT):
            if max_actions is not None and len(equipped) >= max_actions:
                break
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop equipping Chess souls: '
                    'mode is no longer preparation'
                )
                break
            remaining_now = self._safe_read_remaining_time()
            if remaining_now is not None and remaining_now < min_action_s:
                logger.info(
                    'Stop equipping Chess souls by remaining time: '
                    f'remaining_time={remaining_now} < {min_action_s}'
                )
                break
            if remaining_now is None and (time.monotonic() - start_wall) >= unknown_budget_s:
                logger.info(
                    'Stop equipping Chess souls: unknown-countdown wall budget exhausted '
                    f'({unknown_budget_s:.1f}s)'
                )
                break

            active_verified = {
                n
                for n in verified_names
                if self._registered_actual_position(n) not in cooled_slots
            }
            if not active_verified:
                break
            action = self._select_next_equipment_action(
                active_verified,
                repeated_attempts=attempts,
                relax_soul_reserve=relax_soul_reserve,
            )
            if action is None:
                break

            attempt_key = action['attempt_key']
            attempts[attempt_key] = attempts.get(attempt_key, 0) + 1
            outcome = self._equip_selected_hand_equipment(action)
            if outcome['aborted']:
                break
            if not outcome['confirmed']:
                target_slot = int(action['set_index'])
                slot_failures[target_slot] = slot_failures.get(target_slot, 0) + 1
                if slot_failures[target_slot] >= reverify_threshold:
                    cooled_slots.add(target_slot)
                    rec = self._board_slots_table().get(target_slot)
                    if rec and rec.get('source') != 'init' and not stop_on_unconfirmed:
                        rec['stale_reason'] = 'equip_failed_needs_reverify'
                self.screenshot()
                if stop_on_unconfirmed or not self._is_preparation_mode():
                    break
                continue

            equipped.append(outcome['name'])
        else:
            logger.warning(
                'Stop equipping Chess souls at safety limit '
                f'{self.SOUL_EQUIP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess soul equipment complete, equipped={equipped}')
        return equipped

    def _handle_known_goldfish_before_direct_deploy(
        self,
        candidate: dict,
        set_index: int,
        *,
        round_state: dict,
    ) -> dict:
        """上卡前只处理两类已知金鱼边界：已站定配置位硬保护，及已确认错位金鱼先搬后上（0 点详情）。"""
        name = candidate['name']
        set_index = int(set_index)
        if self._is_placed_goldfish_protected_slot(set_index):
            logger.warning(
                'Protect Chess placed goldfish slot before direct deploy: '
                f'defer card={name}, set={set_index}'
            )
            return {'action': 'defer_protected_goldfish', 'candidate': candidate}

        if not self._is_confirmed_arakawa_goldfish(set_index):
            return {'action': 'proceed', 'candidate': candidate}

        if not self._is_preparation_mode() or self._is_shop_open():
            return {'action': 'stop', 'candidate': candidate}

        attempt_key = (name, set_index)
        if attempt_key in round_state['blocked_card_attempts']:
            logger.info(
                'Defer Chess card blocked by confirmed misplaced goldfish: '
                f'relocation already attempted once this round (card={name}, set={set_index})'
            )
            return {'action': 'defer', 'candidate': candidate}

        bond_status = self._check_arakawa_bond_qualified()
        gf_target = self._arakawa_goldfish_target_position()
        remaining = self._read_remaining_time()
        round_state['blocked_card_attempts'].add(attempt_key)
        if not bond_status['qualified']:
            if gf_target is not None and int(gf_target) != set_index:
                self._set_goldfish_relocation_pending(True, source='blocking')
            logger.info(
                'Defer Chess card on confirmed misplaced goldfish: '
                f'card={name}, set={set_index}, reason={bond_status["reason"]}'
            )
            return {'action': 'defer', 'candidate': candidate}

        if (
            remaining is None
            or remaining < self.GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING
        ):
            if gf_target is not None and int(gf_target) != set_index:
                self._set_goldfish_relocation_pending(True, source='blocking')
            logger.info(
                'Defer Chess card on confirmed misplaced goldfish by remaining time: '
                f'card={name}, set={set_index}, remaining_time={remaining}, '
                f'required>={self.GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING}'
            )
            return {'action': 'defer', 'candidate': candidate}

        usable, usable_reason, gf_target = self._check_goldfish_target_slot_usable(
            set_index
        )
        if not usable:
            if gf_target is not None and int(gf_target) != set_index:
                self._set_goldfish_relocation_pending(True, source='blocking')
            logger.info(
                'Defer Chess card on confirmed misplaced goldfish: '
                f'card={name}, set={set_index}, goldfish_target={gf_target}, '
                f'reason={usable_reason}, remaining_time={remaining}'
            )
            return {'action': 'defer', 'candidate': candidate}

        moved = self._move_arakawa_goldfish(set_index, verify_vacated_source=True)
        if not self._is_preparation_mode() or self._is_shop_open():
            return {'action': 'stop', 'candidate': candidate}
        if not moved:
            logger.info(
                'Defer Chess card after misplaced goldfish move remained unconfirmed: '
                f'card={name}, set={set_index}, goldfish_target={gf_target}'
            )
            return {'action': 'defer', 'candidate': candidate}

        round_state['inspected_slots'].discard(set_index)
        round_state['inspected_slot_results'].pop(set_index, None)
        if gf_target is not None:
            round_state['inspected_slots'].discard(int(gf_target))
            round_state['inspected_slot_results'].pop(int(gf_target), None)
        self.screenshot()
        logger.info(
            'Cleared confirmed misplaced goldfish before deploy; rescan hand: '
            f'card={name}, freed_set={set_index}, goldfish_target={gf_target}, '
            f'remaining_time={remaining}'
        )
        return {'action': 'rescan', 'candidate': candidate}

    @staticmethod
    def _pending_record_consumed_or_merged(record: dict) -> bool:
        """判断待核实记录是否带有手牌消耗或合卡升星线索（必须保留同名上阵保护）。"""
        return bool(
            record.get('hand_consumed')
            or record.get('hand_star_upgraded')
            or record.get('board_star_upgraded')
        )

    def _can_recover_stale_pending_from_current_evidence(
        self,
        name: str,
        record: dict,
        *,
        probed_slot: int | None = None,
        probed_name: str | None = None,
    ) -> tuple[bool, str]:
        """按当前稳定证据检查跨回合旧 pending 是否属于回弹假消耗，可安全解除封锁。"""
        current_round = getattr(self, '_current_round_no', None)
        if record.get('last_attempt_round') == current_round:
            return False, 'same_round'
        if not self._pending_record_consumed_or_merged(record):
            return True, 'unconsumed_cross_round'
        if record.get('hand_star_upgraded') or record.get('board_star_upgraded'):
            return False, 'star_upgrade_clue'
        if record.get('newly_occupied_slots'):
            return False, 'newly_occupied_exists'
        prev_hand = int(record.get('hand_count_before') or 0)
        if prev_hand < 1:
            return False, 'missing_hand_baseline'
        cur_hand = self._lineup_hand_card_match_count(name)
        if cur_hand < prev_hand:
            return False, 'hand_count_still_below_before'
        target_slot = int(record.get('set_index') or 0)
        if not 1 <= target_slot <= 12:
            return False, 'invalid_target_slot'
        if self._board_set_state(target_slot) == 'empty':
            return True, 'recovered_stale_pending_empty_target'
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        if (
            probed_slot is not None
            and int(probed_slot) == target_slot
            and probed_name in strategy_shikigami
            and probed_name != name
        ):
            return True, f'recovered_target_confirmed_other_lineup:{probed_name}'
        rec = self._board_slots_table()[target_slot]
        if (
            rec.get('valid')
            and rec.get('kind') == 'lineup'
            and rec.get('identity') not in (None, name)
        ):
            return True, f'recovered_slot_confirmed_other_lineup:{rec["identity"]}'
        return False, 'no_clear_recovery_evidence'

    def _cleanup_nonblocking_pending_deploys(self) -> list[str]:
        """零点击清理已确认上阵、未消耗旧 pending 或当前证据证实假消耗的跨回合记录。"""
        pending = self._get_pending_deploys()
        if not pending:
            return []
        current_round = getattr(self, '_current_round_no', None)
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        cleared_names: list[str] = []
        for name in list(pending.keys()):
            record = pending.get(name)
            if record is None:
                continue
            if name in deployed_names:
                self._clear_pending_deploy(name)
                cleared_names.append(name)
                continue
            if record.get('last_attempt_round') != current_round:
                recoverable, reason = self._can_recover_stale_pending_from_current_evidence(
                    name,
                    record,
                )
                if recoverable:
                    updated = dict(record)
                    updated['hand_consumed'] = False
                    logger.info(
                        'Recover stale Chess pending deploy from current evidence: '
                        f'card={name}, reason={reason}'
                    )
                    self._clear_pending_deploy(name)
                    cleared_names.append(name)
        return cleared_names

    def _has_reconcilable_pending_deploys(
        self,
        round_state: dict | None = None,
    ) -> bool:
        """判断本轮是否尚余单次核实配额且存在跨回合已消耗/合卡待核实记录。"""
        if round_state is None:
            round_state = self._ensure_prep_goldfish_round_state()
        clicks_used = int(round_state.get('pending_reconcile_clicks_used', 0) or 0)
        if clicks_used >= self.PENDING_DEPLOY_MAX_INSPECTS_PER_ROUND:
            return False
        current_round = getattr(self, '_current_round_no', None)
        return any(
            rec.get('last_attempt_round') != current_round
            and self._pending_record_consumed_or_merged(rec)
            for rec in self._get_pending_deploys().values()
        )

    def _select_pending_probe_slot(
        self,
        name: str,
        record: dict,
        *,
        protected_slots: set[int],
        inspected_slots: set[int],
    ) -> tuple[int | None, list[int]]:
        """为跨回合待核实记录挑选唯一可点击核实格；无合法格返回 (None, newly_candidates)。"""
        set_index = int(record.get('set_index') or 0)
        newly_candidates = [
            int(pos)
            for pos in (record.get('newly_occupied_slots') or ())
            if int(pos) not in protected_slots
            and int(pos) not in inspected_slots
            and self._board_set_state(int(pos)) == 'occupied'
        ]
        target_candidate = (
            set_index
            if 1 <= set_index <= 12
            and set_index not in protected_slots
            and set_index not in inspected_slots
            and self._board_set_state(set_index) != 'empty'
            else None
        )
        if (
            record.get('observed_name') not in (None, name)
            and len(newly_candidates) == 1
        ):
            return newly_candidates[0], newly_candidates
        if target_candidate is not None:
            return target_candidate, newly_candidates
        if len(newly_candidates) == 1:
            return newly_candidates[0], newly_candidates
        return None, newly_candidates

    def _reconcile_pending_deploys_once(
        self,
        round_state: dict | None = None,
        *,
        budget: PrepSliceBudget | None = None,
    ) -> list[str]:
        """跨回合余时与预算充足时公平轮转并至多主动点 1 次详情核实 1 条旧 pending。"""
        if round_state is None:
            round_state = self._ensure_prep_goldfish_round_state()

        # 1) 零点击先清理已上阵/可恢复记录（不消耗核实上限）。
        resolved_names = self._cleanup_nonblocking_pending_deploys()
        pending = self._get_pending_deploys()
        if not pending:
            return resolved_names

        # 2) 整轮旧 pending 点击上限与切片共享预算共同把关。
        clicks_used = int(round_state.get('pending_reconcile_clicks_used', 0) or 0)
        if clicks_used >= self.PENDING_DEPLOY_MAX_INSPECTS_PER_ROUND:
            logger.debug(
                'Skip cross-round Chess pending reconcile: per-round inspect budget used '
                f'({clicks_used}/{self.PENDING_DEPLOY_MAX_INSPECTS_PER_ROUND})'
            )
            return resolved_names

        # 3) 仅确认处于准备阶段、商店关闭、倒计时与切片预算达标时才允许主动查询。
        if not self._is_preparation_mode() or self._is_shop_open():
            return resolved_names
        remaining = self._read_remaining_time()
        if budget is not None:
            can_insp, insp_reason = budget.can_start_inspect(
                remaining,
                min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
            )
            if not can_insp:
                logger.info(
                    'Defer cross-round Chess pending deploy check by slice budget: '
                    f'pending_count={len(pending)}, remaining_time={remaining}, reason={insp_reason}'
                )
                return resolved_names
        elif (
            remaining is None
            or remaining < self.PENDING_DEPLOY_RECONCILE_MIN_REMAINING
        ):
            logger.info(
                'Defer cross-round Chess pending deploy check by remaining time: '
                f'pending_count={len(pending)}, remaining_time={remaining}, '
                f'required>={self.PENDING_DEPLOY_RECONCILE_MIN_REMAINING}'
            )
            return resolved_names

        current_round = getattr(self, '_current_round_no', None)
        goldfish_positions, registered_positions = self._protected_recall_positions()
        protected_slots = goldfish_positions | registered_positions
        inspected_slots = round_state['inspected_slots']

        # 4) 从跨回合已消耗/疑似合卡记录中，筛选当前有合法核实格者并按最久未尝试回合轮转排序。
        eligible: list[tuple[int, int, str, dict, int]] = []
        for insert_idx, name in enumerate(list(pending.keys())):
            record = pending.get(name)
            if record is None:
                continue
            if record.get('last_attempt_round') == current_round:
                # 本回合已尝试或本回合新产生的待核实，保留同名保护且不占用当前旧记录查询。
                continue
            if not self._pending_record_consumed_or_merged(record):
                continue
            try:
                probe_slot, newly_candidates = self._select_pending_probe_slot(
                    name,
                    record,
                    protected_slots=protected_slots,
                    inspected_slots=inspected_slots,
                )
            except GameStuckError as exc:
                logger.warning(
                    'Stop cross-round Chess pending reconcile: board anchor missing '
                    f'while inspecting slots for {name}: {exc}'
                )
                return resolved_names
            if probe_slot is None:
                # 当前无合法核实格（如已被己方/金鱼占格或仍为空）不耗用唯一机会，让后续可核实记录优先。
                logger.debug(
                    'Skip Chess pending deploy candidate without legal probe slot: '
                    f'card={name}, target_set={record.get("set_index")}, '
                    f'newly_candidates={newly_candidates}'
                )
                continue
            raw_last_round = record.get('last_attempt_round')
            attempt_order = -1 if raw_last_round is None else int(raw_last_round)
            eligible.append((attempt_order, insert_idx, name, record, probe_slot))

        if not eligible:
            return resolved_names

        _, _, target_name, target_record, probe_slot = min(
            eligible,
            key=lambda item: (item[0], item[1]),
        )
        logger.info(
            'Select single cross-round Chess pending deploy to inspect: '
            f'card={target_name}, probe_slot={probe_slot}, '
            f'last_attempt_round={target_record.get("last_attempt_round")}, '
            f'eligible_count={len(eligible)}, remaining_time={remaining}'
        )

        # 5) 对选中的唯一记录最多主动点击 1 次详情；仅真实发出点击后消耗配额。
        inspection = self._inspect_board_set_shikigami(probe_slot, max_attempts=1)
        clicked = bool(
            inspection.get(
                'clicked',
                inspection.get('reason') not in ('not_preparation', 'shop_open', 'anchor_missing'),
            )
        )
        if not clicked:
            return resolved_names

        round_state['pending_reconcile_clicks_used'] = clicks_used + 1
        if budget is not None:
            budget.consume_inspect()
        inspected_slots.add(probe_slot)
        if inspection['opened']:
            round_state['inspected_slot_results'][probe_slot] = inspection['name']

        if (
            inspection['reason'] == 'not_preparation'
            or not self._is_preparation_mode()
            or self._is_shop_open()
        ):
            updated = dict(target_record)
            updated['last_attempt_round'] = current_round
            pending[target_name] = updated
            self._sync_legacy_pending_arakawa_deploy()
            return resolved_names

        if inspection['opened'] and inspection['name'] == target_name:
            self._register_confirmed_lineup_deploy(
                target_name,
                probe_slot,
                trigger_hakuzosu=True,
            )
            self._clear_pending_deploy(target_name)
            resolved_names.append(target_name)
            logger.info(
                'Reconciled cross-round Chess pending deploy position: '
                f'card={target_name}, actual_set={probe_slot}'
            )
            return resolved_names

        if inspection['opened'] and inspection['name'] == 'arakawa_goldfish':
            self._record_arakawa_goldfish_position(probe_slot, identified=True)
            gf_target = self._arakawa_goldfish_target_position()
            if gf_target is not None and int(gf_target) == probe_slot:
                self._mark_arakawa_goldfish_placed(probe_slot)

        if inspection['opened']:
            recoverable, rec_reason = self._can_recover_stale_pending_from_current_evidence(
                target_name,
                target_record,
                probed_slot=probe_slot,
                probed_name=inspection['name'],
            )
            if recoverable:
                self._clear_pending_deploy(target_name)
                resolved_names.append(target_name)
                logger.info(
                    'Recovered Chess pending deploy after target slot identified other lineup unit: '
                    f'card={target_name}, probed_set={probe_slot}, observed={inspection["name"]}, '
                    f'reason={rec_reason}'
                )
                return resolved_names

        updated = dict(target_record)
        updated['last_attempt_round'] = current_round
        if inspection['opened']:
            updated['observed_name'] = inspection['name']
            updated['reason'] = (
                'name_unreadable'
                if inspection['name'] is None
                else 'target_occupied_by_other'
            )
        else:
            updated['reason'] = inspection['reason']
        pending[target_name] = updated
        self._sync_legacy_pending_arakawa_deploy()
        logger.warning(
            'Keep Chess pending deploy unresolved after cross-round single check: '
            f'card={target_name}, probed_set={probe_slot}, '
            f'reason={updated["reason"]}, observed={updated.get("observed_name")}'
        )
        return resolved_names

    def _move_board_unit(
        self,
        from_slot: int,
        to_slot: int,
        *,
        name: str | None = None,
        source_tag: str = 'board_arrange_move',
    ) -> bool:
        """板内空位直移（0 详情）：源确认变空、目标确认变占才提交格级状态。"""
        src = int(from_slot)
        dst = int(to_slot)
        if src == dst or not (1 <= src <= 12 and 1 <= dst <= 12):
            return False
        if not self._is_preparation_mode() or not self._ensure_shop_closed():
            return False
        if self._is_placed_goldfish_protected_slot(dst):
            return False
        if self._board_set_state(src) != 'occupied' or self._board_set_state(dst) != 'empty':
            return False

        slots_table = self._board_slots_table()
        src_rec = dict(slots_table[src])
        unit_name = name or src_rec.get('identity')
        unit_kind = src_rec.get('kind', 'unknown')
        unit_star = src_rec.get('star') or self._board_set_star(src)

        self.close_shikigami_specifics_if_open()
        logger.info(
            f'Chess board unit move: set {src} -> {dst}, '
            f'unit={unit_name or unit_kind}'
        )
        Press_and_Drag(
            self.device,
            p1=self._set_position(src),
            p2=self._set_position(dst),
            hold_duration=(0.2, 0.3),
            point_random=(-2, -2, 2, 2),
            swipe_duration=0.5,
            name=f'CHESS_MOVE_BOARD_SET_{src}_TO_{dst}',
        )
        round_state = self._ensure_prep_goldfish_round_state()
        round_state['inspected_slots'].discard(src)
        round_state['inspected_slots'].discard(dst)
        round_state['inspected_slot_results'].pop(src, None)
        round_state['inspected_slot_results'].pop(dst, None)

        def move_settled():
            if not self._is_preparation_mode() or self._is_shop_open():
                return True
            return (
                self._board_set_state(src) == 'empty'
                and self._board_set_state(dst) == 'occupied'
            )

        self._wait_chess_action_state(move_settled)
        if not self._is_preparation_mode() or self._is_shop_open():
            return False
        if callable(getattr(self, 'screenshot', None)):
            self.screenshot()
        if (
            self._board_set_state(src) != 'empty'
            or self._board_set_state(dst) != 'occupied'
        ):
            logger.warning(
                f'Chess board move unconfirmed: {src}({self._board_set_state(src)}) '
                f'-> {dst}({self._board_set_state(dst)})'
            )
            return False

        self._invalidate_board_slot(src, 'empty_confirmed', clear_identity=True)
        if unit_name == 'arakawa_goldfish' or unit_kind == 'goldfish':
            self._record_arakawa_goldfish_position(dst, identified=bool(src_rec.get('valid')))
            gf_target = self._arakawa_goldfish_target_position()
            if gf_target is not None and int(gf_target) == dst:
                self._mark_arakawa_goldfish_placed(dst)
        elif unit_name:
            strategy_shikigami = self.get_lineup_strategy()['shikigami']
            resolved_kind = 'lineup' if unit_name in strategy_shikigami else 'non_lineup'
            self._update_board_slot(
                dst,
                occupancy='occupied',
                star=self._board_set_star(dst) or unit_star,
                identity=unit_name,
                kind=resolved_kind,
                valid=bool(src_rec.get('valid', True)),
                player_deployed=(resolved_kind == 'lineup'),
                source=source_tag,
                suspect_merge=False,
                stale_reason=None,
            )
            if resolved_kind == 'lineup':
                todos = getattr(self, '_displaced_lineup_todos', None)
                if isinstance(todos, dict):
                    todos.pop(unit_name, None)
        return True

    def _has_runnable_displaced_todos(self) -> bool:
        """检查是否存在当前未冷却且待回手清理的被换下阵容式神。"""
        todos = getattr(self, '_displaced_lineup_todos', None)
        if not isinstance(todos, dict) or not todos:
            return False
        now = time.monotonic()
        return any(now >= float(item.get('cooldown_until', 0.0)) for item in todos.values())

    def _process_displaced_lineup_todos(
        self,
        *,
        budget: PrepSliceBudget | None = None,
    ) -> list[str]:
        """在同一整理切片预算内，重扫手牌并逐个收尾被换下的阵容式神（循环检测+步数上限）。"""
        todos = getattr(self, '_displaced_lineup_todos', None)
        if not isinstance(todos, dict) or not todos:
            return []
        if not self._is_preparation_mode() or not self._ensure_shop_closed():
            return []

        deployed_done: list[str] = []
        cooldown_s = float(getattr(self, 'DISPLACED_LINEUP_COOLDOWN_SECONDS', 2.0))
        max_steps = budget.max_chain_steps if budget is not None else int(getattr(self, 'DISPLACED_CHAIN_MAX_STEPS', 4))

        for name in sorted(
            list(todos.keys()),
            key=lambda n: float(todos[n].get('created_at', 0.0)),
        ):
            todo = todos.get(name)
            if todo is None:
                continue
            now = time.monotonic()
            if now < float(todo.get('cooldown_until', 0.0)):
                continue
            if not self._is_preparation_mode() or self._is_shop_open():
                break
            target_slot = self.shikigami_deploy_positions.get(name)
            if target_slot is None:
                todos.pop(name, None)
                continue
            target_slot = int(target_slot)
            if budget is not None:
                if budget.chain_steps_used >= max_steps or budget.wall_exhausted():
                    break
                if (name, target_slot) in budget.visited_chain_pairs:
                    logger.info(
                        f'Skip Chess displaced chain loop pair: ({name}, set={target_slot})'
                    )
                    todo['cooldown_until'] = now + cooldown_s
                    continue
                can_act, _ = budget.can_start_action(
                    self._safe_read_remaining_time(),
                    min_remaining=int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3)),
                )
                if not can_act:
                    break
                budget.visited_chain_pairs.add((name, target_slot))
                budget.chain_steps_used += 1

            # 每步重截手牌，杜绝跨帧保存坐标。
            self.screenshot()
            cand = self._find_best_shikigami_hand_card(
                excluded_names=(set(self.shikigami_deploy_positions) - {name}),
            )
            if cand is None or cand['name'] != name:
                todos.pop(name, None)
                continue

            todo['attempts'] = int(todo.get('attempts', 0)) + 1
            res = self.deploy_shikigami_from_hand(
                run_regular_goldfish=False,
                direct_only=False,
                reconcile_pending=False,
                budget=budget,
                candidate_whitelist={name},
            )
            if name in res:
                todos.pop(name, None)
                deployed_done.extend(res)
            else:
                if name in todos:
                    todos[name]['cooldown_until'] = time.monotonic() + cooldown_s
        return deployed_done

    def _record_await_deploy_todo(
        self,
        name: str,
        set_index: int,
        *,
        reason: str,
        recall_slot: int | None = None,
    ) -> None:
        """余时不足或跨切片衔接时登记待办，避免无余时硬上或复用旧候选坐标。"""
        todos = getattr(self, '_displaced_lineup_todos', None)
        if not isinstance(todos, dict):
            todos = {}
            self._displaced_lineup_todos = todos
        prev_todo = todos.get(name, {})
        todos[name] = {
            'name': name,
            'target_slot': int(set_index),
            'recall_slot': int(recall_slot) if recall_slot is not None else None,
            'reason': reason,
            'round_no': getattr(self, '_current_round_no', None),
            'created_at': prev_todo.get('created_at', time.monotonic()),
            'cooldown_until': 0.0,
            'attempts': int(prev_todo.get('attempts', 0)),
        }

    def _run_board_check_and_arrange_slice(
        self,
        *,
        budget: PrepSliceBudget,
        allow_active_inspect: bool = True,
    ) -> bool:
        """Step 4b：游标轮转棋盘逐格检查与有界整理（纠错格优先 0 详情空位/安全中转，最多 1 次核名）。"""
        if not self._is_preparation_mode() or self._is_shop_open():
            return False
        if budget.wall_exhausted():
            return False
        slots = self._sync_board_slots_with_visual_scan()
        if not slots:
            return False
        if bool(hasattr(self, '_is_boss_challenge_round') and self._is_boss_challenge_round()):
            return False

        min_action_s = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
        slots_table = self._board_slots_table()
        round_state = self._ensure_prep_goldfish_round_state()
        hand_cards = self._frame_card_scan('card')
        hand_lineup_names = {c['name'] for c in hand_cards if c.get('name') in self.shikigami_deploy_positions}
        todo_names = set(getattr(self, '_displaced_lineup_todos', {}) or {})
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        ineligible_names = (
            self._candidate_deploy_eligibility_exclusions(deployed_names, None)
            | set(self._get_pending_deploys().keys())
            | round_state['deploy_deferred_names']
        )
        needed_names = (hand_lineup_names - ineligible_names) | (todo_names - ineligible_names)
        acted_any = False

        # 1) 优先无需详情的已知错位阵容格归位（空位直移 -> 安全空位中转 -> 非阵容确认格清理）
        for src in range(1, 13):
            if budget.wall_exhausted() or not self._is_preparation_mode() or self._is_shop_open():
                return acted_any
            rec = slots_table[src]
            if not rec.get('valid') or rec.get('kind') != 'lineup' or rec.get('satisfies_config'):
                continue
            ident = rec.get('identity')
            if not ident or ident not in self.shikigami_deploy_positions:
                continue
            dst = int(self.shikigami_deploy_positions[ident])
            if dst == src or self._is_placed_goldfish_protected_slot(dst):
                continue
            dst_rec = slots_table[dst]
            # 若配置目标位已存在更高/同星或共配单位，则保持不破坏
            if dst_rec.get('valid') and dst_rec.get('identity') in self._configured_names_at_slot(dst):
                dst_star = dst_rec.get('star')
                src_star = rec.get('star')
                if dst_rec.get('identity') != ident or (
                    dst_star is not None and src_star is not None and dst_star >= src_star
                ):
                    continue
            can_act, _ = budget.can_start_action(self._safe_read_remaining_time(), min_remaining=min_action_s)
            if not can_act:
                return acted_any
            dst_state = self._board_set_state(dst)
            if dst_state == 'empty':
                if self._move_board_unit(src, dst, name=ident):
                    budget.actions_done += 1
                    acted_any = True
                continue
            if dst_state == 'occupied' and dst_rec.get('valid') and dst_rec.get('kind') in ('lineup', 'non_lineup'):
                # 寻找安全过渡空位（非保护金鱼格，优先未配置阵容格）
                empty_candidates = [
                    e
                    for e in range(1, 13)
                    if e not in (src, dst)
                    and not self._is_placed_goldfish_protected_slot(e)
                    and self._board_set_state(e) == 'empty'
                ]
                empty_candidates.sort(key=lambda e: (1 if self._configured_names_at_slot(e) else 0, e))
                if empty_candidates:
                    transit = empty_candidates[0]
                    if self._move_board_unit(dst, transit, name=dst_rec.get('identity'), source_tag='board_arrange_transit'):
                        budget.actions_done += 1
                        acted_any = True
                        can_act_2, _ = budget.can_start_action(self._safe_read_remaining_time(), min_remaining=min_action_s)
                        if can_act_2 and self._move_board_unit(src, dst, name=ident):
                            budget.actions_done += 1
                        return acted_any
                elif dst_rec.get('kind') == 'non_lineup' and self._hand_capacity_count() < 10:
                    recalled = self._recall_one_system_board_card(
                        preferred_set_index=dst,
                        candidate_positions=(dst,),
                        raise_on_failure=False,
                    )
                    if recalled == dst:
                        budget.actions_done += 1
                        acted_any = True
                        can_act_2, _ = budget.can_start_action(self._safe_read_remaining_time(), min_remaining=min_action_s)
                        if can_act_2 and self._move_board_unit(src, dst, name=ident):
                            budget.actions_done += 1
                        return acted_any

        # 2) 已确认非阵容格与受阻重复副本让位：只有确实存在可补阵容卡且 hand < 10 时回收并立即重扫部署
        if needed_names and self._hand_capacity_count() < 10:
            for s in range(1, 13):
                if budget.wall_exhausted() or not self._is_preparation_mode() or self._is_shop_open():
                    return acted_any
                rec = slots_table[s]
                if not rec.get('valid') or rec.get('kind') != 'non_lineup':
                    continue
                if self._is_placed_goldfish_protected_slot(s):
                    continue
                can_act, _ = budget.can_start_action(self._safe_read_remaining_time(), min_remaining=min_action_s)
                if not can_act:
                    return acted_any
                # 优先存在本位配置可上卡者
                slot_cfgs = self._configured_names_at_slot(s)
                recalled = self._recall_one_system_board_card(
                    preferred_set_index=s,
                    candidate_positions=(s,),
                    raise_on_failure=False,
                )
                if recalled == s:
                    budget.actions_done += 1
                    acted_any = True
                    self.screenshot()
                    target_deploy_pool = (slot_cfgs & needed_names) or needed_names
                    self.deploy_shikigami_from_hand(
                        run_regular_goldfish=False,
                        direct_only=True,
                        reconcile_pending=False,
                        budget=budget,
                        candidate_whitelist=target_deploy_pool,
                    )
                    return acted_any

            # 仅当无 non_lineup 可收且存在受阻待补卡时，允许已确认可回收重复阵容副本让位。
            min_dup_rem = int(
                getattr(
                    self,
                    'DUPLICATE_RECALL_MIN_REMAINING',
                    getattr(self, 'GOLDFISH_BLOCKED_KNOWN_MOVE_MIN_REMAINING', 8),
                )
            )
            rem_dup = self._safe_read_remaining_time()
            can_dup_act, _ = budget.can_start_action(rem_dup, min_remaining=min_dup_rem)
            if can_dup_act:
                cap_state = self._classify_lineup_capacity_state(self._read_lineup_capacity_status())
                blocked_target_slots = [
                    int(self.shikigami_deploy_positions[n])
                    for n in sorted(needed_names)
                    if n in self.shikigami_deploy_positions
                ]
                dup_plan = None
                for t_slot in blocked_target_slots:
                    verdict = self._is_recallable_duplicate_slot(t_slot)
                    if verdict['recallable']:
                        dup_plan = {'slot': t_slot, **verdict}
                        break
                if dup_plan is None and cap_state == 'full':
                    dup_plan = self._find_verified_duplicate_recall_slot()
                if dup_plan is not None:
                    dup_slot = int(dup_plan['slot'])
                    slot_cfgs = self._configured_names_at_slot(dup_slot)
                    target_deploy_pool = (slot_cfgs & needed_names) or needed_names
                    recalled = self._recall_one_system_board_card(
                        preferred_set_index=dup_slot,
                        candidate_positions=(dup_slot,),
                        raise_on_failure=False,
                        allow_verified_duplicate=True,
                    )
                    if recalled == dup_slot:
                        budget.actions_done += 1
                        acted_any = True
                        self.screenshot()
                        can_follow, _ = budget.can_start_action(
                            self._safe_read_remaining_time(),
                            min_remaining=min_action_s,
                        )
                        if can_follow:
                            self.deploy_shikigami_from_hand(
                                run_regular_goldfish=False,
                                direct_only=True,
                                reconcile_pending=False,
                                budget=budget,
                                candidate_whitelist=target_deploy_pool,
                            )
                        else:
                            for todo_name in sorted(target_deploy_pool):
                                dst = self.shikigami_deploy_positions.get(todo_name)
                                if dst is not None:
                                    self._record_await_deploy_todo(
                                        todo_name,
                                        int(dst),
                                        reason='insufficient_time_after_duplicate_recall',
                                        recall_slot=dup_slot,
                                    )
                        return acted_any

        # 3) 游标轮转主动详情检查（仅在未占用本片详情配额且显式允许主动巡检时触发至多 1 次）
        if not allow_active_inspect or budget.inspects_used >= 1:
            return acted_any
        remaining = self._safe_read_remaining_time()
        can_insp, _ = budget.can_start_inspect(
            remaining,
            min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
            min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
        )
        if not can_insp:
            return acted_any

        cursor = int(getattr(self, '_board_check_cursor', 1) or 1)
        if not 1 <= cursor <= 12:
            cursor = 1
        rotated_slots = [((cursor - 1 + offset) % 12) + 1 for offset in range(12)]
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        reverify_rounds = int(getattr(self, 'BOARD_SLOT_REVERIFY_ROUNDS', 4))
        cur_round = getattr(self, '_current_round_no', None)

        inspected_slots = round_state['inspected_slots']
        cooldown_slots = round_state.get('slot_inspect_cooldown', set())
        blocked_target_slots = {
            int(self.shikigami_deploy_positions[n])
            for n in needed_names
            if n in self.shikigami_deploy_positions
        }

        def _inspect_priority(slot_id: int) -> tuple[int, int, int] | None:
            rec = slots_table[slot_id]
            vis_state = slots[slot_id - 1].get('state', 'unknown')
            if vis_state != 'occupied':
                return None
            if slot_id in cooldown_slots:
                return None
            # P2-1：穿戴连败复核与合卡疑义需越过“仍 valid 且 satisfies_config”提前返回，仍受占格/冷却/预算保护。
            if rec.get('stale_reason') == 'equip_failed_needs_reverify' or rec.get('suspect_merge'):
                return (0, 0, rotated_slots.index(slot_id))
            if rec.get('valid') and rec.get('satisfies_config'):
                v_round = rec.get('verified_round')
                if (
                    cur_round is not None
                    and v_round is not None
                    and (int(cur_round) - int(v_round)) >= reverify_rounds
                    and slot_id not in inspected_slots
                ):
                    return (5, 0, rotated_slots.index(slot_id))
                return None
            if slot_id in inspected_slots:
                return None
            if slot_id in blocked_target_slots and not rec.get('valid'):
                return (1, 0, rotated_slots.index(slot_id))
            cfgs = self._configured_names_at_slot(slot_id)
            if cfgs and not rec.get('valid'):
                min_w = min(int(strategy_shikigami[n].get('deploy_weight', 1)) for n in cfgs)
                return (2, min_w, rotated_slots.index(slot_id))
            if not rec.get('valid'):
                return (3, 0, rotated_slots.index(slot_id))
            return None

        inspect_candidates = []
        for s in rotated_slots:
            prio = _inspect_priority(s)
            if prio is not None:
                inspect_candidates.append((prio, s))
        if not inspect_candidates:
            return acted_any

        inspect_candidates.sort(key=lambda item: item[0])
        _, chosen_slot = inspect_candidates[0]
        inspected_slots.add(chosen_slot)
        budget.consume_inspect()
        inspection = self._inspect_board_set_shikigami(chosen_slot, max_attempts=1)
        self._board_check_cursor = (chosen_slot % 12) + 1
        if inspection['opened']:
            round_state['inspected_slot_results'][chosen_slot] = inspection['name']
        if not inspection['opened'] or inspection['name'] is None:
            cooldown_slots.add(chosen_slot)
            return acted_any

        budget.actions_done += 1
        acted_any = True
        obs = inspection['name']
        # 新确认的身份若是错位阵容卡且其配置位确认空且预算允许，立即顺手 0 详情直移归位！
        if obs in self.shikigami_deploy_positions:
            dst = int(self.shikigami_deploy_positions[obs])
            if (
                dst != chosen_slot
                and not self._is_placed_goldfish_protected_slot(dst)
                and self._board_set_state(dst) == 'empty'
            ):
                can_move, _ = budget.can_start_action(self._safe_read_remaining_time(), min_remaining=min_action_s)
                if can_move and self._move_board_unit(chosen_slot, dst, name=obs):
                    budget.actions_done += 1
        return acted_any

    def _can_direct_deploy_lineup_card(
        self,
        name: str,
        capacity: dict | None,
    ) -> bool:
        """配置目标格确认空着、非已站定金鱼格且现有人口判断未满时返回 True。"""
        if capacity is not None and (
            bool(capacity.get('full'))
            or self._classify_lineup_capacity_state(capacity) == 'full'
        ):
            return False
        set_index = self.shikigami_deploy_positions.get(name)
        if set_index is None:
            return False
        if self._is_placed_goldfish_protected_slot(int(set_index)):
            return False
        return self._board_set_state(int(set_index)) == 'empty'

    def _select_next_deploy_candidate(
        self,
        excluded_names: set[str],
        capacity: dict | None,
    ) -> tuple[dict | None, bool]:
        """先从空位优先上阵的阵容牌中按高星+原权重选牌；无空位直上牌时再选其余候选。"""
        candidate_pool = set(self.shikigami_deploy_positions) - set(excluded_names)
        if not candidate_pool:
            return None, False

        direct_names = {
            name
            for name in candidate_pool
            if self._can_direct_deploy_lineup_card(name, capacity)
        }
        if not direct_names:
            return (
                self._find_best_shikigami_hand_card(
                    excluded_names=excluded_names,
                ),
                False,
            )

        if direct_names == candidate_pool:
            candidate = self._find_best_shikigami_hand_card(
                excluded_names=excluded_names,
            )
            return (
                candidate,
                bool(candidate is not None and candidate['name'] in direct_names),
            )

        direct_candidate = self._find_best_shikigami_hand_card(
            excluded_names=set(excluded_names) | (candidate_pool - direct_names),
        )
        if direct_candidate is not None:
            return direct_candidate, direct_candidate['name'] in direct_names

        fallback_candidate = self._find_best_shikigami_hand_card(
            excluded_names=set(excluded_names) | direct_names,
        )
        if fallback_candidate is not None:
            return fallback_candidate, fallback_candidate['name'] in direct_names
        return None, False

    def _candidate_deploy_eligibility_exclusions(
        self,
        deployed_names: set[str],
        candidate_whitelist: set[str] | None,
    ) -> set[str]:
        """计算因场上已确认满意/保护而应跳过的式神集合（允许高星升级和错位纠位进入候选）。"""
        all_lineup = set(self.shikigami_deploy_positions)
        excluded: set[str] = set()
        if candidate_whitelist is not None:
            excluded |= (all_lineup - set(candidate_whitelist))

        slots_table = self._board_slots_table()
        hand_snap = self._snapshot_lineup_hand_cards()

        for unit_name in deployed_names:
            if unit_name not in all_lineup:
                continue
            target_slot = int(self.shikigami_deploy_positions[unit_name])
            rec_at_target = slots_table[target_slot]
            # 确认已站在目标配置位的同名式神：仅当手牌有确定更高星且无已穿装备风险时才放行，否则跳过。
            if rec_at_target.get('valid') and rec_at_target.get('identity') == unit_name:
                stars = (hand_snap.get(unit_name) or {}).get('stars')
                best_hand_star = max(stars) if stars else None
                board_star = rec_at_target.get('star')
                if (
                    best_hand_star in (1, 2, 3)
                    and board_star in (1, 2, 3)
                    and int(best_hand_star) > int(board_star)
                    and not any(item is not None for item in self._shikigami_attributes(unit_name))
                ):
                    continue
                excluded.add(unit_name)
                continue
            # 若格级记录中该式神只存在错位格（非 target_slot），允许候选入池以便先行移动/比较；
            other_valid = [
                s
                for s in range(1, 13)
                if s != target_slot
                and slots_table[s].get('valid')
                and slots_table[s].get('kind') == 'lineup'
                and slots_table[s].get('identity') == unit_name
            ]
            if other_valid:
                continue
            excluded.add(unit_name)
        return excluded

    def deploy_shikigami_from_hand(
        self,
        *,
        run_regular_goldfish: bool = False,
        direct_only: bool = False,
        reconcile_pending: bool = True,
        budget: PrepSliceBudget | None = None,
        candidate_whitelist: set[str] | None = None,
    ) -> list[str]:
        """关闭商店后按星级比较、错位优先纠位与共享预算上阵手牌阵容卡。"""
        self._last_deploy_stopped_for_direct_only = False
        if not self._is_preparation_mode():
            logger.debug(
                'Skip Chess shikigami deployment: preparation was interrupted '
                'or has ended'
            )
            return []
        if not self._ensure_shop_closed():
            logger.warning(
                'Skip Chess shikigami deployment: shop could not be closed'
            )
            return []
        if self._is_shop_open():
            logger.warning(
                'Skip Chess shikigami deployment: shop is still visible '
                'after close confirmation'
            )
            return []
        if getattr(self, '_chess_deploy_needs_refresh', False):
            # 上轮局部上阵或回收结果不明时，先重新截图后再扫手牌。
            self.screenshot()
            self._chess_deploy_needs_refresh = False
        self._last_system_recall_outcome = None

        round_state = self._ensure_prep_goldfish_round_state()
        # 入口先零点击清理已确认上阵、未消耗旧 pending 与回弹可恢复记录。
        self._cleanup_nonblocking_pending_deploys()
        if direct_only and self._has_reconcilable_pending_deploys(round_state):
            # 存在已消耗/疑似合卡跨回合待核实且本轮配额尚未使用时，提前找鱼后再进入 direct_only=False 核实。
            self._last_deploy_stopped_for_direct_only = True

        deployed: list[str] = []
        deployed_names = set(getattr(self, '_board_lineup_names', set()))
        global_interrupted = False
        slots_table = self._board_slots_table()
        slice_deferred: set[str] = set()

        for _ in range(self.HAND_DEPLOY_SAFETY_LIMIT):
            if budget is not None and budget.wall_exhausted():
                budget.reason_stopped = budget.reason_stopped or 'slice_wall_exhausted'
                break
            if not self._is_preparation_mode():
                logger.debug(
                    'Stop deploying Chess hand cards: '
                    'mode is no longer preparation'
                )
                global_interrupted = True
                break
            if not self._ensure_shop_closed() or self._is_shop_open():
                logger.warning(
                    'Stop deploying Chess hand cards: shop reopened or '
                    'could not be confirmed closed'
                )
                global_interrupted = True
                break

            capacity = self._read_lineup_capacity_status()
            if capacity is None:
                logger.warning(
                    'Chess lineup capacity unavailable (level OCR failed); '
                    'allow direct deploy attempt and block system recall'
                )

            pending_blocked = set(self._get_pending_deploys().keys())
            direct_done = round_state['deploy_direct_attempted_names']
            recovery_queue = round_state['deploy_recovery_queue']
            recovery_done = round_state['deploy_recovery_attempted_names']
            round_deferred = round_state['deploy_deferred_names']
            deployed_names = set(getattr(self, '_board_lineup_names', set()))
            lineup_exclusions = self._candidate_deploy_eligibility_exclusions(
                deployed_names,
                candidate_whitelist,
            )

            if direct_only:
                excluded_names = (
                    lineup_exclusions
                    | pending_blocked
                    | round_deferred
                    | slice_deferred
                    | direct_done
                )
            else:
                excluded_names = (
                    lineup_exclusions
                    | pending_blocked
                    | round_deferred
                    | slice_deferred
                    | recovery_done
                    | (direct_done - set(recovery_queue.keys()))
                )

            candidate, direct_deploy = self._select_next_deploy_candidate(
                excluded_names,
                capacity,
            )
            if candidate is None or candidate['name'] in excluded_names:
                logger.info(
                    'Stop deploying Chess hand cards: no deployable lineup '
                    'hand card candidate'
                )
                break

            name = candidate['name']
            cand_star = candidate.get('star')
            set_index = int(self.shikigami_deploy_positions[name])
            logger.info(
                f'Chess deploy candidate: '
                f'{self._shikigami_display_name(name)}, '
                f'star={cand_star}, '
                f'weight={candidate.get("deploy_weight", 1)}, '
                f'direct={direct_deploy}, '
                f'score={candidate["score"]:.3f}, '
                f'position={candidate["position"]}'
            )

            rec_at_target = slots_table[set_index]
            expect_replace = False

            # A) 已在场但位于错误格 S != target_slot：优先纠位，不重复把手牌合星副本上成第二只。
            misplaced_slots = [
                s
                for s in range(1, 13)
                if s != set_index
                and slots_table[s].get('valid')
                and slots_table[s].get('kind') == 'lineup'
                and slots_table[s].get('identity') == name
            ]
            if misplaced_slots and not (rec_at_target.get('valid') and rec_at_target.get('identity') == name):
                best_other = max(
                    misplaced_slots,
                    key=lambda s: (
                        int(slots_table[s]['star']) if slots_table[s].get('star') in (1, 2, 3) else 0,
                        -s,
                    ),
                )
                other_star = slots_table[best_other].get('star')
                if (
                    self._board_set_state(set_index) == 'empty'
                    and not self._is_placed_goldfish_protected_slot(set_index)
                    and (
                        budget is None
                        or budget.can_start_action(
                            self._safe_read_remaining_time(),
                            min_remaining=int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3)),
                        )[0]
                    )
                ):
                    if self._move_board_unit(best_other, set_index, name=name):
                        if budget is not None:
                            budget.actions_done += 1
                        self.screenshot()
                        continue
                if other_star in (1, 2, 3) and cand_star in (1, 2, 3) and int(other_star) >= int(cand_star):
                    logger.info(
                        f'Defer duplicate Chess card {name}: board copy at set {best_other} '
                        f'(star={other_star}) >= candidate star={cand_star}; wait board arrange'
                    )
                    slice_deferred.add(name)
                    continue
                if other_star not in (1, 2, 3) or cand_star not in (1, 2, 3):
                    logger.info(
                        f'Defer Chess card {name} compare with misplaced set {best_other}: '
                        f'star unreadable (board={other_star}, hand={cand_star})'
                    )
                    slice_deferred.add(name)
                    continue

            # 前置状态核验：已占用且缓存失效（或星级发生异动）时，先有界核名再决定是否拖动。
            target_state_now = self._board_set_state(set_index)
            live_board_star = self._board_set_star(set_index) if target_state_now == 'occupied' else None
            if (
                target_state_now == 'occupied'
                and self._is_board_slot_cache_valid(set_index)
                and rec_at_target.get('source') != 'legacy_seed'
                and rec_at_target.get('star') in (1, 2, 3)
                and live_board_star in (1, 2, 3)
                and int(live_board_star) != int(rec_at_target['star'])
            ):
                self._invalidate_board_slot(
                    set_index,
                    'board_star_changed_before_deploy',
                    clear_identity=False,
                )
                rec_at_target = slots_table[set_index]

            if target_state_now == 'occupied' and not self._is_board_slot_cache_valid(set_index):
                # P2-2：direct_only 阶段不对未验证占用格提前点详情或消耗核名预算，直接暂缓并继续其他空位候选。
                if direct_only:
                    self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer direct-only Chess deploy {name} -> occupied set {set_index} '
                        'with invalid cache: skip inspect until arrange/non-direct phase'
                    )
                    continue
                if set_index in round_state['inspected_slots']:
                    if direct_only:
                        self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer unverified occupied-slot deploy {name} -> set {set_index}: '
                        'slot already inspected this round with invalid cache'
                    )
                    continue
                rem_pre_insp = self._safe_read_remaining_time()
                if budget is not None:
                    can_insp, insp_reason = budget.can_start_inspect(
                        rem_pre_insp,
                        min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                        min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
                    )
                else:
                    min_insp = int(getattr(self, 'GOLDFISH_SINGLE_INSPECT_MIN_REMAINING', 6))
                    can_insp = rem_pre_insp is None or rem_pre_insp >= min_insp
                    insp_reason = 'ok' if can_insp else 'insufficient_time_for_inspect'
                if not can_insp:
                    if direct_only:
                        self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer unverified occupied-slot deploy {name} -> set {set_index} '
                        f'without drag: {insp_reason}'
                    )
                    continue
                if budget is not None:
                    budget.consume_inspect()
                round_state['inspected_slots'].add(set_index)
                pre_inspect = self._inspect_board_set_shikigami(set_index, max_attempts=1)
                if pre_inspect.get('opened'):
                    round_state['inspected_slot_results'][set_index] = pre_inspect.get('name')
                refreshed_star = self._board_set_star(set_index)
                self._record_slot_inspection_result(
                    set_index,
                    pre_inspect,
                    star=refreshed_star,
                )
                rec_at_target = slots_table[set_index]
                target_state_now = self._board_set_state(set_index)
                if target_state_now == 'empty':
                    self._invalidate_board_slot(set_index, 'empty_confirmed', clear_identity=True)
                    rec_at_target = slots_table[set_index]
                elif (
                    not pre_inspect.get('opened')
                    or pre_inspect.get('name') is None
                    or not self._is_board_slot_cache_valid(set_index)
                ):
                    slice_deferred.add(name)
                    logger.warning(
                        f'Defer occupied-slot deploy {name} -> set {set_index} '
                        f'after pre-drag inspect failed: reason={pre_inspect.get("reason")}'
                    )
                    continue

            # B) 同位多式神配置共享：若目标格已被同位其他配置式神合法站定（如流火 7 号位），跳过防互顶。
            if (
                rec_at_target.get('valid')
                and rec_at_target.get('identity') in self._configured_names_at_slot(set_index)
                and rec_at_target.get('identity') != name
            ):
                logger.info(
                    f'Defer Chess deploy for co-configured slot {set_index}: '
                    f'already satisfied by {rec_at_target.get("identity")}'
                )
                slice_deferred.add(name)
                continue

            # C) 目标格已是有效同名式神：逐星级对比 + 已穿装备低星保护；任一星级未知均暂缓，不按 1 星猜测。
            if rec_at_target.get('valid') and rec_at_target.get('identity') == name:
                if rec_at_target.get('source') == 'legacy_seed':
                    board_star = rec_at_target.get('star') or self._board_set_star(set_index)
                else:
                    live_star = self._board_set_star(set_index)
                    board_star = live_star if live_star in (1, 2, 3) else None
                if cand_star not in (1, 2, 3) or board_star not in (1, 2, 3):
                    logger.info(
                        f'Defer Chess same-name comparison for {name} at set {set_index}: '
                        f'star unreadable (board={board_star}, hand={cand_star})'
                    )
                    slice_deferred.add(name)
                    continue
                if int(board_star) >= int(cand_star):
                    slice_deferred.add(name)
                    continue
                if any(item is not None for item in self._shikigami_attributes(name)):
                    logger.warning(
                        f'Defer Chess higher-star replacement for equipped unit {name} at set {set_index}: '
                        'no reliable evidence on equipment preservation yet'
                    )
                    slice_deferred.add(name)
                    continue
                expect_replace = True

            # D) 切片预算模式下：满手牌 >=10 时跳过非空替换/回收；空格仍允许直接尝试部署。
            target_state_now = self._board_set_state(set_index)
            if (
                budget is not None
                and target_state_now == 'occupied'
                and not expect_replace
                and self._hand_capacity_count() >= 10
            ):
                slice_deferred.add(name)
                logger.info(
                    f'Defer Chess deploy on occupied slot {set_index} at full hand (10/10) '
                    f'for {name}; yield to equipment'
                )
                continue

            # D2) 已知目标格占着其他错位非可回收重复的阵容卡：direct_only 阶段禁止直接覆盖顶回，暂缓交由后续阶段整理；
            #     非 direct_only 阶段在其配置目标格确认空时先 0 详情挪走腾空。
            if (
                target_state_now == 'occupied'
                and not expect_replace
                and rec_at_target.get('valid')
                and rec_at_target.get('kind') == 'lineup'
                and rec_at_target.get('identity') not in (None, name)
                and not self._is_recallable_duplicate_slot(set_index)['recallable']
            ):
                if direct_only:
                    self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer direct-only Chess deploy {name} -> set {set_index}: '
                        f'blocked by misplaced lineup unit {rec_at_target.get("identity")}'
                    )
                    continue
                other_ident = rec_at_target['identity']
                other_dst = self.shikigami_deploy_positions.get(other_ident)
                if (
                    other_dst is not None
                    and int(other_dst) != set_index
                    and not self._is_placed_goldfish_protected_slot(int(other_dst))
                    and self._board_set_state(int(other_dst)) == 'empty'
                    and (
                        budget is None
                        or budget.can_start_action(
                            self._safe_read_remaining_time(),
                            min_remaining=int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3)),
                        )[0]
                    )
                ):
                    if self._move_board_unit(set_index, int(other_dst), name=other_ident):
                        if budget is not None:
                            budget.actions_done += 1
                        self.screenshot()
                        continue

            # E) 受阻与人口满恢复：占用可回收占位者 / 空或局部 unknown 但可靠人口已满 / 目标 unknown 有界核实，禁止盲拖。
            cap_evidence_state = self._classify_lineup_capacity_state(capacity)
            pop_blocked = cap_evidence_state == 'full'
            boss_round = bool(
                hasattr(self, '_is_boss_challenge_round') and self._is_boss_challenge_round()
            )
            direct_recall_plan: dict[str, Any] | None = None
            todo_prefix = 'population_recall'

            if target_state_now == 'occupied' and not expect_replace:
                dup_verdict = self._is_recallable_duplicate_slot(set_index)
                if dup_verdict['recallable']:
                    direct_recall_plan = {'slot': set_index, **dup_verdict, 'is_duplicate': True}
                    todo_prefix = 'duplicate_recall'
                elif (
                    rec_at_target.get('valid')
                    and rec_at_target.get('kind') == 'non_lineup'
                    and not self._is_placed_goldfish_protected_slot(set_index)
                ):
                    direct_recall_plan = {
                        'slot': set_index,
                        'name': rec_at_target.get('identity'),
                        'is_duplicate': False,
                    }

            if direct_recall_plan is not None:
                if direct_only:
                    self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer direct-only Chess deploy {name} -> set {set_index}: '
                        f'blocked by verified occupant {direct_recall_plan.get("name")} at set {direct_recall_plan["slot"]}'
                    )
                    continue
                relieved = self._execute_verified_blocker_recall_and_rescan(
                    name,
                    set_index,
                    direct_recall_plan,
                    budget=budget,
                    slots_table=slots_table,
                    todo_reason_prefix=todo_prefix,
                )
                if relieved['status'] == 'stop':
                    global_interrupted = True
                    break
                if relieved['status'] != 'ready':
                    slice_deferred.add(name)
                    continue
                if relieved['target_state_now'] != 'empty':
                    self._record_await_deploy_todo(
                        name,
                        set_index,
                        reason=f'target_{relieved["target_state_now"]}_after_recall',
                        recall_slot=relieved['recall_slot'],
                    )
                    slice_deferred.add(name)
                    continue
                candidate = relieved['candidate']
                cand_star = candidate.get('star')
                rec_at_target = relieved['rec_at_target']
                target_state_now = relieved['target_state_now']
            elif (
                pop_blocked
                and (
                    target_state_now == 'empty'
                    or (target_state_now == 'unknown' and not self._is_board_slot_cache_valid(set_index))
                )
            ):
                if direct_only:
                    self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer direct-only Chess deploy {name} -> set {set_index}: '
                        f'capacity full (target_state={target_state_now})'
                    )
                    continue
                if self._hand_capacity_count() >= 10:
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer population relief recall for {name} -> set {set_index}: '
                        'hand full (10/10), yield to cleanup'
                    )
                    continue
                recall_plan = self._find_verified_arakawa_recall_slot(
                    set_index,
                    target_state=target_state_now,
                    budget=budget,
                    allow_population_relief=True,
                )
                if recall_plan['status'] == 'stop':
                    global_interrupted = True
                    break
                if recall_plan['status'] != 'ready':
                    self._record_await_deploy_todo(
                        name,
                        set_index,
                        reason=f'population_blocked:{recall_plan["reason"]}',
                    )
                    slice_deferred.add(name)
                    logger.info(
                        f'Defer full-capacity Chess deploy {name} -> set {set_index} without blind drag: '
                        f'{recall_plan["reason"]}'
                    )
                    continue
                relieved = self._execute_verified_blocker_recall_and_rescan(
                    name,
                    set_index,
                    recall_plan,
                    budget=budget,
                    slots_table=slots_table,
                    todo_reason_prefix='duplicate_recall' if recall_plan.get('is_duplicate') else 'population_recall',
                )
                if relieved['status'] == 'stop':
                    global_interrupted = True
                    break
                if relieved['status'] != 'ready':
                    slice_deferred.add(name)
                    continue
                if relieved['target_state_now'] != 'empty':
                    self._record_await_deploy_todo(
                        name,
                        set_index,
                        reason=f'target_{relieved["target_state_now"]}_after_population_relief',
                        recall_slot=relieved['recall_slot'],
                    )
                    slice_deferred.add(name)
                    logger.info(
                        f'Record todo for {name} -> set {set_index}: '
                        f'target stays {relieved["target_state_now"]} after freeing slot {relieved["recall_slot"]}'
                    )
                    continue
                candidate = relieved['candidate']
                cand_star = candidate.get('star')
                rec_at_target = relieved['rec_at_target']
                target_state_now = relieved['target_state_now']
            elif target_state_now == 'unknown' and not self._is_board_slot_cache_valid(set_index):
                # 目标格处于 unknown 且人口未确认满：绝不当空格反复盲拖或盲目减员，仅做至多 1 次有界核查或存待办。
                if direct_only:
                    self._last_deploy_stopped_for_direct_only = True
                    slice_deferred.add(name)
                    continue
                cooldown_slots = round_state.get('slot_inspect_cooldown', set())
                can_check_unknown = (
                    not boss_round
                    and set_index not in round_state['inspected_slots']
                    and set_index not in cooldown_slots
                )
                did_reveal = False
                if can_check_unknown:
                    rem_unk = self._safe_read_remaining_time()
                    if budget is not None:
                        can_insp, unk_reason = budget.can_start_inspect(
                            rem_unk,
                            min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                            min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
                        )
                    else:
                        min_insp = int(getattr(self, 'GOLDFISH_SINGLE_INSPECT_MIN_REMAINING', 6))
                        can_insp = rem_unk is None or rem_unk >= min_insp
                        unk_reason = 'ok' if can_insp else 'insufficient_time_for_inspect'
                    if can_insp:
                        if budget is not None:
                            budget.consume_inspect()
                        round_state['inspected_slots'].add(set_index)
                        unk_inspect = self._inspect_board_set_shikigami(set_index, max_attempts=1)
                        if unk_inspect.get('opened'):
                            round_state['inspected_slot_results'][set_index] = unk_inspect.get('name')
                        self._record_slot_inspection_result(
                            set_index,
                            unk_inspect,
                            star=self._board_set_star(set_index),
                        )
                        if not unk_inspect.get('opened') or unk_inspect.get('name') is None:
                            round_state.setdefault('slot_inspect_cooldown', set()).add(set_index)
                        rec_at_target = slots_table[set_index]
                        target_state_now = self._board_set_state(set_index)
                        if target_state_now == 'empty':
                            self._invalidate_board_slot(set_index, 'empty_confirmed', clear_identity=True)
                            did_reveal = True
                        elif target_state_now == 'occupied' and self._is_board_slot_cache_valid(set_index):
                            did_reveal = True
                if did_reveal:
                    continue
                self._record_await_deploy_todo(
                    name,
                    set_index,
                    reason='target_state_unknown',
                )
                if boss_round or set_index in round_state['inspected_slots']:
                    round_deferred.add(name)
                else:
                    slice_deferred.add(name)
                logger.info(
                    f'Defer Chess deploy {name} -> unknown set {set_index} without blind drag'
                )
                continue

            goldfish_check = self._handle_known_goldfish_before_direct_deploy(
                candidate,
                set_index,
                round_state=round_state,
            )
            if goldfish_check['action'] == 'stop':
                break
            if goldfish_check['action'] in ('defer', 'defer_protected_goldfish'):
                round_deferred.add(name)
                continue
            if goldfish_check['action'] == 'rescan':
                continue

            try:
                if not direct_only and name in recovery_queue:
                    direct_result = recovery_queue.pop(name)
                    goldfish_baseline = self._goldfish_formation_baseline(name)
                    if (
                        direct_result.get('observed_name') == 'arakawa_goldfish'
                        and self._board_set_state(set_index) == 'empty'
                        and direct_result.get('hand_count_before', 0) > 0
                        and not direct_result.get('hand_consumed')
                        and self._lineup_hand_card_match_count(name) >= direct_result['hand_count_before']
                    ):
                        round_state['deploy_recovery_attempted_names'].add(name)
                        self.screenshot()
                        relocated = self._find_best_shikigami_hand_card(
                            excluded_names=(set(self.shikigami_deploy_positions) - {name}),
                        )
                        if relocated is not None and relocated['name'] == name:
                            goldfish_baseline = self._goldfish_formation_baseline(name)
                            direct_result = self._deploy_lineup_hand_card_direct(
                                name,
                                relocated['position'],
                                set_index,
                                budget=budget,
                                expect_replace=expect_replace,
                            )
                else:
                    # 在切片预算且 target 既被未知占用、又满员/无法继续核名时跳过无把握拖拽。
                    if (
                        budget is not None
                        and not rec_at_target.get('valid')
                        and target_state_now == 'occupied'
                        and not budget.can_start_inspect(
                            self._safe_read_remaining_time(),
                            min_before_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_BEFORE_EQUIP', 8)),
                            min_after_equip=int(getattr(self, 'PREP_ARRANGE_INSPECT_MIN_REMAINING_AFTER_EQUIP', 6)),
                        )[0]
                    ):
                        slice_deferred.add(name)
                        logger.info(
                            f'Defer unverified occupied-slot deploy {name} -> set {set_index}: '
                            f'slice inspect budget/time unavailable'
                        )
                        continue
                    direct_done.add(name)
                    goldfish_baseline = self._goldfish_formation_baseline(name)
                    direct_result = self._deploy_lineup_hand_card_direct(
                        name,
                        candidate['position'],
                        set_index,
                        budget=budget,
                        expect_replace=expect_replace,
                    )
            except GameStuckError as exc:
                logger.warning(
                    'Stop deploying Chess hand cards: board anchor missing '
                    f'while handling {name} at set {set_index}: {exc}'
                )
                global_interrupted = True
                break

            if (
                not direct_result['position_confirmed']
                and direct_result.get('status') == 'confirmed_not_deployed'
            ):
                if direct_only:
                    recovery_queue[name] = direct_result
                    self._last_deploy_stopped_for_direct_only = True
                    self._chess_deploy_needs_refresh = True
                    self.screenshot()
                    logger.info(
                        'Queue Chess confirmed-not-deployed card for post-goldfish recovery: '
                        f'card={name}, set={set_index}, reason={direct_result["reason"]}'
                    )
                    continue

                if name not in recovery_done and (budget is None or not budget.wall_exhausted()):
                    recovery_result = self._recover_after_confirmed_not_deployed(
                        name,
                        set_index,
                        direct_result,
                        capacity=capacity,
                        round_state=round_state,
                        budget=budget,
                    )
                    if recovery_result['status'] == 'stop':
                        global_interrupted = True
                        break
                    if recovery_result['status'] == 'ready':
                        relocated_candidate = recovery_result['candidate']
                        goldfish_baseline = self._goldfish_formation_baseline(name)
                        try:
                            direct_result = self._deploy_lineup_hand_card_direct(
                                name,
                                relocated_candidate['position'],
                                set_index,
                                budget=budget,
                                expect_replace=expect_replace,
                            )
                        except GameStuckError as exc:
                            logger.warning(
                                'Stop deploying Chess hand cards: board anchor missing '
                                f'during recovery retry for {name}: {exc}'
                            )
                            global_interrupted = True
                            break

            if not direct_result['position_confirmed']:
                global_stop = (
                    direct_result.get('reason')
                    in ('not_preparation', 'shop_not_closed', 'shop_open', 'anchor_missing')
                    or not self._is_preparation_mode()
                    or self._is_shop_open()
                )
                consumed_or_merged = bool(
                    direct_result.get('hand_consumed')
                    or direct_result.get('hand_star_upgraded')
                    or direct_result.get('board_star_upgraded')
                )
                if global_stop:
                    if consumed_or_merged:
                        self._record_pending_deploy(
                            name,
                            set_index,
                            direct_result,
                            status=direct_result.get('status', 'ambiguous'),
                            recovery_attempted=(name in recovery_done),
                        )
                    self._chess_deploy_needs_refresh = True
                    logger.warning(
                        'Stop Chess deploy pass on global interruption: '
                        f'card={name}, set={set_index}, reason={direct_result.get("reason")}'
                    )
                    global_interrupted = True
                    break

                # 回弹且最新稳态已证实未消耗/未合星：绝不写成永久 hand_consumed=True pending；
                # 仅以 hand_consumed=False 记录本轮结果元信息（切回合或清堵后自动解除），本轮不再重复直拖。
                if (
                    direct_result.get('status') == 'confirmed_not_deployed'
                    and not consumed_or_merged
                ):
                    round_deferred.add(name)
                    nonblocking_result = dict(direct_result)
                    nonblocking_result['hand_consumed'] = False
                    self._record_pending_deploy(
                        name,
                        set_index,
                        nonblocking_result,
                        status=direct_result.get('status', 'confirmed_not_deployed'),
                        recovery_attempted=(name in recovery_done),
                    )
                    self._chess_deploy_needs_refresh = True
                    self.screenshot()
                    continue

                self._record_pending_deploy(
                    name,
                    set_index,
                    direct_result,
                    status=direct_result.get('status', 'ambiguous'),
                    recovery_attempted=(name in recovery_done),
                )
                round_deferred.add(name)
                self._chess_deploy_needs_refresh = True
                logger.warning(
                    'Defer Chess card after unconfirmed deploy and continue remaining cards: '
                    f'card={name}, set={set_index}, status={direct_result.get("status")}, '
                    f'reason={direct_result.get("reason")}'
                )
                self.screenshot()
                continue

            self._clear_pending_deploy(name)
            recovery_queue.pop(name, None)
            self._register_confirmed_lineup_deploy(
                name,
                set_index,
                star=direct_result.get('board_star_after') or cand_star,
                goldfish_baseline=goldfish_baseline,
                trigger_hakuzosu=True,
            )
            if budget is not None:
                budget.actions_done += 1
            deployed.append(name)
            deployed_names = set(getattr(self, '_board_lineup_names', set()))
            # 若本次替换确认导致原有阵容式神回手，立刻在同切片共享预算内尝试处理回手归位链！
            if 'returned_to_hand' in (direct_result.get('displaced') or {}).values():
                chain_deployed = self._process_displaced_lineup_todos(budget=budget)
                if chain_deployed:
                    deployed.extend(chain_deployed)
                    deployed_names = set(getattr(self, '_board_lineup_names', set()))
        else:
            logger.warning(
                'Stop deploying Chess hand cards at safety limit '
                f'{self.HAND_DEPLOY_SAFETY_LIMIT}'
            )

        if direct_only:
            logger.info(
                'Chess initial direct deploy complete: '
                f'deployed={deployed}, '
                f'remaining_non_direct={self._last_deploy_stopped_for_direct_only}'
            )

        if (
            not global_interrupted
            and run_regular_goldfish
            and not direct_only
            and self._is_preparation_mode()
            and not self._is_shop_open()
        ):
            self._call_detect_pending_goldfish(context='deploy_tail', budget=budget)

        if (
            not global_interrupted
            and reconcile_pending
            and not direct_only
            and self._is_preparation_mode()
            and not self._is_shop_open()
        ):
            self._reconcile_pending_deploys_once(round_state, budget=budget)

        logger.debug(f'Chess hand deployment complete, deployed={deployed}')
        return deployed

    def _hand_card_detections(self) -> list[dict]:
        """Frame locates shikigami/emblem cards; souls retain existing matching."""
        template_rules = [rule for _, rule in self.soul_hand_rules]
        template_rules.append(self.hakuzosu_protect_rule)
        candidates = [(card['badge_score'], *card['roi']) for card in self._frame_card_scan('card') + self._frame_card_scan('emblem')]
        for rule in template_rules:
            matches = rule.match_all_any(
                self.device.image,
                roi=list(self.HAND_AREA),
                threshold=rule.threshold,
                nms_threshold=0.3,
                frame_id=self.device.image_frame_id,
            )
            for score, x, y, width, height in matches:
                candidates.append((score, x, y, width, height))

        # 多个素材可能在同一张卡上产生近邻命中；每个实际卡位只保留
        # 最高分结果。这里保留素材自身矩形，拖动时使用其中心即可。
        card_matches = []
        for candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
            _, x, y, width, height = candidate
            center_x = x + width // 2
            center_y = y + height // 2
            if any(
                abs(center_x - (kept[1] + kept[3] // 2)) <= 28
                and abs(center_y - (kept[2] + kept[4] // 2)) <= 40
                for kept in card_matches
            ):
                continue
            card_matches.append(candidate)

        detections = []
        for score, x, y, width, height in sorted(
            card_matches,
            key=lambda item: item[1],
        ):
            if width <= 0 or height <= 0:
                continue
            detection = {
                'roi': (x, y, width, height),
                'score': score,
            }
            detections.append(detection)
            logger.debug(
                f'Chess hand card template detected: score={score:.3f}, '
                f'roi={detection["roi"]}'
            )
        if not detections:
            logger.debug('Chess hand card templates found no cards')
        return detections

    def _hand_capacity_count(self) -> int:
        """容量只扫描式神/特殊卡锚点与御魂图片，不识别式神身份。"""
        image = self.device.image
        candidates = []
        for frame, kind in ((self.F_HAND_CARD, 'card'), (self.F_FETTER_BADGE, 'emblem')):
            x, y, w, h = frame.roi_back
            # 只扫描手牌顶部及下方，排除棋盘上的星级标志。
            top = max(y, self.HAND_AREA[1])
            region = image[top:y+h, x:x+w]
            bx, _, _, _ = frame.badge_references[0]
            cx, _, cw, _ = frame.roi_ranges[-1 if kind == 'card' else 1]
            offset = cx + cw/2 - bx
            if frame.badge_grayscale:
                region = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
            for front in self.frame_badges[kind]:
                if frame.badge_grayscale:
                    front = cv2.cvtColor(front, cv2.COLOR_RGB2GRAY)
                if region.shape[0] < front.shape[0] or region.shape[1] < front.shape[1]:
                    continue
                scores = cv2.matchTemplate(region, front, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(scores >= frame.threshold)
                candidates.extend((float(scores[py, px]), x+int(px)+offset) for py, px in zip(ys, xs))
        candidates.extend((item['score'], item['position'][0]) for item in self._soul_hand_cards())
        # 守护之印不占容量；不依赖当前阵容是否配置守护之印。
        x, y, w, h = self.HAND_AREA
        protect = self.hakuzosu_protect_rule.image
        region = image[y:y+h, x:x+w]
        protect_x = []
        if region.shape[0] >= protect.shape[0] and region.shape[1] >= protect.shape[1]:
            scores = cv2.matchTemplate(region, protect, cv2.TM_CCOEFF_NORMED)
            _, xs = np.where(scores >= self.hakuzosu_protect_rule.threshold)
            protect_x = [x+int(px)+protect.shape[1]/2 for px in xs]
        positions = []
        for _, center in sorted(candidates, reverse=True):
            if any(abs(center-x) <= 28 for x in protect_x):
                continue
            if not any(abs(center-x) <= 28 for x in positions):
                positions.append(center)
        logger.debug(f'Chess hand capacity: count={len(positions)}/10, positions={sorted(positions)}')
        return len(positions)

    def _hand_card_rois(self) -> list[tuple[int, int, int, int]]:
        """兼容只需要卡框的分类流程。"""
        return [item['roi'] for item in self._hand_card_detections()]

    def _hand_card_identity_count(
        self,
        card_type: str,
        name: str | None,
    ) -> int:
        """统计手牌中指定素材的命中张数，用于确认出售与装配确实生效。"""
        if card_type == 'shikigami' and name:
            return self._lineup_hand_card_match_count(name)
        if card_type == 'emblem' and name:
            return sum(card['name'] == name for card in self._frame_card_scan('emblem'))
        if card_type == 'soul' and name:
            return sum(card['name'] == name for card in self._soul_hand_cards())
        return len(self._hand_card_detections())

    def cleanup_non_lineup_hand_cards(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
        emergency: bool = False,
    ) -> list[tuple[int, int]]:
        """独立卖卡环节：循环出售纹章和非阵容卡，直到连续确认干净。"""
        if not emergency and self._is_early_round_layout():
            logger.debug(
                'Skip Chess hand cleanup: '
                'alternate layout means round 1-3'
            )
            return []

        sold = []
        failed_sale_attempts = {}
        clean_confirm_frames = 0
        strategy = self.get_lineup_strategy()
        logger.debug(
            'Chess hand cleanup lineup protection: '
            f'lineup={strategy["key"]}, '
            f'names={list(strategy["shikigami"].keys())}'
        )
        for cleanup_pass in range(1, self.HAND_CLEANUP_SAFETY_LIMIT + 1):
            self.close_shikigami_specifics_if_open()
            mode = self._read_chess_mode()
            if not self._is_hand_cleanup_allowed(allowed_modes):
                logger.debug(
                    'Stop cleaning Chess hand cards: '
                    f'mode={mode} is outside {allowed_modes}'
                )
                break

            # 先处理 Frame 已确认种类的纹章；图案未知的纹章留给下方保护。
            badge_target = self._find_badge_hand_card()
            if badge_target is not None:
                logger.info(
                    'Sell Chess card: '
                    f'text={badge_target["text"]}, '
                    f'position={badge_target["position"]}'
                )
                before = self._hand_card_identity_count(
                    'emblem', badge_target['name'],
                )
                self.sell_hand_card(badge_target['position'])
                if self._wait_hand_card_removed(
                    before,
                    lambda: self._hand_card_identity_count(
                        'emblem', badge_target['name'],
                    ),
                ):
                    sold.append(badge_target['position'])
                clean_confirm_frames = 0
                continue

            # 御魂图片可能与星级卡框同时命中。先独立识别御魂，避免
            # classify_hand_card 的固定尺寸模板漏检后将它当作 unknown 出售。
            soul_cards = self._soul_hand_cards()
            discover_cards = (
                self._discover_soul_hand_cards()
                + self._discover_badge_hand_cards()
            )
            sell_target = None
            for card_roi in self._hand_card_rois():
                card_x, _, card_width, _ = card_roi
                discover_card = next((
                    item
                    for item in discover_cards
                    if (
                        card_x - 8
                        <= item['position'][0]
                        <= card_x + card_width + 8
                    )
                ), None)
                if discover_card is not None:
                    logger.debug(
                        'Keep unused Chess discover card during cleanup: '
                        f'text={discover_card["text"]}, '
                        f'position={discover_card["position"]}'
                    )
                    continue
                soul = self._soul_match_in_card(card_roi, soul_cards)
                if soul is not None:
                    logger.debug(
                        'Keep Chess soul hand card during cleanup: '
                        f'name={soul["text"]}, score={soul["score"]:.3f}, '
                        f'position={soul["position"]}'
                    )
                    continue
                protect = self._hakuzosu_protect_match_in_card(card_roi)
                if protect is not None:
                    logger.debug(
                        'Keep Chess Hakuzosu protect card during cleanup: '
                        f'score={protect["score"]:.3f}, '
                        f'position={protect["position"]}'
                    )
                    continue
                result = self.classify_hand_card(card_roi)
                keep = (
                    (result.get('source') == 'frame' and result['type'] == 'unknown')
                    or result['type'] in ('soul', 'discovery', 'duplicator')
                    or (result['type'] == 'emblem' and self._keep_preferred_emblem(result['name']))
                    or (
                        result['type'] == 'shikigami'
                        and result['name'] in self.shikigami_deploy_positions
                    )
                )
                if keep:
                    continue

                sale_key = (result['type'], result['name'])
                if failed_sale_attempts.get(sale_key, 0) >= 2:
                    logger.debug(
                        'Skip repeatedly failed Chess sale target in this '
                        f'cleanup pass: type={result["type"]}, '
                        f'name={result["name"]}'
                    )
                    continue
                sell_target = result
                break
            if sell_target is None:
                clean_confirm_frames += 1
                if (
                    clean_confirm_frames
                    >= self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES
                ):
                    logger.debug(
                        'Chess hand cleanup confirmed clean: '
                        f'frames={clean_confirm_frames}'
                    )
                    break
                logger.debug(
                    'No sellable Chess hand card in current scan, '
                    'wait for layout and verify again: '
                    f'frame={clean_confirm_frames}/'
                    f'{self.HAND_CLEANUP_CLEAN_CONFIRM_FRAMES}'
                )
                self.screenshot()
                continue

            logger.info(
                f'Sell Chess card: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'position={sell_target["position"]}'
            )
            sale_key = (sell_target['type'], sell_target['name'])
            count_before = self._hand_card_identity_count(*sale_key)
            self.sell_hand_card(sell_target['position'])
            confirmed = self._wait_hand_card_removed(
                count_before,
                lambda: self._hand_card_identity_count(*sale_key),
            )
            count_after = self._hand_card_identity_count(*sale_key)
            if confirmed:
                sold.append(sell_target['position'])
                failed_sale_attempts.pop(sale_key, None)
                clean_confirm_frames = 0
                logger.info(
                    'Chess card sale confirmed: '
                    f'type={sell_target["type"]}, '
                    f'name={self._shikigami_display_name(sell_target["name"])}, '
                    f'count={count_before}->{count_after}'
                )
                continue

            failed_sale_attempts[sale_key] = (
                failed_sale_attempts.get(sale_key, 0) + 1
            )
            clean_confirm_frames = 0
            logger.warning(
                'Chess card sale not confirmed; do not register as sold: '
                f'type={sell_target["type"]}, '
                f'name={self._shikigami_display_name(sell_target["name"])}, '
                f'count={count_before}->{count_after}, '
                f'attempt={failed_sale_attempts[sale_key]}/2'
            )
        else:
            logger.warning(
                'Stop cleaning Chess hand cards at safety limit '
                f'{self.HAND_CLEANUP_SAFETY_LIMIT}'
            )

        logger.debug(f'Chess non-lineup hand cleanup complete, sold={sold}')
        return sold

    def _is_hand_cleanup_allowed(
        self,
        allowed_modes: tuple[str, ...] = ('战',),
    ) -> bool:
        """卖卡只在调用方指定阶段执行，阶段变化后立刻停止。"""
        return self._read_chess_mode() in allowed_modes

    def _protected_special_hand_x_positions(self) -> list[float]:
        """收集守护之印、发现卡与黄金复制术的横向位置，避免被当作普通装备出售。"""
        xs = []
        if callable(getattr(self, '_frame_card_scan', None)):
            xs.extend(
                float(card['position'][0])
                for card in (
                    self._discover_soul_hand_cards()
                    + self._discover_badge_hand_cards()
                    + self._golden_copy_hand_cards()
                )
            )
        if hasattr(self, 'hakuzosu_protect_rule'):
            rule = self.hakuzosu_protect_rule
            protect_img = rule.image
            x, y, w, h = self.HAND_AREA
            region = self.device.image[y:y + h, x:x + w]
            if (
                region.shape[0] >= protect_img.shape[0]
                and region.shape[1] >= protect_img.shape[1]
            ):
                scores = cv2.matchTemplate(
                    region, protect_img, cv2.TM_CCOEFF_NORMED,
                )
                _, match_xs = np.where(scores >= rule.threshold)
                xs.extend(
                    float(x + int(px) + protect_img.shape[1] / 2)
                    for px in match_xs
                )
        return xs

    def _select_next_sellable_equipment_for_cleanup(
        self,
        verified_names: set[str],
    ) -> dict | None:
        """选出一张当前无合法目标且超出配置预留的可出售装备，优先卖同名多余普通御魂。"""
        verified = self._verified_board_lineup_names(verified_names)
        special_xs = self._protected_special_hand_x_positions()
        soul_cards = [
            card
            for card in self._soul_hand_cards()
            if not any(
                abs(card['position'][0] - special_x) <= 28
                for special_x in special_xs
            )
        ]
        soul_counts = Counter(card['name'] for card in soul_cards)
        soul_reserve_counts, soul_reserve_owners = self._soul_hand_reserve_info(soul_cards)
        candidates = []

        for card in soul_cards:
            name = card['name']
            count = soul_counts[name]
            reserve_count = int(soul_reserve_counts.get(name, 0))
            reserve_owners = soul_reserve_owners.get(name, set())
            generic_targets = [
                entry
                for entry in self._soul_generic_target_entries(
                    name, card['category'], verified,
                )
                if entry[0] not in reserve_owners
            ]
            protected = reserve_count + len(generic_targets)
            if count <= protected:
                continue
            surplus = count - protected
            # 0=同名多余普通御魂，1=无合法目标/超预留纹章，2=单张无目标普通御魂。
            bucket = 0 if count >= 2 else 2
            candidates.append((
                (bucket, -surplus, -count, -card['position'][0]),
                {
                    'kind': 'soul',
                    'name': name,
                    'display_name': card.get(
                        'text', self.SOUL_DISPLAY_NAMES.get(name, name),
                    ),
                    'position': card['position'],
                    'count': count,
                    'reserve_count': reserve_count,
                    'protected_count': protected,
                    'surplus': surplus,
                    'reason': (
                        'duplicate_surplus_normal_soul'
                        if count >= 2
                        else 'no_valid_target_above_reserve'
                    ),
                },
            ))

        emblem_cards = self._recognized_emblem_hand_cards()
        emblem_counts = Counter(card['name'] for card in emblem_cards)
        for card in emblem_cards:
            name = card['name']
            count = emblem_counts[name]
            emblem_needing = self._emblem_preferred_needing_units(name)
            reserve_count = len(emblem_needing)
            emblem_needing_set = set(emblem_needing)
            generic_targets = [
                entry
                for entry in self._emblem_generic_target_entries(
                    name, verified,
                )
                if entry[0] not in emblem_needing_set
            ]
            protected = reserve_count + len(generic_targets)
            if count <= protected:
                continue
            surplus = count - protected
            candidates.append((
                (1, -surplus, -count, -card['position'][0]),
                {
                    'kind': 'emblem',
                    'name': name,
                    'display_name': name,
                    'position': card['position'],
                    'count': count,
                    'reserve_count': reserve_count,
                    'protected_count': protected,
                    'surplus': surplus,
                    'reason': 'emblem_no_target_above_reserve',
                },
            ))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _select_next_non_lineup_shikigami_for_cleanup(self) -> dict | None:
        """选出一张已识别的非阵容式神手牌；未知卡与特殊卡不入选。"""
        soul_cards = self._soul_hand_cards()
        discover_cards = (
            self._discover_soul_hand_cards()
            + self._discover_badge_hand_cards()
        )
        special_xs = self._protected_special_hand_x_positions()
        lineup_names = set(self.shikigami_deploy_positions)
        for card_roi in self._hand_card_rois():
            card_x, _, card_width, _ = card_roi
            if any(
                card_x - 8 <= item['position'][0] <= card_x + card_width + 8
                for item in discover_cards
            ):
                continue
            if self._soul_match_in_card(card_roi, soul_cards) is not None:
                continue
            if any(
                card_x - 8 <= special_x <= card_x + card_width + 8
                for special_x in special_xs
            ):
                continue
            if self._hakuzosu_protect_match_in_card(card_roi) is not None:
                continue
            result = self.classify_hand_card(card_roi)
            if (
                result.get('type') == 'shikigami'
                and result.get('name')
                and result['name'] not in lineup_names
            ):
                return {
                    'type': 'shikigami',
                    'name': result['name'],
                    'display_name': self._shikigami_display_name(
                        result['name']
                    ),
                    'position': result['position'],
                }
        return None

    def emergency_cleanup_hand(self) -> dict | None:
        """手牌满时逐张执行：备战可装先装 -> 卖无目标超预留装备 -> 卖非阵容式神；降到<=9即停。"""
        initial_mode = self._read_chess_mode()
        if (
            initial_mode not in ('备', '战')
            or self.appear(self.I_SELECT_GRIGRI)
        ):
            logger.warning(
                f'Cannot run emergency Chess hand cleanup in mode={initial_mode}'
            )
            return None
        if not self._ensure_shop_closed(allowed_modes=(initial_mode,)):
            logger.warning(
                'Cannot run emergency Chess hand cleanup: '
                'shop could not be closed'
            )
            return None

        self.screenshot()
        self.close_shikigami_specifics_if_open()
        if (
            self._read_chess_mode() != initial_mode
            or self.appear(self.I_SELECT_GRIGRI)
        ):
            logger.warning(
                'Stop emergency Chess hand cleanup: mode changed or grigri '
                'appeared after closing shop'
            )
            return None

        initial_hand_count = self._hand_capacity_count()
        equipped = []
        sold_equipment = []
        sold_non_lineup = []
        equip_attempts = {}
        logged_non_lineup_entry = False

        for _ in range(self.HAND_CLEANUP_SAFETY_LIMIT):
            self.close_shikigami_specifics_if_open()
            mode = self._read_chess_mode()
            if (
                mode != initial_mode
                or self.appear(self.I_SELECT_GRIGRI)
                or self._is_shop_open()
            ):
                logger.warning(
                    'Stop emergency Chess hand cleanup: phase or screen '
                    f'became unstable (mode={mode}, initial={initial_mode})'
                )
                return None

            current_count = self._hand_capacity_count()
            if current_count <= 9:
                logger.info(
                    'Chess full-hand cleanup reached purchase threshold: '
                    f'hand_capacity={initial_hand_count}->{current_count}/10'
                )
                break

            verified_board_names = self._verified_board_lineup_names()
            min_action_s = int(getattr(self, 'PREP_ACTION_MIN_REMAINING', 3))
            rem_now = self._safe_read_remaining_time()
            can_equip_now = (
                self._is_preparation_mode()
                and not self._is_shop_open()
                and bool(verified_board_names)
                and (rem_now is None or rem_now >= min_action_s)
            )
            if can_equip_now:
                action = self._select_next_equipment_action(
                    verified_board_names,
                    repeated_attempts=equip_attempts,
                )
                if action is not None:
                    step_equipped = self.equip_souls_from_hand(
                        verified_board_names,
                        max_actions=1,
                        include_special=False,
                        repeated_attempts=equip_attempts,
                        stop_on_unconfirmed=True,
                    )
                    if (
                        self._read_chess_mode() != initial_mode
                        or self.appear(self.I_SELECT_GRIGRI)
                        or self._is_shop_open()
                    ):
                        logger.warning(
                            'Stop emergency Chess hand cleanup: screen changed '
                            'during equipment step'
                        )
                        return None
                    if step_equipped:
                        after_count = self._hand_capacity_count()
                        equipped.extend(step_equipped)
                        logger.info(
                            'Chess full-hand equip step confirmed: '
                            f'item={step_equipped[0]}, '
                            f'hand_capacity={current_count}->{after_count}/10'
                        )
                        continue
                    self.screenshot()
                    continue

                # 指定对象仍未上阵时，先允许将手牌预留御魂释放为通用分配（仍保护指定纹章与两槽）。
                relaxed_action = self._select_next_equipment_action(
                    verified_board_names,
                    repeated_attempts=equip_attempts,
                    relax_soul_reserve=True,
                )
                if relaxed_action is not None:
                    relaxed_equipped = self.equip_souls_from_hand(
                        verified_board_names,
                        max_actions=1,
                        include_special=False,
                        repeated_attempts=equip_attempts,
                        stop_on_unconfirmed=True,
                        relax_soul_reserve=True,
                    )
                    if (
                        self._read_chess_mode() != initial_mode
                        or self.appear(self.I_SELECT_GRIGRI)
                        or self._is_shop_open()
                    ):
                        logger.warning(
                            'Stop emergency Chess hand cleanup: screen changed '
                            'during relaxed equipment step'
                        )
                        return None
                    if relaxed_equipped:
                        after_count = self._hand_capacity_count()
                        equipped.extend(relaxed_equipped)
                        logger.info(
                            'Chess full-hand relaxed equipment step confirmed (释放未上阵指定御魂): '
                            f'item={relaxed_equipped[0]}, '
                            f'hand_capacity={current_count}->{after_count}/10'
                        )
                        continue
                    self.screenshot()
                    continue

            equip_sale = self._select_next_sellable_equipment_for_cleanup(
                verified_board_names
            )
            if equip_sale is not None:
                id_before = self._hand_card_identity_count(
                    equip_sale['kind'], equip_sale['name'],
                )
                logger.info(
                    'Chess full-hand sell equipment: '
                    f'type={equip_sale["kind"]}, '
                    f'name={equip_sale["display_name"]}, '
                    f'reason={equip_sale["reason"]}, '
                    f'position={equip_sale["position"]}, '
                    f'identity_count={id_before}, '
                    f'hand_capacity={current_count}/10'
                )
                self.sell_hand_card(equip_sale['position'])
                confirmed = self._wait_hand_card_removed(
                    id_before,
                    lambda: self._hand_card_identity_count(
                        equip_sale['kind'], equip_sale['name'],
                    ),
                )
                id_after = self._hand_card_identity_count(
                    equip_sale['kind'], equip_sale['name'],
                )
                after_count = self._hand_capacity_count()
                if (
                    not confirmed
                    or self._read_chess_mode() != initial_mode
                    or self.appear(self.I_SELECT_GRIGRI)
                ):
                    # 装备出售结果未知或画面变化时直接停止，决不能跳去卖式神。
                    logger.warning(
                        'Stop Chess full-hand cleanup without selling shikigami: '
                        'equipment sale unconfirmed or screen changed '
                        f'(type={equip_sale["kind"]}, '
                        f'name={equip_sale["display_name"]}, '
                        f'identity_count={id_before}->{id_after}, '
                        f'hand_capacity={current_count}->{after_count}/10)'
                    )
                    return None
                sold_equipment.append({
                    'kind': equip_sale['kind'],
                    'name': equip_sale['name'],
                    'position': equip_sale['position'],
                })
                logger.info(
                    'Chess full-hand equipment sale confirmed: '
                    f'type={equip_sale["kind"]}, '
                    f'name={equip_sale["display_name"]}, '
                    f'identity_count={id_before}->{id_after}, '
                    f'hand_capacity={current_count}->{after_count}/10'
                )
                continue

            non_lineup = self._select_next_non_lineup_shikigami_for_cleanup()
            if non_lineup is not None:
                if not logged_non_lineup_entry:
                    logger.info(
                        'Chess full-hand enter shikigami sale (non-lineup): '
                        'no equippable or sellable equipment remaining, '
                        f'hand_capacity={current_count}/10'
                    )
                    logged_non_lineup_entry = True
                id_before = self._hand_card_identity_count(
                    'shikigami', non_lineup['name'],
                )
                logger.info(
                    'Sell Chess non-lineup shikigami for full-hand cleanup: '
                    f'name={non_lineup["display_name"]}({non_lineup["name"]}), '
                    f'position={non_lineup["position"]}, '
                    f'identity_count={id_before}, '
                    f'hand_capacity={current_count}/10'
                )
                self.sell_hand_card(non_lineup['position'])
                confirmed = self._wait_hand_card_removed(
                    id_before,
                    lambda: self._hand_card_identity_count(
                        'shikigami', non_lineup['name'],
                    ),
                )
                id_after = self._hand_card_identity_count(
                    'shikigami', non_lineup['name'],
                )
                after_count = self._hand_capacity_count()
                if (
                    not confirmed
                    or self._read_chess_mode() != initial_mode
                    or self.appear(self.I_SELECT_GRIGRI)
                ):
                    logger.warning(
                        'Stop Chess full-hand cleanup: non-lineup shikigami '
                        'sale unconfirmed or screen changed '
                        f'(name={non_lineup["display_name"]}, '
                        f'identity_count={id_before}->{id_after}, '
                        f'hand_capacity={current_count}->{after_count}/10)'
                    )
                    return None
                sold_non_lineup.append(non_lineup['position'])
                logger.info(
                    'Chess full-hand non-lineup shikigami sale confirmed: '
                    f'name={non_lineup["display_name"]}({non_lineup["name"]}), '
                    f'identity_count={id_before}->{id_after}, '
                    f'hand_capacity={current_count}->{after_count}/10'
                )
                continue

            break
        else:
            logger.warning(
                'Stop emergency Chess hand cleanup at safety limit '
                f'{self.HAND_CLEANUP_SAFETY_LIMIT}'
            )

        final_hand_count = self._hand_capacity_count()
        logger.info(
            'Emergency Chess hand cleanup complete: '
            f'hand_capacity={initial_hand_count}->{final_hand_count}/10, '
            f'equipped={equipped}, '
            f'sold_equipment={[item["name"] for item in sold_equipment]}, '
            f'sold_non_lineup={sold_non_lineup}'
        )
        return {
            'type': 'emergency_cleanup',
            'equipped': equipped,
            'sold_equipment': sold_equipment,
            'sold_non_lineup': sold_non_lineup,
            'hand_count_before': initial_hand_count,
            'hand_count_after': final_hand_count,
        }

    def _free_one_hand_slot_for_purchase(
        self,
        sell_lineup: bool = False,
    ) -> dict | None:
        """购买受阻时清理；降到<=9后停止，无其他可清理项时才卖阵容手牌式神；_buy_shop_slot 严禁直接传 sell_lineup=True。"""
        def _sell_lineup_until_ready(reason: str) -> dict | None:
            logger.info(
                f'Chess full-hand enter lineup shikigami sale: reason={reason}, '
                f'hand_capacity={self._hand_capacity_count()}/10'
            )
            sold_lineup = []
            for _ in range(self.HAND_CLEANUP_SAFETY_LIMIT):
                if (
                    not self._is_hand_cleanup_allowed(('备', '战'))
                    or self.appear(self.I_SELECT_GRIGRI)
                ):
                    return None
                self.screenshot()
                sold_one = self.sell_one_lineup_hand_card()
                if sold_one is None:
                    return None
                sold_lineup.append(sold_one)
                if self._hand_capacity_count() <= 9:
                    break
            return {
                'type': 'lineup',
                'name': sold_lineup[-1]['name'],
                'position': sold_lineup[-1]['position'],
                'sold_lineup': sold_lineup,
                'hand_count_after': self._hand_capacity_count(),
            }

        if sell_lineup:
            if not self._ensure_shop_closed(allowed_modes=('备', '战')):
                return None
            result = _sell_lineup_until_ready('post_click_retry_lineup_fallback')
            if result is None:
                return None
        else:
            result = self.emergency_cleanup_hand()
            if result is None:
                return None
            freed_by_cleanup = bool(
                result.get('equipped')
                or result.get('sold_equipment')
                or result.get('sold_non_lineup')
            )
            cap_after = self._hand_capacity_count()
            # 既要兼容旧替身仅返回未带 hand_count_after 的 NOOP 场景，也要确保实盘达到 <=9/10 后不误卖阵容卡。
            still_needs_slot = (cap_after >= 10) or (
                not freed_by_cleanup
                and result.get('hand_count_after') is None
            )
            if still_needs_slot:
                reason = (
                    f'hand_still_full_{cap_after}_of_10_'
                    'no_equippable_or_sellable_equipment_or_non_lineup_remaining'
                    if cap_after >= 10
                    else 'emergency_cleanup_freed_no_hand_space'
                )
                if (
                    not self._is_hand_cleanup_allowed(('备', '战'))
                    or self.appear(self.I_SELECT_GRIGRI)
                ):
                    return None
                lineup_result = _sell_lineup_until_ready(reason)
                if lineup_result is None:
                    return None
                lineup_result['equipped'] = result.get('equipped', [])
                lineup_result['sold_equipment'] = result.get(
                    'sold_equipment', []
                )
                lineup_result['sold_non_lineup'] = result.get(
                    'sold_non_lineup', []
                )
                result = lineup_result

        # 本方法只在购前/购后清理流程调用；清理完成后必须重新展开商店继续购卡。
        if not self._ensure_shop_open():
            logger.warning(
                'Emergency Chess hand cleanup succeeded, but shop could not '
                'be reopened'
            )
            return None
        self.screenshot()
        return result

    def _golden_copy_targets(self, verified_names: set[str]) -> list[tuple[str, int]]:
        """仅选择已确认在棋盘上的一费式神，使用本局实际站位。"""
        targets = []
        for name in self._verified_board_lineup_names(verified_names):
            entry = resolve_shikigami(name)
            position = self._registered_actual_position(name)
            if entry is not None and entry.cost == 1 and position is not None:
                targets.append((name, int(position)))
        return sorted(targets, key=lambda item: (item[1], item[0]))

    def _golden_copy_hand_cards(self) -> list[dict]:
        return [card for card in self._frame_card_scan('emblem')
                if card['type'] == 'duplicator']

    def use_golden_copies_from_hand(self, verified_names: set[str]) -> int:
        """黄金复制术拖至已部署的一费式神；没有目标或未消耗则保留。"""
        used = 0
        for _ in range(self.SOUL_EQUIP_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                break
            cards = self._golden_copy_hand_cards()
            if not cards:
                break
            targets = self._golden_copy_targets(verified_names)
            if not targets:
                logger.info('Keep 黄金复制术: no verified deployed one-cost shikigami')
                break
            if not self._ensure_shop_closed() or not self._is_preparation_mode():
                break
            # 关闭商店后重新读取卡牌位置，避免使用旧画面的坐标。
            cards = self._golden_copy_hand_cards()
            if not cards:
                break
            card = min(cards, key=lambda item: item['position'][0])
            name, position = targets[0]
            before = len(cards)
            if not self._equip_soul_card(card['position'], position, 'GOLDEN_COPY'):
                break
            if not self._wait_hand_card_removed(before, lambda: len(self._golden_copy_hand_cards())):
                logger.warning(f'黄金复制术 use not confirmed: target={name}, set={position}')
                break
            used += 1
            logger.info(f'黄金复制术 used: target={name}, set={position}')
        return used

    def _recognized_emblem_hand_cards(self) -> list[dict]:
        """纹章 Frame 定位卡牌，中心图案确认种类；Click 范围用于拖拽。"""
        return [dict(card) for card in self._frame_card_scan('emblem')
                if card['type'] == 'emblem']

    def _can_equip_emblem_on_unit(
        self,
        name: str,
        emblem_name: str,
    ) -> bool:
        """按策略 A 判断式神是否不自带该羁绊且仍有指定/可用槽位可佩戴该纹章。"""
        bond = grigri_bond_name(emblem_name)
        if bond is None:
            return False
        if bond in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ()):
            return False
        budget = self._unit_equipment_slot_budget(name)
        if not budget['can_preferred_emblem']:
            return False
        return emblem_name not in budget['occupied']

    def _emblem_preferred_needing_units(self, emblem_name: str) -> list[str]:
        """返回配置了该专属纹章且仍可佩戴的全部式神名。"""
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        return [
            name
            for name, unit in strategy_shikigami.items()
            if emblem_name in unit.get('preferred_emblems', ())
            and self._can_equip_emblem_on_unit(name, emblem_name)
        ]

    def _emblem_reserve_count(self, emblem_name: str) -> int:
        """返回需要为尚未满足的专属纹章配置预留的张数。"""
        return len(self._emblem_preferred_needing_units(emblem_name))

    def _emblem_generic_target_entries(
        self,
        emblem_name: str,
        verified_names: set[str],
        *,
        relax_soul_reserve: bool = False,
    ) -> list[tuple[str, int]]:
        """按策略 A 返回不带该羁绊、有可用通用槽位的通用纹章合法目标（按实际站位升序）。"""
        bond = grigri_bond_name(emblem_name)
        strategy_shikigami = self.get_lineup_strategy()['shikigami']
        lineup_bonds = {
            item
            for name in strategy_shikigami
            for item in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ())
        }
        if bond is None or bond not in lineup_bonds:
            return []
        targets = []
        for name in self._verified_board_lineup_names(verified_names):
            config = strategy_shikigami.get(name)
            if config is None:
                continue
            if bond in SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ()):
                continue
            budget = self._unit_equipment_slot_budget(
                name,
                relax_soul_reserve=relax_soul_reserve,
            )
            if not budget['can_generic_emblem'] or emblem_name in budget['occupied']:
                continue
            actual_pos = self._registered_actual_position(name)
            if actual_pos is not None:
                targets.append((name, actual_pos))
        return sorted(targets, key=lambda item: (item[1], item[0]))

    def _emblem_target_entries(
        self,
        emblem_name: str,
        verified_names: set[str],
        *,
        hand_count: int | None = None,
        relax_soul_reserve: bool = False,
    ) -> list[tuple[str, int, bool]]:
        """返回 (target_name, actual_pos, is_preferred)；未上阵先按需求数预留。"""
        verified = self._verified_board_lineup_names(verified_names)
        needing = self._emblem_preferred_needing_units(emblem_name)
        deployed_preferred = []
        for name in needing:
            if name not in verified:
                continue
            actual_pos = self._registered_actual_position(name)
            if actual_pos is not None:
                deployed_preferred.append((name, actual_pos))
        if deployed_preferred:
            deployed_preferred.sort(key=lambda item: (item[1], item[0]))
            return [
                (name, pos, True)
                for name, pos in deployed_preferred
            ]

        reserve_count = len(needing)
        available_count = 1 if hand_count is None else int(hand_count)
        if available_count <= reserve_count:
            return []
        return [
            (name, pos, False)
            for name, pos in self._emblem_generic_target_entries(
                emblem_name,
                verified,
                relax_soul_reserve=relax_soul_reserve,
            )
        ]

    def _emblem_targets(
        self,
        emblem_name: str,
        verified_names: set[str],
        *,
        hand_count: int | None = None,
    ) -> list[tuple[str, int]]:
        """按实际站位升序选择优先或通用合法纹章目标。"""
        return [
            (name, pos)
            for name, pos, _ in self._emblem_target_entries(
                emblem_name,
                verified_names,
                hand_count=hand_count,
            )
        ]

    def _keep_preferred_emblem(self, emblem_name: str) -> bool:
        """保留尚未装备给指定式神的专属纹章。"""
        return self._emblem_reserve_count(emblem_name) > 0

    def equip_emblems_from_hand(
        self,
        verified_names: set[str],
    ) -> list[str]:
        """按指定优先和实际站位装配纹章；确认失败保留记录，无合法目标且超预留才清理。"""
        equipped = []
        verified_names = self._verified_board_lineup_names(verified_names)
        attempts = {}
        for _ in range(self.SOUL_EQUIP_SAFETY_LIMIT):
            if not self._is_preparation_mode():
                break
            cards = sorted(
                self._recognized_emblem_hand_cards(),
                key=lambda item: item['position'][0],
            )
            if not cards:
                break
            emblem_counts = Counter(card['name'] for card in cards)
            preferred_pick = None
            generic_pick = None
            sell_pick = None
            for card in cards:
                entries = self._emblem_target_entries(
                    card['name'],
                    verified_names,
                    hand_count=emblem_counts[card['name']],
                )
                for target_name, set_index, is_preferred in entries:
                    attempt_key = (
                        'emblem',
                        card['name'],
                        card['position'][0] // 20,
                        set_index,
                    )
                    if attempts.get(attempt_key, 0) >= 2:
                        continue
                    candidate = (card, target_name, set_index, attempt_key)
                    if is_preferred and preferred_pick is None:
                        preferred_pick = candidate
                    elif not is_preferred and generic_pick is None:
                        generic_pick = candidate
                if (
                    sell_pick is None
                    and not self._emblem_target_entries(
                        card['name'], verified_names, hand_count=1,
                    )
                    and not self._emblem_generic_target_entries(
                        card['name'], verified_names,
                    )
                    and emblem_counts[card['name']]
                    > self._emblem_reserve_count(card['name'])
                ):
                    sell_pick = card

            chosen = preferred_pick or generic_pick
            if chosen is not None:
                card, target_name, set_index, attempt_key = chosen
                attempts[attempt_key] = attempts.get(attempt_key, 0) + 1
                outcome = self._equip_selected_hand_equipment({
                    'kind': 'emblem',
                    'tier': (
                        'preferred_emblem'
                        if preferred_pick is not None
                        else 'generic_emblem'
                    ),
                    'card': card,
                    'target_name': target_name,
                    'set_index': set_index,
                    'attempt_key': attempt_key,
                })
                if outcome['aborted']:
                    break
                if outcome['confirmed']:
                    equipped.append(outcome['name'])
                else:
                    self.screenshot()
                continue

            if sell_pick is not None:
                before = self._hand_card_identity_count(
                    'emblem', sell_pick['name'],
                )
                logger.info(
                    'Sell Chess emblem without valid targets above reserve: '
                    f'{sell_pick["name"]}, identity_count={before}'
                )
                self.sell_hand_card(sell_pick['position'])
                if not self._wait_hand_card_removed(
                    before,
                    lambda: self._hand_card_identity_count(
                        'emblem', sell_pick['name'],
                    ),
                ):
                    break
                continue
            break
        return equipped

    def _find_badge_hand_card(self) -> dict | None:
        """返回最左侧已确认种类的纹章，未识别的纹章保留。"""
        cards = self._recognized_emblem_hand_cards()
        return next((card for card in cards if not self._keep_preferred_emblem(card['name'])), None)

    def _recall_one_system_board_card(
        self,
        preferred_set_index: int | None = None,
        *,
        candidate_positions: tuple[int, ...] | list[int] | None = None,
        raise_on_failure: bool = True,
        allow_verified_duplicate: bool = False,
    ) -> int | None:
        """满员上卡时只下阵一个系统卡或已确认重复阵容副本格，成功则返回对应站位。"""
        self._last_system_recall_outcome = 'not_found'
        if not self._is_preparation_mode():
            self._last_system_recall_outcome = 'not_preparation'
            return None
        if not self._ensure_shop_closed():
            logger.warning(
                'Cannot free Chess lineup slot: shop could not be closed'
            )
            return None

        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        positions = (
            [int(pos) for pos in candidate_positions]
            if candidate_positions is not None
            else list(self.BOARD_RECALL_POSITIONS)
        )
        if preferred_set_index in positions:
            positions.remove(preferred_set_index)
            positions.insert(0, preferred_set_index)

        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )
        self.screenshot()
        goldfish_positions, _ = self._protected_recall_positions()
        for set_index in positions:
            is_dup_override = bool(
                allow_verified_duplicate
                and self._is_recallable_duplicate_slot(set_index)['recallable']
            )
            if set_index in goldfish_positions:
                continue
            if set_index in player_positions and not is_dup_override:
                continue
            if not self._board_set_has_shikigami(set_index):
                continue

            source = self._set_position(set_index)
            goldfish_kept_at_target = False
            for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
                if not self._is_preparation_mode():
                    self._last_system_recall_outcome = 'not_preparation'
                    logger.info(
                        'Pause Chess system-card recall: mode is no longer preparation'
                    )
                    return None
                if self._hand_capacity_count() >= 10:
                    self._last_system_recall_outcome = 'hand_full'
                    logger.info('Pause Chess system-card recall: hand is full, no room for recalled card')
                    return None
                drag_source = (
                    source
                    if attempt == 1
                    else (source[0], source[1] - 14)
                )
                Press_and_Drag(
                    self.device,
                    p1=drag_source,
                    p2=hand_target,
                    hold_duration=(0.2, 0.3),
                    point_random=(-2, -2, 2, 2),
                    swipe_duration=0.5,
                    name=(
                        f'CHESS_FREE_SYSTEM_SET_{set_index}'
                        f'_ATTEMPT_{attempt}'
                    ),
                )
                if self._wait_chess_action_state(
                    lambda: self._board_set_is_empty(set_index)
                ):
                    slot_rec = self._board_slots_table().get(int(set_index), {})
                    recalled_ident = slot_rec.get('identity')
                    if (
                        recalled_ident
                        and slot_rec.get('kind') == 'lineup'
                        and self._has_other_satisfied_copy(
                            recalled_ident,
                            exclude_slot=int(set_index),
                        )
                    ):
                        # 仅清理副本所在格状态，本体配置位、已上阵登记与装备记录全部无损保留。
                        self._invalidate_board_slot(
                            int(set_index),
                            'empty_confirmed',
                            clear_identity=True,
                        )
                    elif recalled_ident and slot_rec.get('kind') == 'lineup':
                        self._mark_board_unit_returned_to_hand(
                            recalled_ident,
                            from_slot=int(set_index),
                            reason='recalled_to_hand',
                        )
                    else:
                        self._invalidate_board_slot(
                            int(set_index),
                            'empty_confirmed',
                            clear_identity=True,
                        )
                    self._last_system_recall_outcome = 'recalled'
                    logger.debug(
                        f'Chess system card recalled for deployment: '
                        f'set={set_index}, attempt={attempt}'
                    )
                    return set_index
                if self._handle_goldfish_after_board_action_failure(
                    set_index,
                    action='recall_for_deploy',
                ):
                    self.screenshot()
                    source_state = self._board_set_state(set_index)
                    if source_state == 'empty':
                        self._last_system_recall_outcome = 'recalled'
                        logger.info(
                            'Chess failed recall source cleared after moving '
                            f'goldfish: set={set_index}'
                        )
                        return set_index
                    if set_index == self._arakawa_goldfish_target_position():
                        goldfish_kept_at_target = True
                        logger.info(
                            'Keep Chess goldfish at assigned position during '
                            f'system recall: set={set_index}'
                        )
                        break
                    if source_state == 'occupied':
                        logger.info(
                            'Chess failed recall source remains occupied after '
                            'goldfish swap; continue original recall: '
                            f'set={set_index}'
                        )
                        continue
                    self._last_system_recall_outcome = 'unknown_after_drag'
                    logger.warning(
                        'Chess failed recall source state is unknown after '
                        f'handling goldfish; stop system recall: set={set_index}'
                    )
                    return None
                post_state = self._board_set_state(set_index)
                if post_state != 'occupied':
                    # 已发出拖拽但超时后状态未知，不再重复拖拽也不继续扫后续格。
                    self._last_system_recall_outcome = 'unknown_after_drag'
                    logger.warning(
                        'Chess system card recall result is unknown after '
                        f'timeout; stop retrying drag: set={set_index}, '
                        f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                        f'state={post_state}'
                    )
                    return None
                if (
                    attempt == 1
                    and raise_on_failure
                    and self._check_arakawa_bond_qualified()['qualified']
                    and not self._is_confirmed_arakawa_goldfish(set_index)
                ):
                    round_state = self._ensure_prep_goldfish_round_state()
                    remaining = self._read_remaining_time()
                    if (
                        int(set_index) not in round_state['inspected_slots']
                        and remaining is not None
                        and remaining >= self.GOLDFISH_SINGLE_INSPECT_MIN_REMAINING
                    ):
                        round_state['inspected_slots'].add(int(set_index))
                        inspection = self._inspect_board_set_shikigami(
                            set_index,
                            max_attempts=1,
                        )
                        if inspection.get('name') == 'arakawa_goldfish':
                            self._record_arakawa_goldfish_position(
                                set_index,
                                identified=True,
                            )
                            goldfish_kept_at_target = True
                            logger.info(
                                'Skip Chess system recall on confirmed '
                                f'unidentified goldfish at set {set_index}'
                            )
                            break
                logger.warning(
                    'Chess system card recall did not clear occupied slot: '
                    f'set={set_index}, '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                    f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
                )
            else:
                if not raise_on_failure:
                    self._last_system_recall_outcome = 'recall_failed'
                    logger.warning(
                        'Stop Chess constrained system-card recall without '
                        f'raising: set={set_index} remained occupied after '
                        f'{self.ACTION_ICON_MAX_ATTEMPTS} attempts'
                    )
                    return None
                raise GameStuckError(
                    'Chess: failed to recall occupied system card at '
                    f'set {set_index} after 3 attempts'
                )
            if goldfish_kept_at_target:
                continue
        return None

    def recall_all_board_cards(self) -> bool:
        """按系统自动上阵顺序，快速回收棋盘右侧四个候选位置。"""
        if not self._ensure_shop_closed():
            logger.warning(
                'Abort Chess board recall: shop could not be closed'
            )
            return False
        hand_target = self._rule_center(
            RuleClick(
                roi_front=self.HAND_AREA,
                roi_back=self.HAND_AREA,
                name='chess_hand_area',
            )
        )

        count = self._read_shikigami_count()
        if count is not None and count.get('all_empty', False):
            logger.debug('Chess board is already confirmed empty; skip recall')
            self._board_lineup_names = set()
            self._player_deployed_positions = set()
            self._board_actual_positions = {}
            return True

        tracked_names = set(getattr(self, '_board_lineup_names', set()))
        player_positions = set(
            getattr(self, '_player_deployed_positions', set())
        )
        recall_positions = tuple(
            set_index
            for set_index in self.BOARD_RECALL_POSITIONS
            if set_index not in player_positions
        )
        protected_recall_positions = sorted(
            set(self.BOARD_RECALL_POSITIONS) & player_positions
        )
        if protected_recall_positions:
            logger.debug(
                'Keep Chess system-set positions during recall: '
                f'they were deployed by script, positions='
                f'{protected_recall_positions}'
            )
        logger.debug(
            f'Chess board recall order: {recall_positions}, '
            f'current_count={None if count is None else count["current"]}'
        )
        if not self._is_preparation_mode():
            logger.debug(
                'Stop recalling Chess board cards: '
                'mode is no longer preparation'
            )
            return False

        # 刷新棋盘状态；若商店收起动画吞掉首个手势，由下方空格确认
        # 和有界重试处理，不再无条件等待收起动画。
        self.screenshot()

        # 仅记录已明确确认清空的格子；未知格与留守目标格的金鱼位均保留登记。
        cleared_positions: set[int] = set()
        for set_index in recall_positions:
            slot_state = self._board_set_state(set_index)
            if slot_state == 'empty':
                cleared_positions.add(set_index)
                logger.debug(
                    f'Skip Chess recall set {set_index}: '
                    'slot is already confirmed empty'
                )
                continue
            if slot_state != 'occupied':
                logger.debug(
                    f'Skip Chess recall set {set_index}: '
                    f'slot state is {slot_state}'
                )
                continue
            source = self._set_position(set_index)
            goldfish_handled = False
            for attempt in range(1, self.ACTION_ICON_MAX_ATTEMPTS + 1):
                if self._hand_capacity_count() >= 10:
                    logger.info('Pause Chess board recall: hand is full, no room for recalled card')
                    return False
                drag_source = (
                    source
                    if attempt == 1
                    else (source[0], source[1] - 14)
                )
                Press_and_Drag(
                    self.device,
                    p1=drag_source,
                    p2=hand_target,
                    hold_duration=(0.2, 0.3),
                    point_random=(-3, -3, 3, 3),
                    swipe_duration=0.5 if attempt > 1 else 0.45,
                    name=(
                        f'CHESS_RECALL_SET_{set_index}'
                        f'_ATTEMPT_{attempt}'
                    ),
                )
                if self._wait_chess_action_state(
                    lambda: self._board_set_is_empty(set_index)
                ):
                    cleared_positions.add(set_index)
                    logger.debug(
                        'Chess board recall confirmed empty: '
                        f'set={set_index}, '
                        f'attempt={attempt}/'
                        f'{self.ACTION_ICON_MAX_ATTEMPTS}'
                    )
                    count = self._read_shikigami_count()
                    break
                if self._handle_goldfish_after_board_action_failure(
                    set_index,
                    action='recall_all',
                ):
                    self.screenshot()
                    source_state = self._board_set_state(set_index)
                    if source_state == 'empty':
                        cleared_positions.add(set_index)
                        goldfish_handled = True
                        logger.info(
                            'Continue Chess board recall after goldfish '
                            f'cleared source: set={set_index}'
                        )
                        break
                    if set_index == self._arakawa_goldfish_target_position():
                        goldfish_handled = True
                        logger.info(
                            'Keep Chess goldfish at assigned position during '
                            f'board recall: set={set_index}, '
                            f'source_state={source_state}'
                        )
                        break
                    if source_state == 'occupied':
                        logger.info(
                            'Chess board recall source remains occupied after '
                            'goldfish swap; retry original recall: '
                            f'set={set_index}'
                        )
                        continue
                    logger.warning(
                        'Chess board recall source state is unknown after '
                        f'handling goldfish; stop retrying drag: set={set_index}'
                    )
                    break
                post_state = self._board_set_state(set_index)
                if post_state != 'occupied':
                    # 等待超时后状态未知，不按仍确认占用重复拖拽，并保留原登记。
                    logger.warning(
                        'Chess board recall result is unknown after timeout; '
                        f'stop retrying drag: set={set_index}, '
                        f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                        f'state={post_state}'
                    )
                    break
                logger.warning(
                    'Chess board recall slot still occupied: '
                    f'set={set_index}, '
                    f'attempt={attempt}/{self.ACTION_ICON_MAX_ATTEMPTS}, '
                    f'timeout={self.ACTION_ICON_WAIT_TIMEOUT:.0f}s'
                )
            else:
                raise GameStuckError(
                    'Chess: board recall failed at '
                    f'set {set_index} after 3 attempts'
                )
            if goldfish_handled:
                count = self._read_shikigami_count()

        self.screenshot()
        count = self._read_shikigami_count()
        # 只清除脚本记录中已确认清空的站位；未知格与脚本保护位保留记录。
        self._board_lineup_names = {
            name
            for name in tracked_names
            if getattr(self, '_board_actual_positions', {}).get(
                name,
                self.shikigami_deploy_positions.get(name),
            )
            not in cleared_positions
        }
        self._board_actual_positions = {
            name: set_index
            for name, set_index in getattr(
                self,
                '_board_actual_positions',
                {},
            ).items()
            if set_index not in cleared_positions
        }
        special_positions = {
            int(unit['position'])
            for unit in getattr(self, '_board_special_units', {}).values()
            if unit.get('position') is not None
        }
        self._player_deployed_positions = (
            (player_positions - cleared_positions)
            | special_positions
        )
        if count is not None and count.get('all_empty', False):
            self._board_lineup_names = set()
            self._board_actual_positions = {}
            self._player_deployed_positions = special_positions
        if count is None:
            logger.debug('Chess board recall completed; count is unavailable')
        else:
            logger.debug(
                'Chess board recall completed at positions '
                f'{self.BOARD_RECALL_POSITIONS}: '
                f'cleared={sorted(cleared_positions)}, '
                f'{count["current"]}/{count["total"]}'
            )
        return True
