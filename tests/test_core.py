"""Tests for the generic building blocks.

Run:  python -m unittest discover -s tests -v
"""

import itertools
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands, icm, pushfold, safety, table_memory  # noqa: E402

PAYOUTS = [50, 30, 20]


def brute_force_points(stacks, me, payouts):
    """Brute force: enumerate every finishing order and its probability. Used to check icm.my_points."""
    alive = []
    for seat in range(len(stacks)):
        if stacks[seat] > 0:
            alive.append(seat)
    value = 0.0
    for order in itertools.permutations(alive):
        chance = 1.0
        remaining = 0
        for seat in alive:
            remaining += stacks[seat]
        for seat in order:
            chance *= stacks[seat] / remaining
            remaining -= stacks[seat]
        place = order.index(me)
        if place < len(payouts):
            value += chance * payouts[place]
    return value


class IcmTest(unittest.TestCase):
    def test_equal_stacks_split_evenly(self):
        stacks = [2000] * 8
        self.assertAlmostEqual(icm.my_points(stacks, 3, PAYOUTS), 100 / 8)

    def test_matches_brute_force(self):
        stacks = [5200, 0, 3100, 900, 0, 4400, 2400, 0]
        for me in (0, 2, 3, 5, 6):
            self.assertAlmostEqual(
                icm.my_points(stacks, me, PAYOUTS),
                brute_force_points(stacks, me, PAYOUTS),
                places=9,
            )

    def test_points_add_up_to_all_payouts(self):
        stacks = [7000, 2500, 0, 1500, 3000, 0, 1200, 800]
        total = 0.0
        for value in icm.all_points(stacks, PAYOUTS):
            total += value
        self.assertAlmostEqual(total, 100.0)

    def test_two_players_left(self):
        # two players left: the one with 3/4 of the chips gets 50 points 3/4 of the time, 30 otherwise
        stacks = [12000, 0, 0, 4000, 0, 0, 0, 0]
        self.assertAlmostEqual(icm.my_points(stacks, 0, PAYOUTS), 0.75 * 50 + 0.25 * 30)

    def test_winner_takes_first_place(self):
        stacks = [0, 0, 16000, 0, 0, 0, 0, 0]
        self.assertAlmostEqual(icm.my_points(stacks, 2, PAYOUTS), 50)

    def test_just_busted(self):
        # my stack is 0 and 2 players are alive: I finish 3rd and get 20 points
        self.assertAlmostEqual(icm.my_points([0, 9000, 7000, 0], 0, PAYOUTS), 20)
        # 3 players are alive: I finish 4th and get nothing
        self.assertAlmostEqual(icm.my_points([0, 6000, 6000, 4000], 0, PAYOUTS), 0)

    def test_more_than_three_paid_places(self):
        payouts = [40, 25, 15, 12, 8]
        stacks = [3000, 1000, 2500, 500, 4000, 0]
        for me in (0, 1, 3):
            self.assertAlmostEqual(
                icm.my_points(stacks, me, payouts),
                brute_force_points(stacks, me, payouts),
                places=9,
            )

    def test_more_chips_is_worth_less_per_chip(self):
        # a property of placement points: doubling the chips does not double the points
        small = icm.my_points([2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000], 0, PAYOUTS)
        big = icm.my_points([4000, 0, 2000, 2000, 2000, 2000, 2000, 2000], 0, PAYOUTS)
        self.assertGreater(big, small)
        self.assertLess(big, 2 * small)


class HandsTest(unittest.TestCase):
    def test_169_classes_cover_1326_combos(self):
        names = set()
        total = 0
        for index in range(169):
            names.add(hands.class_name(index))
            total += hands.class_combos(index)
            self.assertEqual(len(hands.all_combos(index)), hands.class_combos(index))
        self.assertEqual(len(names), 169)
        self.assertEqual(total, 1326)

    def test_class_of_cards(self):
        self.assertEqual(hands.class_name(hands.class_index("As", "Kd")), "AKo")
        self.assertEqual(hands.class_name(hands.class_index("Kd", "As")), "AKo")
        self.assertEqual(hands.class_name(hands.class_index("Th", "Jh")), "JTs")
        self.assertEqual(hands.class_name(hands.class_index("7c", "7d")), "77")

    def test_every_combo_maps_back(self):
        for index in range(169):
            for combo in hands.all_combos(index):
                self.assertEqual(hands.class_index(combo[0], combo[1]), index)

    def test_blocked_combos(self):
        ak = hands.class_index("As", "Kh")
        aa = hands.class_index("Ah", "Ad")
        self.assertEqual(hands.compatible_combos(ak, aa), 3)
        self.assertEqual(hands.compatible_combos(aa, aa), 1)


