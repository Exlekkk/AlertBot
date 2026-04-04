import unittest


class ABCConfidenceRefactorTests(unittest.TestCase):
    def test_a_confidence_only_high_when_clean(self):
        from engine.signals import _abc_confidence
        clean = _abc_confidence("A_LONG", "long", "bull", "continuation", "explosive", ["bos_up", "mss_up", "fvg"])
        weak = _abc_confidence("A_LONG", "long", "lean_bull", "continuation", "watch", ["fvg"])
        self.assertGreaterEqual(clean, 74)
        self.assertLess(weak, clean)
        self.assertLessEqual(clean, 89)

    def test_b_confidence_not_artificially_high(self):
        from engine.signals import _abc_confidence
        b_value = _abc_confidence("B_PULLBACK_SHORT", "short", "lean_bear", "repair", "ready", ["resistance_zone", "trigger_repair"])
        self.assertGreaterEqual(b_value, 58)
        self.assertLessEqual(b_value, 76)

    def test_c_confidence_stays_low_to_mid(self):
        from engine.signals import _abc_confidence
        c_value = _abc_confidence("C_LEFT_LONG", "long", "neutral", "early", "probe", ["support_zone", "early_warning"])
        self.assertGreaterEqual(c_value, 50)
        self.assertLessEqual(c_value, 70)

    def test_counter_trend_a_gets_pulled_down(self):
        from engine.signals import _abc_confidence
        normal = _abc_confidence("A_SHORT", "short", "bear", "continuation", "explosive", ["bos_down", "mss_down", "resistance_zone"])
        counter = _abc_confidence("A_SHORT", "short", "lean_bull", "continuation", "explosive", ["bos_down", "mss_down", "resistance_zone"])
        self.assertLess(counter, normal)


if __name__ == "__main__":
    unittest.main()
