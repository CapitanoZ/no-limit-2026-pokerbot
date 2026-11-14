"""How the share of our stack invested postflop relates to results, and how early busts happen.

Run:  python tools/postflop_risk.py history/practice4.jsonl.gz
"""

import gzip
import json
import sys
from collections import defaultdict

LEVELS = ["under 10%", "10% to 30%", "30% to 70%", "over 70%"]


def level_of(fraction):
    if fraction < 0.1:
        return "under 10%"
    if fraction < 0.3:
        return "10% to 30%"
    if fraction < 0.7:
        return "30% to 70%"
    return "over 70%"


def main():
    path = sys.argv[1]
    tables = 0
    by_level = defaultdict(lambda: [0, 0.0])
    by_level_deep = defaultdict(lambda: [0, 0.0])
    early_bust = defaultdict(int)
    early_tables = 0
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
            for hand in table["hands"]:
                before = hand["stacks_before"][me]
                if before <= 0:
                    continue
                big_blind = hand["blinds"][1]
                street = 0
                put_in = 0
                street_bet = 0
                put_postflop = 0
                pre_all_in = False
                acted_postflop = False
                for event in hand["events"]:
                    kind = event["kind"]
                    if kind == "board":
                        if event.get("amount") == 1:
                            street += 1
                            street_bet = 0
                        continue
                    if event.get("seat") != me:
                        continue
                    amount = event.get("amount", 0)
                    added = 0
                    if kind in ("blind", "ante", "call"):
                        added = amount
                        street_bet += amount
                    elif kind == "raise":
                        added = amount - street_bet
                        street_bet = amount
                    put_in += added
                    if street == 0 and put_in >= 0.9 * before:
                        pre_all_in = True
                    if street > 0 and kind in ("check", "call", "raise", "fold"):
                        acted_postflop = True
                        put_postflop += added
                delta = hand["equity_after"][me] - hand["equity_before"][me]
                if acted_postflop and not pre_all_in:
                    name = level_of(put_in / float(before))
                    record = by_level[name]
                    record[0] += 1
                    record[1] += delta
                    if before >= 20 * big_blind:
                        record = by_level_deep[name]
                        record[0] += 1
                        record[1] += delta
                if hand["stacks_after"][me] == 0 and hand["hand"] <= 60:
                    early_tables += 1
                    if pre_all_in:
                        early_bust["all in preflop"] += 1
                    elif acted_postflop:
                        early_bust["lost the stack postflop"] += 1
                    else:
                        early_bust["other"] += 1

    print("tables scored:", tables)
    print("Hands that saw a flop, by share of our stack put in during the hand (preflop all-ins excluded):")
    for name in LEVELS:
        count, total = by_level[name]
        deep_count, deep_total = by_level_deep[name]
        print("  %-10s %5.2f hands/table   %+6.2f pts/table   %+7.3f pts/hand    "
              "with 20+ big blinds: %5.2f hands/table, %+6.2f pts"
              % (name, count / float(tables), total / tables, total / max(1, count),
                 deep_count / float(tables), deep_total / tables))
    print("busted within the first 60 hands: %d tables (%.1f%%)"
          % (early_tables, 100.0 * early_tables / tables))
    for name in early_bust:
        print("  %-24s %d tables (%.1f%%)" % (name, early_bust[name], 100.0 * early_bust[name] / tables))


if __name__ == "__main__":
    main()