class FakeLegal:
    def __init__(self, kind, min_amount=0, max_amount=0):
        self.kind = kind
        self.min_amount = min_amount
        self.max_amount = max_amount


class FakeEnum:
    def __init__(self, value):
        self.value = value


class SafetyTest(unittest.TestCase):
    def test_kind_name_handles_strings_and_enums(self):
        self.assertEqual(safety.kind_name("Raise"), "raise")
        self.assertEqual(safety.kind_name(FakeEnum("fold")), "fold")

    def test_fallback_prefers_check_then_fold(self):
        check = FakeLegal("check")
        fold = FakeLegal("fold")
        call = FakeLegal("call", 200, 200)
        self.assertIs(safety.pick_fallback([call, check]), check)
        self.assertIs(safety.pick_fallback([call, fold]), fold)
        self.assertIs(safety.pick_fallback([call]), call)
        self.assertIsNone(safety.pick_fallback([]))

    def test_clamp_amount(self):
        self.assertEqual(safety.clamp_amount(399.9, 400, 2000), 400)
        self.assertEqual(safety.clamp_amount(5000, 400, 2000), 2000)
        self.assertEqual(safety.clamp_amount(850.7, 400, 2000), 850)
        self.assertIs(type(safety.clamp_amount(850.7, 400, 2000)), int)

    def test_resolve_raise(self):
        legal = [FakeLegal("fold"), FakeLegal("call", 200, 200), FakeLegal("raise", 400, 2000)]
        found, amount = safety.resolve(legal, "raise", 100)
        self.assertEqual(found.kind, "raise")
        self.assertEqual(amount, 400)

    def test_resolve_steps_down_when_not_legal(self):
        legal = [FakeLegal("fold"), FakeLegal("call", 200, 200)]
        found, amount = safety.resolve(legal, "raise", 900)
        self.assertEqual(found.kind, "call")
        self.assertEqual(amount, 200)

        legal = [FakeLegal("check"), FakeLegal("raise", 40, 2000)]
        found, amount = safety.resolve(legal, "call", 0)
        self.assertEqual(found.kind, "check")

        found, amount = safety.resolve(legal, "fold", 0)
        self.assertEqual(found.kind, "check")

        self.assertIsNone(safety.resolve([], "fold", 0))


class FakeEvent:
    def __init__(self, kind, seat=None, amount=0, cards=None):
        self.kind = kind
        self.seat = seat
        self.amount = amount
        self.cards = cards


