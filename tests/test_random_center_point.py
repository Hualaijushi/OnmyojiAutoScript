from itertools import chain, product
import random
from random import SystemRandom
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from module.atom.swipe import RuleSwipe
from module.base.utils import random as random_utils


class _SequenceRandom:
    def __init__(self, values):
        self.values = iter(values)

    def randrange(self, start, stop):
        value = next(self.values)
        if not start <= value < stop:
            raise AssertionError(f'测试随机值超出范围：{value}')
        return value


class RandomCenterPointTest(TestCase):
    def test_points_stay_in_half_open_roi(self):
        roi = (100, 200, 37, 29)
        for _ in range(5000):
            x, y = random_utils.random_center_point_in_roi(roi)
            self.assertLessEqual(100, x)
            self.assertLess(x, 137)
            self.assertLessEqual(200, y)
            self.assertLess(y, 229)

    def test_single_pixel_roi_returns_only_valid_point(self):
        for _ in range(20):
            self.assertEqual(
                random_utils.random_center_point_in_roi((100, 200, 1, 1)),
                (100, 200),
            )

    def test_invalid_roi_raises(self):
        for roi in (
            (100, 200, 0, 1),
            (100, 200, 1, 0),
            (100, 200, -1, 1),
            (100, 200, 1, -1),
        ):
            with self.subTest(roi=roi):
                with self.assertRaises(ValueError):
                    random_utils.random_center_point_in_roi(roi)

        with self.assertRaises(TypeError):
            random_utils.random_center_point_in_roi((100.0, 200, 1, 1))

    def test_uses_module_system_random_only(self):
        self.assertIsInstance(random_utils._rng, SystemRandom)
        fake_rng = _SequenceRandom((10, 11, 12, 20, 21, 22))
        random.seed(1)
        np.random.seed(1)
        with patch.object(random_utils, '_rng', fake_rng), \
                patch('random.randrange', side_effect=AssertionError('不应使用普通random')), \
                patch('numpy.random.randint', side_effect=AssertionError('不应使用np.random')):
            self.assertEqual(
                random_utils.random_center_point_in_roi((10, 20, 3, 3)),
                (11, 21),
            )

    def test_center_is_more_frequent_than_edges(self):
        triples = list(product(range(9), repeat=3))
        fake_rng = _SequenceRandom(chain.from_iterable(triples))
        with patch.object(random_utils, '_rng', fake_rng):
            results = [random_utils._center_biased_int(0, 9) for _ in triples]

        center_count = sum(3 <= value <= 5 for value in results)
        edge_count = sum(value <= 1 or value >= 7 for value in results)
        self.assertGreater(center_count, edge_count)

    def test_rule_swipe_coord_format_and_ranges(self):
        swipe = RuleSwipe(
            roi_front=(100, 200, 20, 30),
            roi_back=(400, 500, 40, 50),
            mode='default',
        )
        for _ in range(100):
            coord = swipe.coord()
            self.assertEqual(len(coord), 4)
            self.assertTrue(all(isinstance(value, int) for value in coord))
            x1, y1, x2, y2 = coord
            self.assertLessEqual(100, x1)
            self.assertLess(x1, 120)
            self.assertLessEqual(200, y1)
            self.assertLess(y1, 230)
            self.assertLessEqual(400, x2)
            self.assertLess(x2, 440)
            self.assertLessEqual(500, y2)
            self.assertLess(y2, 550)
