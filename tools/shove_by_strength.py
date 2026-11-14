"""Our own preflop shoves and raises, split by hand strength: placement points gained per hand.

We know the three cards we were dealt each hand, so we can look up the hand's top-percent rank.
Answers the question: do shoves with weak hands actually make money?

Run:  python tools/shove_by_strength.py history/round1.jsonl.gz
"""

import gzip
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands3  # noqa: E402

STRENGTHS = ["top 10%", "10-25%", "25-50%", "50-100%"]
STACKS = ["<8", "8-12", "12-20", "20-40", "40+"]


def strength_of(pct):
    if pct <= 10:
        return "top 10%"
    if pct <= 25:
        return "10-25%"
    if pct <= 50:
        return "25-50%"
    return "50-100%"


def stack_of(stack, big_blind):
    value = stack / float(big_blind)
    if value < 8:
        return "<8"
    if value < 12:
        return "8-12"
    if value < 20:
        return "12-20"
    if value < 40:
        return "20-40"
    return "40+"


def main():
    path = sys.argv[1]
    with open(os.path.join(ROOT, "bot", "nl26", "data", "pgh_tables.json")) as handle:
        pct_table = json.load(handle)["pct"]
    data = defaultdict(lambda: [0, 0.0])
    tables = 0
    with gzip.open(path, "rt") as handle:
        handle.readline()
        while True:
            line = handle.readline()
            if not line:
                break
            table = json.loads(line)
            own = json.loads(handle.readline())["you"]
            me = own["seat"]
            if table["fillers"][me]:
                continue
            tables += 1
            for index in range(len(table["hands"])):
                hand = table["hands"][index]
                cards = own["cards"][index]
                before = hand["stacks_before"][me]
                if before <= 0 or len(cards) != 3:
                    continue
                big_blind = hand["blinds"][1]
                raises = 0
                kind_of_shove = None
                for event in hand["events"]:
                    kind = event["kind"]
                    if kind == "board":
                        break
                    if kind != "raise":
                        continue
                    if event.get("seat") == me:
                        if event.get("amount", 0) >= 0.9 * before:
                            if raises == 0:
                                kind_of_shove = "open shove"
                            elif raises == 1:
                                kind_of_shove = "re-shove over a raise"
                        elif raises == 1:
                            kind_of_shove = "small re-raise"
                        elif raises == 0:
                            kind_of_shove = "small open raise"
                        break
                    raises += 1
                if kind_of_shove is None:
                    continue
                pct = pct_table[hands3.class_index3(cards[0], cards[1], cards[2])]
                delta = hand["equity_after"][me] - hand["equity_before"][me]
                record = data[(kind_of_shove, stack_of(before, big_blind), strength_of(pct))]
                record[0] += 1
                record[1] += delta

    print("tables scored:", tables, "  each cell: placement points per hand (times per 100 tables)")
    for kind_of_shove in ("open shove", "re-shove over a raise", "small re-raise", "small open raise"):
        print(kind_of_shove)
        print("  stack     " + "".join("%-22s" % name for name in STRENGTHS))
        for stack in STACKS:
            cells = []
            for strength in STRENGTHS:
                count, total = data[(kind_of_shove, stack, strength)]
                if count >= 30:
                    cells.append("%+6.2f (%5.1fx)       " % (total / count, 100.0 * count / tables))
                else:
                    cells.append("   -                   ")
            print("  %-6s    %s" % (stack, "".join(cells)))


if __name__ == "__main__":
    main()
