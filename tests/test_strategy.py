"""纪律规则单元测试：覆盖买入阶梯、递增口径、动作判定、卖出档位。"""

import unittest

from src import strategy


class TestBuyAmount(unittest.TestCase):
    def test_large_cap_tiers(self):
        self.assertEqual(strategy.buy_amount("large_cap", 5), 2000)
        self.assertEqual(strategy.buy_amount("large_cap", 15), 1000)
        self.assertEqual(strategy.buy_amount("large_cap", 25), 500)
        # 边界：恰好等于 30 分位不买入
        self.assertEqual(strategy.buy_amount("large_cap", 30), 0)
        self.assertEqual(strategy.buy_amount("large_cap", 50), 0)

    def test_chinext_geometric(self):
        self.assertAlmostEqual(strategy.buy_amount("chinext", 35), 300)
        self.assertAlmostEqual(strategy.buy_amount("chinext", 25), 450)
        self.assertAlmostEqual(strategy.buy_amount("chinext", 15), 675)
        self.assertAlmostEqual(strategy.buy_amount("chinext", 5), 1012.5)
        self.assertEqual(strategy.buy_amount("chinext", 40), 0)

    def test_star50_double(self):
        self.assertEqual(strategy.buy_amount("star50", 25), 500)
        self.assertEqual(strategy.buy_amount("star50", 15), 1000)
        self.assertEqual(strategy.buy_amount("star50", 5), 2000)
        self.assertEqual(strategy.buy_amount("star50", 30), 0)


class TestAction(unittest.TestCase):
    def test_large_cap(self):
        self.assertEqual(strategy.action("large_cap", 10), "buy")
        self.assertEqual(strategy.action("large_cap", 32), "hold")
        self.assertEqual(strategy.action("large_cap", 40), "pause")
        self.assertEqual(strategy.action("large_cap", 75), "sell_zone")

    def test_chinext_neutral_band(self):
        self.assertEqual(strategy.action("chinext", 45), "hold")
        self.assertEqual(strategy.action("chinext", 55), "pause")

    def test_star50_neutral_band(self):
        self.assertEqual(strategy.action("star50", 35), "hold")
        self.assertEqual(strategy.action("star50", 45), "pause")


class TestSellSteps(unittest.TestCase):
    def test_no_cross(self):
        self.assertEqual(strategy.crossed_sell_steps(75, 0), [])

    def test_first_cross_at_80(self):
        self.assertEqual(strategy.crossed_sell_steps(80, 0), [80.0])

    def test_no_repeat_within_band(self):
        self.assertEqual(strategy.crossed_sell_steps(85, 80), [])

    def test_second_cross_at_90(self):
        self.assertEqual(strategy.crossed_sell_steps(95, 80), [90.0])

    def test_jump_crosses_both(self):
        self.assertEqual(strategy.crossed_sell_steps(92, 0), [80.0, 90.0])


if __name__ == "__main__":
    unittest.main()
