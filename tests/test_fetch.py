"""fetch.normalize 单元测试：分位换算与字段映射（不触发网络请求）。"""

import re
import unittest

from src import fetch


class TestNormalize(unittest.TestCase):
    def setUp(self):
        self.item = {
            "index_code": "SH000300",
            "ts": 1789056000000,
            "pe": 13.4959,
            "pb": 1.4228,
            "pe_percentile": 0.6736,
            "pb_percentile": 0.4056,
            "roe": 0.1054,
            "yeild": 0.0263,
            "date": "09-11",
        }

    def test_percent_conversion(self):
        rec = fetch.normalize(self.item)
        self.assertEqual(rec["pe_percent"], 67.36)
        self.assertEqual(rec["pb_percent"], 40.56)

    def test_meta_mapping(self):
        rec = fetch.normalize(self.item)
        self.assertEqual(rec["name"], "沪深300")
        self.assertEqual(rec["category"], "large_cap")
        self.assertEqual(rec["index_code"], "SH000300")

    def test_date_format(self):
        rec = fetch.normalize(self.item)
        self.assertIsNotNone(rec["date"])
        self.assertRegex(rec["date"], r"^\d{4}-\d{2}-\d{2}$")


class TestPercentHelper(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(fetch._to_percent(None))

    def test_zero(self):
        self.assertEqual(fetch._to_percent(0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
