"""`dev_tools/large_click_roi_review.py` 的纯单元测试。

只测符号识别、AST 消费者索引、语义 / 优先级初判、清单组装与分组，不 import 任何 Task、
不启动 Device / MuMu / OCR。
"""

import unittest

from dev_tools import large_click_roi_review as lr


def _rec(symbol, w, h, rule_type="RuleClick", scope="Demo", line=10,
         file="tasks/Demo/assets.py", semantics="fixed", asset_file=None):
    short, long = min(w, h), max(w, h)
    return {
        "symbol": symbol, "rule_type": rule_type, "scope": scope, "file": file, "line": line,
        "roi": [0, 0, w, h], "x": 0, "y": 0, "width": w, "height": h,
        "short_side": short, "long_side": long, "area": w * h,
        "aspect_ratio": round(long / short, 3), "roi_semantics": semantics,
        "size_flag": "normal", "asset_file": asset_file,
    }


class SymbolNameTest(unittest.TestCase):
    def test_accepts_asset_style_names(self):
        for name in ("C_OK", "I_FIRE", "C_RANDOM_ALL", "L_ROTATE_2"):
            self.assertTrue(lr._is_symbol_name(name), name)

    def test_rejects_lowercase_and_short(self):
        for name in ("self", "click", "x", "", "Config"):
            self.assertFalse(lr._is_symbol_name(name), name)

    def test_symbols_in_returns_symbol_and_qualifier(self):
        import ast
        tree = ast.parse("f(self.C_RANDOM_ALL, GeneralBattleAssets.C_X, I_FIRE, obj.lower)")
        self.assertEqual(sorted(set(lr._symbols_in(tree))),
                         [("C_RANDOM_ALL", "self"), ("C_X", "GeneralBattleAssets"),
                          ("I_FIRE", None)])


class ConsumerIndexTest(unittest.TestCase):
    def test_click_verb_records_click_usage(self):
        idx = lr.index_source(
            "class T:\n    def run(self):\n        self.appear_then_click(self.I_FIRE)\n",
            "tasks/Demo/script_task.py")
        (u,) = idx["I_FIRE"]
        self.assertEqual((u.kind, u.verb, u.func, u.line), ("click", "appear_then_click", "run", 3))

    def test_detect_verb_records_detect_usage(self):
        idx = lr.index_source("def f(t):\n    t.appear(I_CHECK)\n", "tasks/Demo/a.py")
        self.assertEqual(idx["I_CHECK"][0].kind, "detect")

    def test_coord_attribute_counts_as_click(self):
        idx = lr.index_source("def f():\n    x, y = C_AREA.coord()\n", "tasks/Demo/a.py")
        self.assertEqual(idx["C_AREA"][0].kind, "coord")

    def test_random_choice_counts_as_indirect_click(self):
        # GameUi/default_pages.py 的真实形状：先 random.choice 选安全区，再 click
        idx = lr.index_source(
            "def f(t):\n    c = random.choice([A.C_RANDOM_TOP, A.C_RANDOM_DOWN])\n    t.click(c)\n",
            "tasks/GameUi/default_pages.py")
        self.assertEqual(idx["C_RANDOM_TOP"][0].kind, "indirect_click")
        self.assertEqual(idx["C_RANDOM_DOWN"][0].kind, "indirect_click")

    def test_multiline_call_still_matched(self):
        idx = lr.index_source(
            "def f(t):\n    t.ui_click(\n        C_BIG,\n        stop=I_DONE,\n    )\n",
            "tasks/Demo/a.py")
        self.assertIn("C_BIG", idx)
        self.assertIn("I_DONE", idx)

    def test_unknown_verb_not_indexed(self):
        idx = lr.index_source("def f():\n    logger.info(C_BIG)\n", "tasks/Demo/a.py")
        self.assertNotIn("C_BIG", idx)

    def test_enclosing_function_is_innermost_def(self):
        idx = lr.index_source(
            "class T:\n    def outer(self):\n        def inner():\n"
            "            self.click(C_X)\n        return inner\n", "tasks/Demo/a.py")
        self.assertEqual(idx["C_X"][0].func, "inner")

    def test_syntax_error_source_is_skipped(self):
        self.assertEqual(lr.index_source("def (:\n", "tasks/Demo/a.py"), {})

    def test_qualifier_is_recorded(self):
        idx = lr.index_source(
            "def f(t):\n    t.click(GeneralBattleAssets.C_RANDOM_LEFT)\n", "tasks/GameUi/a.py")
        self.assertEqual(idx["C_RANDOM_LEFT"][0].qualifier, "GeneralBattleAssets")

    def test_self_qualifier_is_recorded(self):
        idx = lr.index_source("class T:\n    def f(self):\n        self.click(self.C_X)\n", "a.py")
        self.assertEqual(idx["C_X"][0].qualifier, "self")


