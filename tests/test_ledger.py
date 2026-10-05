"""台账记录单元测试（使用临时路径，不污染真实数据）。"""

import tempfile
import unittest
from pathlib import Path

from src import ledger


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "ledger.json"

    def test_cumulative_and_cycle(self):
        st = ledger.record("SH000300", 125.0, "2026-01-01", self.tmp)
        self.assertEqual(st["total_invested"], 125.0)
        self.assertEqual(st["consecutive_buy_weeks"], 1)

        st = ledger.record("SH000300", 250.0, "2026-01-08", self.tmp)
        self.assertEqual(st["total_invested"], 375.0)
        self.assertEqual(st["consecutive_buy_weeks"], 2)

    def test_cycle_resets_on_no_buy(self):
        ledger.record("SH000300", 125.0, "2026-01-01", self.tmp)
        st = ledger.record("SH000300", 0.0, "2026-01-08", self.tmp)
        self.assertEqual(st["consecutive_buy_weeks"], 0)
        self.assertEqual(st["total_invested"], 125.0)


if __name__ == "__main__":
    unittest.main()
