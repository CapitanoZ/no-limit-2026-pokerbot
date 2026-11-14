"""Compare two discard rules: all in preflop, run to showdown, average share of the pot.

The opponent always uses the old rule (only what the hand has made so far). We play the same
deals once with the old rule and once with the new one.
Also times one call of the new rule.

Run:  python tools/compare_discard.py
"""

import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import pgh  # noqa: E402

DEALS = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
PASSES = int(sys.argv[1]) if len(sys.argv) > 1 else 2


def share_of(tables, keep, opponent_keep, board_a, board_b):
    cards = tables.cards
    evaluate = tables.evaluate
    points = 0
    for board in (board_a, board_b):
        mine = []
        for name in keep:
            mine.append(cards[name])
        theirs = []
        for name in opponent_keep:
            theirs.append(cards[name])
        full = []
        for name in board:
            full.append(cards[name])
        a = evaluate(mine + full)
        b = evaluate(theirs + full)
        if a > b:
            points += 2
        elif a == b:
            points += 1
    return points / 4.0


def keep_after(hole, drop):
    result = []
    for index in range(3):
        if index != drop:
            result.append(hole[index])
    return result


def main():
    tables = pgh.Tables()
    rng = random.Random(5)
    old_total = 0.0
    new_total = 0.0
    different = 0
    spent = []
    for _ in range(DEALS):
        deal = rng.sample(tables.names, 16)
        hero = deal[0:3]
        villain = deal[3:6]
        board_a = deal[6:11]
        board_b = deal[11:16]
        turn = (board_a[0:4], board_b[0:4])

        villain_drop, _, _ = pgh.keep_scores(tables, villain, turn)
        villain_keep = keep_after(villain, villain_drop)

        old_drop, _, _ = pgh.keep_scores(tables, hero, turn)
        start = time.perf_counter_ns()
        new_drop, _, _ = pgh.sampled_strength(tables, hero, turn, PASSES)
        spent.append(time.perf_counter_ns() - start)
        if old_drop != new_drop:
            different += 1
        old_total += share_of(tables, keep_after(hero, old_drop), villain_keep, board_a, board_b)
        new_total += share_of(tables, keep_after(hero, new_drop), villain_keep, board_a, board_b)

    spent.sort()
    print("dealt %d hands" % DEALS)
    print("old rule: average pot share %.2f%%" % (100.0 * old_total / DEALS))
    print("new rule: average pot share %.2f%%" % (100.0 * new_total / DEALS))
    print("the two rules discard a different card in %.1f%% of deals" % (100.0 * different / DEALS))
    print("new rule, one call: median %.0f us, p99 %.0f us, max %.0f us"
          % (spent[len(spent) // 2] / 1000.0, spent[int(len(spent) * 0.99)] / 1000.0, spent[-1] / 1000.0))


if __name__ == "__main__":
    main()
