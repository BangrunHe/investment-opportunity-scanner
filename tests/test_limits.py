"""限额检查单元测试。"""

import unittest

from src import limits


class TestLimits(unittest.TestCase):
    def test_over_invest(self):
        alerts = limits.check(
            "SH000300", {"total_invested": 60000.0, "consecutive_buy_weeks": 10}
        )
        self.assertTrue(any(a["code"] == "over_invest" for a in alerts))

    def test_over_cycle(self):
        alerts = limits.check(
            "SH000688", {"total_invested": 1000.0, "consecutive_buy_weeks": 60}
        )
        self.assertTrue(any(a["code"] == "over_cycle" for a in alerts))

    def test_no_alert(self):
        alerts = limits.check(
            "SZ399006", {"total_invested": 1000.0, "consecutive_buy_weeks": 10}
        )
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
