"""Read Chess cards with shared Frame layouts and generated portrait references."""
from copy import copy
from functools import cached_property
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from module.atom.image import RuleImage
from module.logger import logger
from tasks.Chess.assets import ChessAssets
from tasks.Chess.strategy.shikigami_catalog import normalize_bond_ocr_text, bond_key, SHIKIGAMI_BONDS_BY_ROMAJI

ROOT = Path(__file__).resolve().parents[1] / 'resource'


def read_image(path):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f'Cannot decode {path}')
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def frame_layout(name):
    rules = json.loads((ROOT/'c_frame.json').read_text(encoding='utf-8'))
    return next(rule for rule in rules if rule['itemName'] == name)


def layout_bytes(rule):
    return json.dumps(rule, ensure_ascii=False, sort_keys=True).encode('utf-8')

EMBLEM_ROOT = ROOT / 'fetter/portraits'


class ChessFrameCardsMixin:
    # Only portrait identity matching uses grayscale; badge/OCR/Frame outputs stay RGB.
    FRAME_PORTRAIT_GRAYSCALE = True
    FRAME_PORTRAIT_AMBIGUITY_MARGIN = 0.03

    def _board_empty_paper_rules(self):
        """按固定顺序返回普通棋盘空位小纸人模板规则（3 -> 1 -> 2）。"""
        return (self.I_C_PAPER_3, self.I_C_PAPER_1, self.I_C_PAPER_2)

    def _can_confirm_board_empty_with_paper(self, boss: bool) -> bool:
        """仅在普通回合、确认「备」且商店收起后才允许使用小纸人判空。"""
        if boss:
            return False
        if not self._is_preparation_mode():
            return False
        return not self._is_shop_open()

    def _match_board_paper_in_slot(self, image, center):
        """以格子落点 (cx, cy) 为基准在格内搜索小纸人，按 3 -> 1 -> 2 达阈值即停。"""
        cx, cy = center
        offset_x, offset_y = self.BOARD_EMPTY_PAPER_OFFSET
        box_w, box_h = self.BOARD_EMPTY_PAPER_SIZE
        img_h, img_w = image.shape[:2]
        left = max(0, cx + offset_x)
        top = max(0, cy + offset_y)
        right = min(img_w, cx + offset_x + box_w)
        bottom = min(img_h, cy + offset_y + box_h)
        roi = (left, top, max(0, right - left), max(0, bottom - top))
        if roi[2] <= 0 or roi[3] <= 0:
            return False, 0.0, None, roi
        crop = image[top:bottom, left:right]
        best_score = None
        for rule in self._board_empty_paper_rules():
            front = rule.image
            if front.shape[0] > crop.shape[0] or front.shape[1] > crop.shape[1]:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(
                crop, front, cv2.TM_CCOEFF_NORMED,
            ))[1])
            if not np.isfinite(score):
                continue
            if best_score is None or score > best_score:
                best_score = score
            if score >= rule.threshold:
                return True, score, rule.name, roi
        return False, (0.0 if best_score is None else best_score), None, roi

    def _board_frame_scan(self):
        """用表情开关定位，一帧读取十二个站位的勾玉、星级与普通准备阶段空位小纸人。"""
        image = self.device.image
        boss = self._is_boss_challenge_round()
        key = (getattr(self.device, 'image_frame_id', None), id(image), boss)
        cached = getattr(self, '_board_frame_cache', None)
        if cached is not None and cached[0] == key:
            return cached[1]
        frame = self.F_BOSS_BOARD_OCCUPANCY if boss else self.F_BOARD_OCCUPANCY
        result = frame.run(self, *([None] * len(frame.roi_ranges)))
        slots = []
        if result.matched:
            paper_enabled = self._can_confirm_board_empty_with_paper(boss)
            for crop, area, deploy_area in zip(
                result[:12],
                frame.matched_ranges[:12],
                frame.matched_ranges[12:24],
            ):
                scores = []
                for star, rule in enumerate(self.board_occupancy_rules, 1):
                    front = rule.image
                    if front.shape[0] > crop.shape[0] or front.shape[1] > crop.shape[1]:
                        continue
                    score = float(cv2.minMaxLoc(cv2.matchTemplate(
                        crop, front, cv2.TM_CCOEFF_NORMED,
                    ))[1])
                    if np.isfinite(score) and score >= self.BOARD_OCCUPANCY_TEMPLATE_THRESHOLD:
                        scores.append((score, star))
                scores.sort(reverse=True)
                jade_matched = bool(scores)
                jade_star = (scores[0][1] if scores and
                             (len(scores) == 1 or scores[0][0] - scores[1][0] >= .05)
                             else None)
                center = (
                    int(round(deploy_area[0] + deploy_area[2] / 2)),
                    int(round(deploy_area[1] + deploy_area[3] / 2)),
                )
                if boss:
                    state = 'occupied' if jade_matched else 'empty'
                    paper_matched = False
                    paper_score = None
                    paper_template = None
                    paper_roi = None
                elif paper_enabled:
                    paper_matched, paper_score, paper_template, paper_roi = (
                        self._match_board_paper_in_slot(image, center)
                    )
                    if jade_matched and not paper_matched:
                        state = 'occupied'
                    elif paper_matched and not jade_matched:
                        state = 'empty'
                    else:
                        state = 'unknown'
                else:
                    # 普通回合非「备」或商店展开时禁用小纸人判空，未命中勾玉一律记未知。
                    paper_matched = False
                    paper_score = None
                    paper_template = None
                    paper_roi = None
                    state = 'occupied' if jade_matched else 'unknown'
                slots.append({
                    'state': state,
                    'occupied': state == 'occupied',
                    'empty': state == 'empty',
                    'unknown': state == 'unknown',
                    'star': jade_star if state == 'occupied' else None,
                    'roi': tuple(int(round(v)) for v in area),
                    'center': center,
                    'jade_matched': jade_matched,
                    'paper_checked': paper_enabled,
                    'paper_matched': paper_matched,
                    'paper_score': paper_score,
                    'paper_template': paper_template,
                    'paper_roi': paper_roi,
                })
        else:
            logger.debug('Chess board Frame: emoji anchor not found')
        self._board_frame_cache = (key, slots)
        return slots

    @cached_property
    def golden_copy_portrait(self):
        return self._frame_matching_portrait(read_image(ROOT / 'fetter/golden_copy.png'))

    def _golden_copy_score(self, portrait):
        portrait = self._frame_matching_portrait(portrait)
        front = self.golden_copy_portrait
        if portrait.shape[0] < front.shape[0] or portrait.shape[1] < front.shape[1]:
            return 0.0
        return float(cv2.minMaxLoc(cv2.matchTemplate(
            portrait, front, cv2.TM_CCOEFF_NORMED,
        ))[1])

    def _frame_matching_portrait(self, image):
        if self.FRAME_PORTRAIT_GRAYSCALE and image.ndim == 3:
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return image

    @cached_property
    def frame_emblem_library(self):
        library = json.loads((EMBLEM_ROOT/'index.json').read_text(encoding='utf-8'))
        current = frame_layout('fetter_badge')
        if current != library['layout']:
            raise ValueError('Emblem Frame changed: rebuild with dev_tools.chess.build_fetter_library')
        return library

    @cached_property
    def frame_emblem_portraits(self):
        return {key: self._frame_matching_portrait(read_image(EMBLEM_ROOT/item['file']))
                for key, item in self.frame_emblem_library['entries'].items()}

    def _frame_emblem_identity(self, portrait, text):
        portrait = self._frame_matching_portrait(portrait)
        scored = []
        threshold = ChessAssets.F_FETTER_BADGE.operations[2].get('threshold', .8)
        for key, front in self.frame_emblem_portraits.items():
            if front.shape[0] > portrait.shape[0] or front.shape[1] > portrait.shape[1]:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(portrait, front, cv2.TM_CCOEFF_NORMED))[1])
            if np.isfinite(score) and score >= threshold:
                scored.append((score, key))
        if not scored:
            return None, 0.0
        scored.sort(reverse=True)
        near = [item for item in scored if scored[0][0]-item[0] < .03]
        if len(near) == 1:
            return near[0][1], near[0][0]
        entries = self.frame_emblem_library['entries']
        text = ''.join(str(text).split())
        matching = [(score, key) for score, key in near
                    if text in [entries[key]['name'], *entries[key]['ocr_aliases']]]
        return (matching[0][1], matching[0][0]) if len(matching) == 1 else (None, scored[0][0])

    @cached_property
    def frame_card_library(self):
        library = json.loads((ROOT/'card_index.json').read_text(encoding='utf-8'))
        for kind in ('card', 'store'):
            digest = hashlib.sha256(layout_bytes(frame_layout({'card':'hand_card','store':'store_card'}[kind]))).hexdigest()
            if digest != library['layouts'][kind]:
                raise ValueError('Chess Frame layout changed: rebuild with dev_tools.chess.build_card_library')
        return library

    @cached_property
    def frame_portraits(self):
        return {
            kind: {name: self._frame_matching_portrait(read_image(ROOT/item['portrait']))
                   for name, item in entries.items()}
            for kind, entries in self.frame_card_library['cards'].items()
        }

    @cached_property
    def frame_badges(self):
        return {
            kind: [read_image(Path(file)) for file in frame.files]
            for kind, frame in (('card', ChessAssets.F_HAND_CARD), ('store', ChessAssets.F_STORE_CARD),
                                ('emblem', ChessAssets.F_FETTER_BADGE))
        }


    def _score_frame_portraits(self, kind, portrait, *, threshold=None):
        """按运行时完全一致的预处理与归一化模板匹配，计算头像库全部式神得分。"""
        portrait_norm = self._frame_matching_portrait(portrait)
        frame = ChessAssets.F_HAND_CARD if kind == 'card' else ChessAssets.F_STORE_CARD
        eff_threshold = float(frame.operations[-2].get('threshold', 0.8) if threshold is None else threshold)
        all_scored = []
        for name, front in self.frame_portraits[kind].items():
            if front.shape[0] > portrait_norm.shape[0] or front.shape[1] > portrait_norm.shape[1]:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(portrait_norm, front, cv2.TM_CCOEFF_NORMED))[1])
            if np.isfinite(score):
                all_scored.append((score, name))
        all_scored.sort(reverse=True)
        above_threshold = [(score, name) for score, name in all_scored if score >= eff_threshold]
        return above_threshold, all_scored, eff_threshold

    def _resolve_card_identity_detail(self, kind, portrait, text, *, portrait_threshold=None):
        """执行与运行时一致的头像阈值、0.03 歧义区间及羁绊 OCR 消歧，并返回诊断明细。"""
        above_threshold, all_scored, eff_threshold = self._score_frame_portraits(
            kind, portrait, threshold=portrait_threshold,
        )
        margin = float(self.FRAME_PORTRAIT_AMBIGUITY_MARGIN)
        if not above_threshold:
            return {
                'resolved_name': None,
                'resolved_score': 0.0,
                'effective_threshold': eff_threshold,
                'ambiguity_margin': margin,
                'all_scored': all_scored,
                'above_threshold': [],
                'near_candidates': [],
                'ambiguity_triggered': False,
                'ambiguity_resolved': False,
                'bond_observed': None,
                'bond_matching_names': [],
            }
        near = [(score, name) for score, name in above_threshold if above_threshold[0][0] - score < margin]
        if len(near) == 1:
            return {
                'resolved_name': near[0][1],
                'resolved_score': near[0][0],
                'effective_threshold': eff_threshold,
                'ambiguity_margin': margin,
                'all_scored': all_scored,
                'above_threshold': above_threshold,
                'near_candidates': near,
                'ambiguity_triggered': False,
                'ambiguity_resolved': True,
                'bond_observed': None,
                'bond_matching_names': [near[0][1]],
            }
        entries = self.frame_card_library['cards'][kind]
        if kind == 'store':
            raw = normalize_bond_ocr_text(text[0]) if text else ''
            names = [(score, name) for score, name in near if entries[name]['name'] == raw]
            if len(names) == 1:
                return {
                    'resolved_name': names[0][1],
                    'resolved_score': names[0][0],
                    'effective_threshold': eff_threshold,
                    'ambiguity_margin': margin,
                    'all_scored': all_scored,
                    'above_threshold': above_threshold,
                    'near_candidates': near,
                    'ambiguity_triggered': True,
                    'ambiguity_resolved': True,
                    'bond_observed': raw,
                    'bond_matching_names': [names[0][1]],
                }
        observed = bond_key(tuple(normalize_bond_ocr_text(t) for t in text[-3:]))
        matching = [
            (score, name) for score, name in near
            if observed and observed == bond_key(SHIKIGAMI_BONDS_BY_ROMAJI[name])
        ]
        resolved = (matching[0][1], matching[0][0]) if len(matching) == 1 else (None, above_threshold[0][0])
        return {
            'resolved_name': resolved[0],
            'resolved_score': resolved[1],
            'effective_threshold': eff_threshold,
            'ambiguity_margin': margin,
            'all_scored': all_scored,
            'above_threshold': above_threshold,
            'near_candidates': near,
            'ambiguity_triggered': True,
            'ambiguity_resolved': len(matching) == 1,
            'bond_observed': sorted(observed) if observed else [],
            'bond_matching_names': [name for _, name in matching],
        }

    def _frame_card_identity(self, kind, portrait, text):
        """Require a portrait match; use name/traits to resolve near-score candidates."""
        detail = self._resolve_card_identity_detail(kind, portrait, text)
        return detail['resolved_name'], detail['resolved_score']

    def _scan_hand_card_badge_anchors(self, frame, kind, *, badge_threshold=None):
        """按角标规则扫描并去重候选卡锚点，与 _frame_card_scan 共用定位基准。"""
        image = self.device.image
        eff_threshold = float(frame.threshold if badge_threshold is None else badge_threshold)
        x, y, w, h = frame.roi_back
        bx, by, bw, bh = frame.badge_references[0]
        back = image[y:y+h, x:x+w]
        if frame.badge_grayscale:
            back = cv2.cvtColor(back, cv2.COLOR_RGB2GRAY)
        candidates = []
        for index, front in enumerate(self.frame_badges[kind]):
            if frame.badge_grayscale:
                front = cv2.cvtColor(front, cv2.COLOR_RGB2GRAY)
            if min(back.shape[:2]) == 0 or front.shape[0] > back.shape[0] or front.shape[1] > back.shape[1]:
                continue
            scores = cv2.matchTemplate(back, front, cv2.TM_CCOEFF_NORMED)
            ys, xs = np.where(scores >= eff_threshold)
            candidates.extend((float(scores[dy, dx]), x+int(dx), y+int(dy), index) for dy, dx in zip(ys, xs))
        anchors = []
        for candidate in sorted(candidates, reverse=True):
            if not any(abs(candidate[1]-a[1]) < bw and abs(candidate[2]-a[2]) < bh for a in anchors):
                anchors.append(candidate)
        return sorted(anchors, key=lambda a: a[1]), eff_threshold

    def _build_local_card_frame(self, frame, kind, ax, ay, index, *, badge_threshold=None):
        """构造单张卡锚定的局部 RuleFrame 副本，并在越界时返回 None。"""
        image = self.device.image
        bx, by, bw, bh = frame.badge_references[0]
        local = copy(frame)
        # The third trait is optional; an empty OCR result is normal here.
        local.optional_ocr_ranges = {'card': (2,), 'store': (3,), 'emblem': ()}[kind]
        local.files = [frame.files[index]]
        local.badgefile = local.files
        local.file = local.files[0]
        local.badge_references = [frame.badge_references[0]]
        local._badge_reference = local.badge_references[0]
        local.roi_front = [bx, by, bw, bh]
        local.roi_back = (ax, ay, self.frame_badges[kind][index].shape[1], self.frame_badges[kind][index].shape[0])
        if badge_threshold is not None:
            local.threshold = float(badge_threshold)
        dx, dy = ax-bx, ay-by
        if any(rx+dx < 0 or ry+dy < 0 or rx+dx+rw > image.shape[1] or ry+dy+rh > image.shape[0]
               for rx, ry, rw, rh in frame.roi_ranges):
            return None
        return local

    def diagnose_hand_card_candidates(
        self,
        *,
        badge_threshold=None,
        portrait_threshold=None,
        bond_ocr_available=True,
    ):
        """用运行时完全一致的 Frame/灰度头像/歧义路径扫描当前截图中的候选式神，并返回逐卡诊断明细。"""
        frame = ChessAssets.F_HAND_CARD
        anchors, eff_badge_threshold = self._scan_hand_card_badge_anchors(
            frame, 'card', badge_threshold=badge_threshold,
        )
        eff_portrait_threshold = float(
            frame.operations[-2].get('threshold', 0.8)
            if portrait_threshold is None
            else portrait_threshold
        )
        entries = self.frame_card_library['cards']['card']
        results = []
        for score, ax, ay, index in anchors:
            local = self._build_local_card_frame(
                frame, 'card', ax, ay, index, badge_threshold=eff_badge_threshold,
            )
            if local is None:
                continue
            local.defer_ocr = True
            result = self.runframe(local)
            if not result:
                continue
            text = tuple(result[:-2])
            portrait_crop = result[-2]
            detail = self._resolve_card_identity_detail(
                'card', portrait_crop, text, portrait_threshold=eff_portrait_threshold,
            )
            bond_ocr_status = 'not_needed'
            if detail['resolved_name'] is None and detail['above_threshold']:
                if bond_ocr_available:
                    try:
                        local.defer_ocr = False
                        ocr_result = self.runframe(local)
                        if ocr_result:
                            text = tuple(ocr_result[:-2])
                            portrait_crop = ocr_result[-2]
                            detail = self._resolve_card_identity_detail(
                                'card', portrait_crop, text, portrait_threshold=eff_portrait_threshold,
                            )
                            bond_ocr_status = 'resolved' if detail['ambiguity_resolved'] else 'ambiguous'
                        else:
                            bond_ocr_status = 'frame_failed'
                    except Exception as exc:
                        bond_ocr_status = f'unavailable:{type(exc).__name__}'
                else:
                    bond_ocr_status = 'ocr_service_not_running'

            card_roi = tuple(int(round(v)) for v in result[-1])
            portrait_roi = tuple(int(round(v)) for v in local.matched_ranges[-2])
            bw, bh = self.frame_badges['card'][index].shape[1], self.frame_badges['card'][index].shape[0]
            top3 = [
                {
                    'rank': rank,
                    'name': name,
                    'cn_name': entries.get(name, {}).get('name', name),
                    'score': round(float(sc), 4),
                    'above_threshold': bool(sc >= eff_portrait_threshold),
                }
                for rank, (sc, name) in enumerate(detail['all_scored'][:3], 1)
            ]
            near_list = [
                {
                    'name': name,
                    'cn_name': entries.get(name, {}).get('name', name),
                    'score': round(float(sc), 4),
                }
                for sc, name in detail['near_candidates']
            ]
            resolved_name = detail['resolved_name']
            cx, cy, cw, ch = card_roi
            results.append({
                'index': len(results) + 1,
                'star': self._frame_star(frame.files[index]),
                'badge_index': index,
                'badge_file': frame.files[index],
                'badge_bbox': [int(ax), int(ay), int(bw), int(bh)],
                'badge_score': round(float(score), 4),
                'badge_threshold': eff_badge_threshold,
                'badge_grayscale': bool(frame.badge_grayscale),
                'card_bbox': list(card_roi),
                'position': [cx + cw // 2, cy + ch // 2],
                'portrait_bbox': list(portrait_roi),
                'portrait_crop_rgb': portrait_crop,
                'portrait_grayscale': bool(self.FRAME_PORTRAIT_GRAYSCALE),
                'portrait_threshold': eff_portrait_threshold,
                'top3': top3,
                'ambiguity_margin': detail['ambiguity_margin'],
                'ambiguity_triggered': detail['ambiguity_triggered'],
                'ambiguity_resolved': detail['ambiguity_resolved'],
                'near_candidates': near_list,
                'bond_texts': [str(t) for t in text],
                'bond_observed': detail['bond_observed'],
                'bond_ocr_status': bond_ocr_status,
                'name': resolved_name,
                'cn_name': entries.get(resolved_name, {}).get('name', '未识别') if resolved_name else '未识别',
                'score': round(float(detail['resolved_score']), 4),
                'type': 'shikigami' if resolved_name else 'unknown',
            })
        return results

    def _frame_card_scan(self, kind):
        """Locate all badges, then run one Frame per card; reuse outputs on the same screenshot."""
        image = self.device.image
        key = (getattr(self.device, 'image_frame_id', None), id(image))
        cache = getattr(self, '_chess_frame_card_cache', None)
        if cache is None or cache[0] != key:
            cache = (key, {})
            self._chess_frame_card_cache = cache
        if kind in cache[1]:
            return cache[1][kind]
        frame = {'card': ChessAssets.F_HAND_CARD, 'store': ChessAssets.F_STORE_CARD,
                 'emblem': ChessAssets.F_FETTER_BADGE}[kind]
        bx, by, bw, bh = frame.badge_references[0]
        anchors, _ = self._scan_hand_card_badge_anchors(frame, kind)
        cards = []
        for score, ax, ay, index in anchors:
            local = self._build_local_card_frame(frame, kind, ax, ay, index)
            if local is None:
                continue
            local.defer_ocr = True
            result = self.runframe(local)  # No True arguments: this path never clicks.
            if not result:
                continue
            if kind == 'emblem':
                raw_text, roi, portrait = result
                # Image identity first. Only an unknown/ambiguous portrait needs OCR.
                copy_score = self._golden_copy_score(portrait)
                golden_copy = copy_score >= .8
                key, identity_score = (None, copy_score) if golden_copy else self._frame_emblem_identity(portrait, '')
                discovery = None
                if key is None and not golden_copy:
                    _, targets = local.range_targets(image.shape, allow_missing_image=True)
                    raw_text = targets[0].ocr(image)
                    text = ''.join(str(raw_text).split()).strip('()（）[]【】')
                    discovery = text if text in ('发现纹章', '发现御魂') else None
                    golden_copy = text == '黄金复制术'
                    if not discovery and not golden_copy:
                        key, identity_score = self._frame_emblem_identity(portrait, raw_text)
                reference = self.frame_emblem_library['entries'].get(key, {})
                cx, cy, cw, ch = roi
                cards.append({
                    'type': 'duplicator' if golden_copy else ('discovery' if discovery else ('emblem' if key else 'unknown')),
                    'name': '黄金复制术' if golden_copy else (discovery or reference.get('name')),
                    'kind': '黄金复制术' if golden_copy else discovery,
                    'similarity': (copy_score if copy_score >= .8 else 1.0) if golden_copy else (1.0 if discovery else identity_score),
                    'score': identity_score, 'badge_score': score,
                    'position': (cx+cw//2, cy+ch//2), 'roi': roi, 'source': 'frame',
                    'text': raw_text, 'raw_text': (raw_text,), 'action': None,
                })
                logger.debug(f'Chess Frame emblem: name={reference.get("name")}, score={identity_score:.3f}, roi={roi}, text={raw_text}')
                continue
            text = tuple(result[:-2])
            name, identity_score = self._frame_card_identity(kind, result[-2], text)
            if name is None and identity_score > 0:
                local.defer_ocr = False
                result = self.runframe(local)
                if not result:
                    continue
                text = tuple(result[:-2])
                name, identity_score = self._frame_card_identity(kind, result[-2], text)
            roi = result[-1]
            cx, cy, cw, ch = roi
            reference = self.frame_card_library['cards'][kind].get(name, {})
            cards.append({
                'type': 'shikigami' if name else 'unknown', 'name': name,
                'score': identity_score, 'badge_score': score,
                'position': (cx+cw//2, cy+ch//2), 'roi': roi,
                'source': 'frame', 'price': reference.get('cost'),
                'portrait_roi': tuple(int(round(v)) for v in local.matched_ranges[-2]),
                'bonds': SHIKIGAMI_BONDS_BY_ROMAJI.get(name, ()) if name else tuple(normalize_bond_ocr_text(t) for t in text[-3:] if normalize_bond_ocr_text(t)),
                'raw_text': text, 'raw_name': text[0] if kind == 'store' else '',
                'star': None if kind == 'store' else self._frame_star(frame.files[index]),
                'action': None,
            })
            logger.debug(f'Chess Frame {kind}: name={name}, star={cards[-1]["star"]}, badge={Path(frame.files[index]).name}, score={identity_score:.3f}, roi={roi}, text={text}')
        cache[1][kind] = cards
        return cards

    @staticmethod
    def _frame_star(file):
        return int(Path(file).stem.rsplit('_', 1)[1])

    def _frame_hand_in_roi(self, roi):
        x, y, w, h = roi
        matches = [card for card in self._frame_card_scan('card') + self._frame_card_scan('emblem')
                   if x <= card['position'][0] < x+w and y <= card['position'][1] < y+h]
        return max(matches, key=lambda card: card['score']) if matches else None

    def _frame_shop_in_slot(self, click_rule, expected_name=None):
        slot_key = tuple(click_rule.roi_back)
        references = getattr(self, '_chess_shop_slot_references', None)
        if references is None:
            references = self._chess_shop_slot_references = {}
        reference = references.get((slot_key, expected_name)) if expected_name else None
        if reference is not None:
            # After buying another slot, only recheck this already identified portrait.
            x, y, w, h = reference['portrait_roi']
            crop = self.device.image[y:y+h, x:x+w]
            front = self.frame_portraits['store'][expected_name]
            if crop.shape[:2] != (h, w) or front.shape[0] > h or front.shape[1] > w:
                return None
            crop = self._frame_matching_portrait(crop)
            score = float(cv2.minMaxLoc(cv2.matchTemplate(crop, front, cv2.TM_CCOEFF_NORMED))[1])
            if not np.isfinite(score) or score < ChessAssets.F_STORE_CARD.operations[-2].get('threshold', .8):
                return None
            return {**reference, 'score': score}
        x, y, w, h = slot_key
        matches = [card for card in self._frame_card_scan('store')
                   if card['name'] and x <= card['position'][0] < x+w and y <= card['position'][1] < y+h]
        result = max(matches, key=lambda card: card['score']) if matches else None
        if result is not None:
            references[(slot_key, result['name'])] = result
        if result is not None and expected_name is not None and result['name'] != expected_name:
            return None
        return result
