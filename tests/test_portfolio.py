"""核心-卫星体系与黄金再平衡规则单元测试。"""

import unittest

from src import portfolio


class TestWeights(unittest.TestCase):
    def test_weights(self):
        funds = [
            {"category": "core", "holding_assets": 5000},
            {"category": "satellite", "holding_assets": 3000},
            {"category": "gold", "holding_assets": 2000},
        ]
        w = portfolio.weights(funds)
        self.assertEqual(w["total"], 10000)
        self.assertAlmostEqual(w["core_ratio"], 0.5)
        self.assertAlmostEqual(w["satellite_ratio"], 0.3)
        self.assertAlmostEqual(w["gold_ratio"], 0.2)

    def test_zero_total(self):
        w = portfolio.weights([])
        self.assertEqual(w["total"], 0.0)
        self.assertEqual(w["core_ratio"], 0.0)


class TestCheckRules(unittest.TestCase):
    def test_satellite_over(self):
        funds = [
            {"category": "core", "holding_assets": 5000},
            {"category": "satellite", "holding_assets": 5000},  # 50% > 40%
        ]
        alerts = portfolio.check_rules(funds)
        self.assertTrue(any(a["code"] == "satellite_over" for a in alerts))

    def test_gold_rebalance_over(self):
        funds = [
            {"category": "core", "holding_assets": 6000},
            {"category": "gold", "holding_assets": 4000},  # 40%，偏离基准 25% 超过 7%
        ]
        alerts = portfolio.check_rules(funds)
        self.assertTrue(any(a["code"] == "gold_rebalance" for a in alerts))

    def test_no_alert(self):
        funds = [
            {"category": "core", "holding_assets": 5500},
            {"category": "satellite", "holding_assets": 2000},
            {"category": "gold", "holding_assets": 2500},
        ]
        # 总 10000，核心 55%、卫星 20%、黄金 25% -> 无提醒
        self.assertEqual(portfolio.check_rules(funds), [])

    def test_no_gold_no_rebalance(self):
        # 组合中无黄金持仓时，不应误报「加仓黄金」
        funds = [{"category": "core", "holding_assets": 10000}]
        alerts = portfolio.check_rules(funds)
        self.assertFalse(any(a["code"] == "gold_rebalance" for a in alerts))


if __name__ == "__main__":
    unittest.main()