class TableMemoryTest(unittest.TestCase):
    def test_empty_and_broken_memory_give_fresh_stats(self):
        for memory in (b"", b"garbage", b"\x00" * table_memory.SIZE, None, 12345):
            stats = table_memory.decode(memory)
            self.assertEqual(stats.hand_number, 0)
            self.assertEqual(stats.seats[0][table_memory.HANDS], 0)

    def test_round_trip(self):
        stats = table_memory.TableStats()
        stats.hand_number = 77
        stats.street = 2
        stats.raise_seen = True
        stats.seats[4][table_memory.VPIP] = 9
        stats.seats[9][table_memory.FOLD_TO_RAISE] = 65535
        memory = table_memory.encode(stats)
        self.assertEqual(len(memory), table_memory.SIZE)
        again = table_memory.decode(memory)
        self.assertEqual(again.hand_number, 77)
        self.assertEqual(again.street, 2)
        self.assertTrue(again.raise_seen)
        self.assertEqual(again.seats, stats.seats)

    def test_counts_one_hand(self):
        stats = table_memory.TableStats()
        events = [
            FakeEvent("hand", None, 5),
            FakeEvent("blind", 0, 10),
            FakeEvent("blind", 1, 20),
            FakeEvent("call", 2, 20),     # seat 2 limps
            FakeEvent("raise", 3, 80),    # seat 3 raises
            FakeEvent("fold", 4),         # seat 4 folds to the raise
            FakeEvent("some_new_kind", 5, 1),
            FakeEvent("fold", 0),
            FakeEvent("call", 1, 60),     # the big blind calls
            FakeEvent("fold", 2),         # seat 2 folds to the raise
            FakeEvent("board", None, 0, ["As", "Kd", "2c"]),
            FakeEvent("check", 1),
            FakeEvent("raise", 3, 100),   # a postflop bet does not count as a preflop raise
            FakeEvent("call", 1, 100),
            FakeEvent("show", 3, 0, ["Ah", "Ad"]),
            FakeEvent("show", 1, 0, ["Ks", "Qs"]),
            FakeEvent("win", 3, 400),
        ]
        table_memory.update(stats, events)
        seats = stats.seats
        self.assertEqual(stats.hand_number, 5)
        for seat in (0, 1, 2, 3, 4):
            self.assertEqual(seats[seat][table_memory.HANDS], 1)
        self.assertEqual(seats[5][table_memory.HANDS], 0)
        self.assertEqual(seats[2][table_memory.VPIP], 1)
        self.assertEqual(seats[3][table_memory.VPIP], 1)
        self.assertEqual(seats[3][table_memory.PFR], 1)
        self.assertEqual(seats[1][table_memory.VPIP], 1)
        self.assertEqual(seats[1][table_memory.PFR], 0)
        self.assertEqual(seats[4][table_memory.FACED_RAISE], 1)
        self.assertEqual(seats[4][table_memory.FOLD_TO_RAISE], 1)
        self.assertEqual(seats[1][table_memory.FACED_RAISE], 1)
        self.assertEqual(seats[1][table_memory.FOLD_TO_RAISE], 0)
        self.assertEqual(seats[2][table_memory.FOLD_TO_RAISE], 1)
        self.assertEqual(seats[3][table_memory.SHOWDOWNS], 1)
        self.assertEqual(seats[1][table_memory.SHOWDOWNS], 1)

    def test_events_split_across_turns(self):
        # events of one hand delivered in two batches must give the same result as one batch
        first = [FakeEvent("hand", None, 1), FakeEvent("blind", 0, 10), FakeEvent("raise", 2, 60)]
        second = [FakeEvent("fold", 3), FakeEvent("call", 0, 50), FakeEvent("call", 0, 50)]
        stats = table_memory.TableStats()
        table_memory.update(stats, first)
        stats = table_memory.decode(table_memory.encode(stats))
        table_memory.update(stats, second)
        self.assertEqual(stats.seats[3][table_memory.FOLD_TO_RAISE], 1)
        self.assertEqual(stats.seats[0][table_memory.HANDS], 1)
        self.assertEqual(stats.seats[0][table_memory.VPIP], 1)

    def test_rate_with_little_data_stays_near_prior(self):
        stats = table_memory.TableStats()
        stats.seats[1][table_memory.FACED_RAISE] = 1
        stats.seats[1][table_memory.FOLD_TO_RAISE] = 1
        rate = stats.rate(1, table_memory.FOLD_TO_RAISE, table_memory.FACED_RAISE, 0.6, 10)
        self.assertGreater(rate, 0.6)
        self.assertLess(rate, 0.7)


class PushFoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = pushfold.Tables()
        cls.aces = hands.class_index("As", "Ah")
        cls.trash = hands.class_index("7s", "2h")

    def test_tables_look_sane(self):
        tables = self.tables
        self.assertEqual(len(tables.eq_top), 101)
        self.assertEqual(hands.class_name(tables.order[0]), "AA")
        # a pair of aces is ahead of any range
        self.assertGreater(tables.eq_top[100][self.aces], 0.8)
        self.assertLess(tables.eq_top[5][self.trash], 0.3)
        # heads-up with 10 big blinds each: accepted theory is to shove about 58% and call about 37%
        self.assertTrue(50 < tables.default_push_pct(1, 10) < 65)
        self.assertTrue(30 < tables.default_call_pct(1, "bb", 10) < 45)
        # the earlier the position (more players behind), the fewer hands shove
        self.assertLess(tables.default_push_pct(7, 10), tables.default_push_pct(2, 10))

    def scenario(self, big_blind):
        # 8 players with 2000 chips each; I act first in seat 0; seats 6 and 7 are the blinds
        stacks = [2000] * 8
        posted = [0] * 8
        posted[6] = big_blind // 2
        posted[7] = big_blind
        callers = [1, 2, 3, 4, 5, 6, 7]
        return stacks, posted, callers

    def test_aces_always_push(self):
        stacks, posted, callers = self.scenario(200)
        edge = pushfold.push_edge(
            self.tables, self.aces, stacks, posted, 0, callers, [10] * 7, [50, 30, 20]
        )
        self.assertGreater(edge, 0)

    def test_trash_first_to_act_folds(self):
        stacks, posted, callers = self.scenario(200)
        edge = pushfold.push_edge(
            self.tables, self.trash, stacks, posted, 0, callers, [10] * 7, [50, 30, 20]
        )
        self.assertLess(edge, 0)

    def test_early_all_in_with_trash_loses(self):
        # a play we considered: shoving junk at 10/20 blinds. It loses even if only the top 2% call
        stacks, posted, callers = self.scenario(20)
        edge = pushfold.push_edge(
            self.tables, self.trash, stacks, posted, 0, callers, [2] * 7, [50, 30, 20]
        )
        self.assertLess(edge, 0)

    def test_nobody_calls_means_free_blinds(self):
        stacks, posted, callers = self.scenario(200)
        edge = pushfold.push_edge(
            self.tables, self.trash, stacks, posted, 0, callers, [0] * 7, [50, 30, 20]
        )
        self.assertGreater(edge, 0)

    def test_tighter_callers_help_the_pusher(self):
        stacks, posted, callers = self.scenario(200)
        loose = pushfold.push_edge(
            self.tables, self.trash, stacks, posted, 0, callers, [30] * 7, [50, 30, 20]
        )
        tight = pushfold.push_edge(
            self.tables, self.trash, stacks, posted, 0, callers, [3] * 7, [50, 30, 20]
        )
        self.assertGreater(tight, loose)

    def test_inputs_are_not_modified(self):
        stacks, posted, callers = self.scenario(200)
        stacks_before = list(stacks)
        posted_before = list(posted)
        pushfold.push_edge(
            self.tables, self.aces, stacks, posted, 0, callers, [10] * 7, [50, 30, 20]
        )
        self.assertEqual(stacks, stacks_before)
        self.assertEqual(posted, posted_before)

    def test_call_with_aces_fold_with_trash(self):
        # seat 3 shoves 2000 and I am the big blind (seat 7)
        stacks = [2000] * 8
        posted = [0] * 8
        posted[6] = 100
        posted[7] = 200
        posted[3] = 2000
        good = pushfold.call_edge(self.tables, self.aces, stacks, posted, 7, 3, 15, [50, 30, 20])
        bad = pushfold.call_edge(self.tables, self.trash, stacks, posted, 7, 3, 15, [50, 30, 20])
        self.assertGreater(good, 0)
        self.assertLess(bad, 0)

    def test_bubble_makes_calling_tighter(self):
        # 4 players left and the top 3 are paid: one very short stack is about to bust.
        # Here I must be more careful calling a shove than chip EV alone would suggest.
        hand = hands.class_index("Ah", "Td")
        stacks = [5000, 5000, 5700, 300, 0, 0, 0, 0]
        posted = [5000, 400, 0, 0, 0, 0, 0, 0]
        with_places = pushfold.call_edge(self.tables, hand, stacks, posted, 1, 0, 40, [50, 30, 20])
        winner_takes_all = pushfold.call_edge(self.tables, hand, stacks, posted, 1, 0, 40, [100])
        self.assertGreater(winner_takes_all, 0)
        self.assertLess(with_places, 0)


if __name__ == "__main__":
    unittest.main()
