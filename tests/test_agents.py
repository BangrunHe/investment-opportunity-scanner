"""规则化加仓周期估算单元测试（不触发大模型）。"""

import unittest

from src import agents, config


class TestRuleBasedCycle(unittest.TestCase):
    def test_buy_signal_cycle(self):
        cfg = config.config_for("SH000300")
        result = agents._rule_based_cycle(cfg, 15.0, "buy", 250.0)
        self.assertEqual(result["signal"], "buy")
        self.assertGreater(result["estimated_cycle_weeks"], 0)

    def test_sell_zone_no_cycle(self):
        cfg = config.config_for("SH000688")
        result = agents._rule_based_cycle(cfg, 85.0, "sell_zone", 0.0)
        self.assertEqual(result["signal"], "sell_zone")
        self.assertEqual(result["estimated_cycle_weeks"], 0)

    def test_pause_no_cycle(self):
        cfg = config.config_for("SZ399006")
        result = agents._rule_based_cycle(cfg, 55.0, "pause", 0.0)
        self.assertEqual(result["signal"], "pause")
        self.assertEqual(result["estimated_cycle_weeks"], 0)


if __name__ == "__main__":
    unittest.main()
