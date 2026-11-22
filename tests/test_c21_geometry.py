import unittest

from ocr_evolution.geometry import read_tsv_lines, check_verified_table_adjacency


HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
def line(block, x, y, text):
    return f"5\t1\t{block}\t1\t1\t1\t{x}\t{y}\t40\t12\t95\t{text}\n"


def pairs():
    return HEAD + line(1, 10, 10, "품목") + line(2, 200, 10, "수량") + line(3, 10, 100, "사과") + line(4, 200, 100, "2")


class C21GeometryTests(unittest.TestCase):
    def test_table_neighbor_checks_on_real_coordinates(self):
        gold = [
            {"type": "table", "checked": "verified", "cell": "품목", "right": "수량", "down": "사과"},
            {"type": "table", "checked": "verified", "cell": "수량", "down": "2"},
        ]
        result = check_verified_table_adjacency(pairs(), gold)
        self.assertEqual(result["checked"], 3)
        self.assertEqual(result["matched"], 3)
        self.assertEqual(result["verified_direction_accuracy"], 1.0)

    def test_bad_direction_not_counted(self):
        data = [{"type": "table", "checked": "verified", "cell": "품목", "left": "수량"}]
        self.assertEqual(check_verified_table_adjacency(pairs(), data)["matched"], 0)

    def test_ambiguous_reference_blocks(self):
        dup = pairs() + line(5, 350, 10, "품목")
        data = [{"type": "table", "checked": "verified", "cell": "품목", "right": "수량"}]
        self.assertEqual(check_verified_table_adjacency(dup, data)["matched"], 0)

    def test_missing_or_invalid_tsv_fails_closed(self):
        with self.assertRaises(ValueError):
            read_tsv_lines("not TSV")
        data = [{"type": "table", "checked": "verified", "cell": "품목", "right": "수량"}]
        self.assertEqual(check_verified_table_adjacency(HEAD, data)["matched"], 0)

    def test_unverified_input_blocked(self):
        with self.assertRaises(ValueError):
            check_verified_table_adjacency(pairs(), [
                {"type": "table", "checked": "unreviewed", "cell": "품목", "right": "수량"}
            ])


if __name__ == "__main__":
    unittest.main()
