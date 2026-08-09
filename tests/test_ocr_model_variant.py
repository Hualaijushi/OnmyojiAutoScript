import unittest
import sys
import types
from unittest.mock import patch

import numpy as np

from module.atom.ocr import RuleOcr
from module.ocr.rpc import OcrRuntime


class FakeOcrModel:
    def __init__(self, single_results=None, full_results=None):
        self.single_results = single_results or {}
        self.full_results = full_results or {}
        self.single_calls = []
        self.full_calls = []

    def ocr_single_line(self, _image, model_variant=None):
        self.single_calls.append(model_variant)
        return self.single_results[model_variant]

    def detect_and_ocr(self, _image, model_variant=None, **kwargs):
        self.full_calls.append((model_variant, kwargs))
        return self.full_results[model_variant]


def make_rule(mode="Single", model_variant="small"):
    rule = RuleOcr(
        name="test_rule",
        mode=mode,
        method="Default",
        roi=(0, 0, 2, 2),
        area=(0, 0, 2, 2),
        keyword="",
        model_variant=model_variant,
    )
    return rule


class OcrModelVariantTest(unittest.TestCase):
    image = np.zeros((2, 2, 3), dtype=np.uint8)

    def test_default_model_is_small(self):
        rule = RuleOcr(
            name="default_rule",
            mode="Single",
            method="Default",
            roi=(0, 0, 2, 2),
            area=(0, 0, 2, 2),
            keyword="",
        )
        self.assertEqual(rule.model_variant, "small")

    def test_low_single_line_score_stays_on_small(self):
        rule = make_rule()
        fake = FakeOcrModel(single_results={"small": ("wrong", 0.2)})
        rule.__dict__["model"] = fake

        self.assertEqual(rule.ocr_single_line(self.image), "")
        self.assertEqual(fake.single_calls, ["small"])

    def test_explicit_medium_does_not_run_small_first(self):
        rule = make_rule(model_variant="medium")
        fake = FakeOcrModel(single_results={"medium": ("result", 0.9)})
        rule.__dict__["model"] = fake

        self.assertEqual(rule.ocr_single_line(self.image), "result")
        self.assertEqual(fake.single_calls, ["medium"])

    def test_full_ocr_uses_only_the_selected_model(self):
        rule = make_rule(mode="Full")
        fake = FakeOcrModel(full_results={"small": []})
        rule.__dict__["model"] = fake

        results = rule.detect_and_ocr(self.image, logDisplay=False)
        self.assertEqual(results, [])
        self.assertEqual([call[0] for call in fake.full_calls], ["small"])

    def test_runtime_lazily_caches_each_model_variant(self):
        created_variants = []

        class FakeTextSystem:
            def __init__(self, model_variant, **_kwargs):
                self.model_variant = model_variant
                created_variants.append(model_variant)

        fake_module = types.ModuleType("module.ocr.onnx_ppocr")
        fake_module.TextSystem = FakeTextSystem
        runtime = OcrRuntime({"engine": "onnx", "worker_count": 1})
        try:
            with patch.dict(sys.modules, {"module.ocr.onnx_ppocr": fake_module}):
                small = runtime._get_model("small")
                self.assertIs(runtime._get_model("small"), small)
                medium = runtime._get_model("medium")
                self.assertIsNot(small, medium)
        finally:
            runtime.shutdown()

        self.assertEqual(created_variants, ["small", "medium"])


if __name__ == "__main__":
    unittest.main()
