import unittest
from ocr_evolution.evaluator import Case, evaluate
from ocr_evolution.cycle import run_cycle

class EvolutionTests(unittest.TestCase):
    def test_improvement_requires_holdout(self):
        b=[Case("a","HELLO","HELO")]
        c=[Case("a","HELLO","HELLO")]
        r=run_cycle(b,c,"cycle-001")
        self.assertEqual(r["decision"],"CANDIDATE_ELIGIBLE_FOR_HUMAN_REVIEW")
        self.assertFalse(r["applied"])
    def test_regression_blocks(self):
        b=[Case("a","HELLO","HELLO"),Case("b","WORLD","WORL")]
        c=[Case("a","HELLO","HELO"),Case("b","WORLD","WORLD")]
        self.assertEqual(run_cycle(b,c,"cycle-002")["decision"],"BLOCKED")
    def test_training_split_blocks(self):
        with self.assertRaises(ValueError):
            evaluate([Case("a","x","x","train")],[Case("a","x","x","train")])
    def test_mismatch_blocks(self):
        with self.assertRaises(ValueError):
            evaluate([Case("a","x","x")],[Case("a","y","y")])
    def test_duplicate_blocks(self):
        with self.assertRaises(ValueError):
            evaluate([Case("a","x","x"),Case("a","x","x")],[Case("a","x","x"),Case("a","x","x")])
if __name__=="__main__":
    unittest.main()