class AttributionTest(unittest.TestCase):
    _CM = {"GeneralBattleAssets": "tasks/Component/GeneralBattle/assets.py",
           "GameUiAssets": "tasks/GameUi/assets.py"}

    def _u(self, qual):
        return lr.Usage("tasks/X/a.py", 1, "f", "click", "click", qualifier=qual)

    def test_unique_symbol_keeps_everything_as_exact(self):
        rec = _rec("C_ONLY", 200, 200)
        kept, attr = lr.attribute_usages([self._u("self")], rec, self._CM, ambiguous=False)
        self.assertEqual((len(kept), attr), (1, "exact"))

    def test_qualifier_pointing_elsewhere_is_dropped(self):
        rec = _rec("C_RANDOM_LEFT", 140, 437, file="tasks/GameUi/assets.py")
        kept, attr = lr.attribute_usages([self._u("GeneralBattleAssets")], rec,
                                         self._CM, ambiguous=True)
        self.assertEqual((kept, attr), ([], "exact_by_qualifier"))

    def test_qualifier_pointing_here_is_kept_and_exact(self):
        rec = _rec("C_RANDOM_LEFT", 192, 506, file="tasks/Component/GeneralBattle/assets.py")
        kept, attr = lr.attribute_usages([self._u("GeneralBattleAssets")], rec,
                                         self._CM, ambiguous=True)
        self.assertEqual((len(kept), attr), (1, "exact_by_qualifier"))

    def test_self_qualifier_stays_ambiguous(self):
        rec = _rec("C_RANDOM_RIGHT", 191, 518, file="tasks/Component/GeneralBattle/assets.py")
        kept, attr = lr.attribute_usages([self._u("self")], rec, self._CM, ambiguous=True)
        self.assertEqual((len(kept), attr), (1, "ambiguous"))

    def test_assets_class_map_finds_real_classes(self):
        cm = lr.build_assets_class_map()
        self.assertEqual(cm.get("GeneralBattleAssets"),
                         "tasks/Component/GeneralBattle/assets.py")
        self.assertEqual(cm.get("GameUiAssets"), "tasks/GameUi/assets.py")


class SemanticsTest(unittest.TestCase):
    def test_random_name_wins_over_size(self):
        self.assertEqual(lr._guess_semantics(_rec("C_RANDOM_ALL", 1207, 543), []), "random_region")

    def test_fullscreen(self):
        self.assertEqual(lr._guess_semantics(_rec("C_GREEN_MARK_AREA", 1280, 720), []),
                         "fullscreen_dismiss")

    def test_settlement_hint(self):
        self.assertEqual(lr._guess_semantics(_rec("C_UI_REWARD", 208, 368), []),
                         "settlement_region")

    def test_fixed_business(self):
        self.assertEqual(
            lr._guess_semantics(_rec("C_LOGIN_ENSURE_LOGIN_CHARACTER_IN_SAME_SVR", 500, 400), []),
            "fixed_business_area")

    def test_rule_image_defaults_to_dynamic_template(self):
        self.assertEqual(lr._guess_semantics(_rec("I_BIG_PANEL", 300, 300, "RuleImage"), []),
                         "dynamic_template")

    def test_card_hint(self):
        self.assertEqual(lr._guess_semantics(_rec("C_SHIKIGAMI_1", 167, 140), []), "wide_card")

    def test_square_click_is_large_button(self):
        self.assertEqual(lr._guess_semantics(_rec("C_BTN_GO", 120, 110), []), "large_button")

    def test_target_kind_region_vs_point(self):
        self.assertEqual(lr._target_kind("random_region"), "region")
        self.assertEqual(lr._target_kind("settlement_region"), "region")
        self.assertEqual(lr._target_kind("large_button"), "point")
        self.assertEqual(lr._target_kind("wide_card"), "point")

    def test_priority_p0_for_region_semantics(self):
        self.assertEqual(lr._priority(_rec("C_RANDOM_ALL", 1207, 543), "random_region", False), "P0")
        self.assertEqual(lr._priority(_rec("C_X", 1280, 720), "fullscreen_dismiss", True), "P0")

    def test_priority_p1_for_buttons_and_cards(self):
        self.assertEqual(lr._priority(_rec("C_BTN", 120, 110), "large_button", True), "P1")
        self.assertEqual(lr._priority(_rec("C_CARD", 167, 140), "wide_card", True), "P1")

    def test_priority_p2_for_detect_only_template(self):
        self.assertEqual(
            lr._priority(_rec("I_PANEL", 300, 300, "RuleImage"), "dynamic_template", False), "P2")

    def test_dead_asset_question_is_first(self):
        qs = lr._review_questions("large_button", _rec("C_X", 120, 110), False, False)
        self.assertIn("死资产", qs[0])

    def test_detect_only_question_is_first(self):
        qs = lr._review_questions("large_button", _rec("C_X", 120, 110), False, True)
        self.assertIn("检测", qs[0])

    def test_thin_roi_adds_aspect_question(self):
        qs = lr._review_questions("large_safe_region", _rec("C_BAR", 800, 100), True, True)
        self.assertTrue(any("宽高比" in q for q in qs))


