"""Regression checks for runner reconstruction and alignment leakage."""

import unittest

from validate_mlb_alignment import apply_movements, align_pa


def movement(player, start, end, out=False, scoring=False):
    return {"movement": {"start": start, "end": end, "isOut": out},
            "details": {"runner": {"id": player}, "isScoringEvent": scoring}}


def candle(ts):
    return {"end_period_ts": ts, "end_period_utc": str(ts), "home_bid": .40,
            "home_ask": .42, "home_mid": .41, "spread": .02}


class AlignmentTests(unittest.TestCase):
    def test_runner_scoring_after_intermediate_base_does_not_leave_phantom_runner(self):
        state = {"home": 0, "away": 0, "outs": 1, "bases": {"2B": 11}}
        apply_movements(state, [movement(11, "2B", "3B"), movement(11, "3B", "score", scoring=True),
                                movement(22, None, "2B")], "home")
        self.assertEqual(state, {"home": 1, "away": 0, "outs": 1, "bases": {"2B": 22}})

    def test_double_play_leaves_uninvolved_runner_in_place(self):
        state = {"home": 0, "away": 0, "outs": 0, "bases": {"1B": 11, "2B": 33}}
        apply_movements(state, [movement(11, "1B", None, out=True),
                                movement(22, None, None, out=True)], "away")
        self.assertEqual(state["outs"], 2)
        self.assertEqual(state["bases"], {"2B": 33})

    def test_backward_quote_before_previous_play_finished_is_rejected(self):
        pa = {"anchor_ts": 150, "state_ready_ts": 130}
        row = align_pa([pa], [candle(120), candle(180)])[0]
        self.assertEqual(row["quote_end_ts"], 120)
        self.assertTrue(row["age_ok"])
        self.assertFalse(row["same_recorded_state"])
        self.assertFalse(row["eligible"])

    def test_quote_at_anchor_is_excluded_and_safety_lag_changes_selection(self):
        pa = {"anchor_ts": 180, "state_ready_ts": 100}
        row = align_pa([pa], [candle(60), candle(120), candle(180)])[0]
        self.assertEqual(row["quote_end_ts"], 120)
        self.assertTrue(row["eligible"])
        lagged = align_pa([pa], [candle(60), candle(120), candle(180)], lag=60)[0]
        self.assertEqual(lagged["quote_end_ts"], 60)
        self.assertFalse(lagged["same_recorded_state"])


if __name__ == "__main__":
    unittest.main()