class BuildItemsTest(unittest.TestCase):
    def test_threshold_filters_small_roi(self):
        recs = [_rec("C_SMALL", 50, 50), _rec("C_BIG", 200, 200)]
        items = lr.build_items(recs, {}, {}, threshold=96)
        self.assertEqual([it.symbol for it in items], ["C_BIG"])

    def test_rule_ocr_never_enters_main_list(self):
        recs = [_rec("O_BIG", 400, 400, "RuleOcr")]
        self.assertEqual(lr.build_items(recs, {}, {}, threshold=96), [])

    def test_detect_only_rule_image_excluded(self):
        recs = [_rec("I_PANEL", 300, 300, "RuleImage")]
        idx = {"I_PANEL": [lr.Usage("tasks/Demo/a.py", 5, "f", "appear", "detect")]}
        self.assertEqual(lr.build_items(recs, idx, {"I_PANEL": 1}, threshold=96), [])

    def test_rule_image_with_click_consumer_included(self):
        recs = [_rec("I_BTN", 300, 300, "RuleImage")]
        idx = {"I_BTN": [lr.Usage("tasks/Demo/a.py", 5, "f", "appear_then_click", "click")]}
        items = lr.build_items(recs, idx, {"I_BTN": 1}, threshold=96)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].consumer_status, "HAS_CLICK_CONSUMER")

    def test_rule_click_included_even_without_consumer_but_flagged_unused(self):
        items = lr.build_items([_rec("C_DEAD", 200, 200)], {}, {}, threshold=96)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].consumer_status.startswith("UNUSED"))

    def test_ambiguous_attribution_when_symbol_defined_in_several_scopes(self):
        recs = [_rec("C_RANDOM_LEFT", 140, 437, scope="GameUi"),
                _rec("C_RANDOM_LEFT", 192, 506, scope="Component")]
        items = lr.build_items(recs, {}, {}, threshold=96)
        self.assertTrue(all(it.consumer_attribution == "ambiguous" for it in items))
        self.assertEqual(items[0].defined_in_scopes, ["Component", "GameUi"])

    def test_exact_attribution_for_unique_symbol(self):
        items = lr.build_items([_rec("C_ONLY", 200, 200)], {}, {}, threshold=96)
        self.assertEqual(items[0].consumer_attribution, "exact")

    def test_ids_are_sequential_and_sorted_by_priority_then_area(self):
        recs = [_rec("C_CARD_1", 150, 150),                       # wide_card → P1
                _rec("C_RANDOM_ALL", 1207, 543),                  # random → P0
                _rec("C_RANDOM_SMALLER", 200, 200)]               # random → P0
        items = lr.build_items(recs, {}, {}, threshold=96)
        self.assertEqual([it.id for it in items], ["001", "002", "003"])
        self.assertEqual([it.symbol for it in items],
                         ["C_RANDOM_ALL", "C_RANDOM_SMALLER", "C_CARD_1"])

    def test_review_status_always_pending(self):
        items = lr.build_items([_rec("C_BIG", 200, 200)], {}, {}, threshold=96)
        self.assertEqual(items[0].review_status, "pending")

    def test_resource_path_from_asset_file(self):
        recs = [_rec("I_BTN", 300, 300, "RuleImage", asset_file="./tasks/Demo/x/y.png")]
        idx = {"I_BTN": [lr.Usage("a.py", 1, "f", "click", "click")]}
        items = lr.build_items(recs, idx, {"I_BTN": 1}, threshold=96)
        self.assertEqual(items[0].resource_path, "tasks/Demo/x/y.png")
        self.assertFalse(items[0].resource_exists)

    def test_goes_through_click_sampler_and_default_strategy(self):
        items = lr.build_items([_rec("C_BIG", 200, 200)], {}, {}, threshold=96)
        self.assertTrue(items[0].goes_through_click_sampler)
        self.assertEqual(items[0].current_strategy, "LEGACY_UNIFORM")


class GroupingTest(unittest.TestCase):
    def test_excluded_contains_detect_only_image_and_ocr(self):
        recs = [_rec("I_PANEL", 300, 300, "RuleImage"), _rec("O_BIG", 400, 400, "RuleOcr")]
        ex = lr.build_excluded(recs, {}, threshold=96)
        self.assertEqual(sorted(r["symbol"] for r in ex), ["I_PANEL", "O_BIG"])

    def test_all_random_ignores_threshold(self):
        recs = [_rec("C_DOKAN_RANDOM_CLICK_AREA1", 10, 30), _rec("C_RANDOM_ALL", 1207, 543)]
        out = lr.build_all_random(recs, {})
        self.assertEqual(len(out), 2)
        self.assertTrue(all(r["review_status"] == "pending" for r in out))

    def test_all_random_skips_ocr(self):
        self.assertEqual(lr.build_all_random([_rec("O_RANDOM", 400, 400, "RuleOcr")], {}), [])

    def test_very_large_includes_detect_only_items(self):
        recs = [_rec("I_FULL", 1280, 720, "RuleImage"), _rec("C_SMALL", 100, 100)]
        out = lr.build_very_large([], recs, {})
        self.assertEqual([r["symbol"] for r in out], ["I_FULL"])
        self.assertFalse(out[0]["in_main_list"])
        self.assertIn("死资产", out[0]["verdict"])

    def test_very_large_verdict_with_click_consumer(self):
        recs = [_rec("C_FULL", 1280, 720)]
        idx = {"C_FULL": [lr.Usage("a.py", 1, "f", "click", "click")]}
        out = lr.build_very_large([], recs, idx)
        self.assertIn("点击消费者", out[0]["verdict"])

    def test_is_settlement_group(self):
        items = lr.build_items([_rec("C_UI_REWARD", 208, 368, scope="GlobalGame"),
                                _rec("C_SHIKIGAMI_1", 167, 140, scope="Chess")], {}, {},
                               threshold=96)
        flags = {it.symbol: lr.is_settlement_group(it) for it in items}
        self.assertTrue(flags["C_UI_REWARD"])
        self.assertFalse(flags["C_SHIKIGAMI_1"])


class RepoSmokeTest(unittest.TestCase):
    """真实仓库跑一次，确认不炸且关键不变量成立（不锁定精确数字）。"""

    def test_repo_review_has_random_and_no_ocr(self):
        from dataclasses import asdict
        from dev_tools import click_roi_inventory as cri
        records = [asdict(r) for r in cri.scan_repo(list(cri.DEFAULT_ROOTS))]
        idx = lr.build_consumer_index()
        refs = lr.build_reference_index()
        items = lr.build_items(records, idx, refs, class_map=lr.build_assets_class_map())
        self.assertGreater(len(items), 50)
        self.assertTrue(all(it.rule_type != "RuleOcr" for it in items))
        self.assertTrue(all(it.short_side >= lr.LARGE_SHORT_SIDE for it in items))
        self.assertTrue(all(it.review_status == "pending" for it in items))
        # C_RANDOM_CLICK 在 GeneralBattle 里确有点击调用方
        rc = [it for it in items if it.symbol == "C_RANDOM_CLICK"]
        self.assertTrue(rc and rc[0].consumer_status == "HAS_CLICK_CONSUMER")
        # 全部 RANDOM 清单不受门槛限制，应比主清单里的 RANDOM 多
        allr = lr.build_all_random(records, idx)
        self.assertGreaterEqual(len(allr), sum(1 for it in items if "RANDOM" in it.symbol))


if __name__ == "__main__":
    unittest.main()
