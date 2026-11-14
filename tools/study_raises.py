"""Study how one team plays after someone's small raise: when it re-raises small or re-shoves,
and how that turns out.

Only this spot is counted: preflop, exactly one player has made a small raise (not a shove),
and it is this team's turn.

Run:  python tools/study_raises.py "Pluto" history/round1.jsonl.gz [more history files]
"""

import gzip
import json
import sys
from collections import defaultdict

RANKS = "23456789TJQKA"
BUCKETS = ["<8", "8-12", "12-20", "20-40", "40+"]


def bucket(stack, big_blind):
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


def pct(count, total):
    if total == 0:
        return "  - "
    return "%3.0f%%" % (100.0 * count / total)


def read_tables(path):
    with gzip.open(path, "rt") as handle:
        header = json.loads(handle.readline())
        names = {}
        for entry in header["entries"]:
            names[entry["entry_id"]] = entry["team_name"]
        while True:
            line = handle.readline()
            if not line:
                break
            table = json.loads(line)
            if not handle.readline():
                break
            yield names, table


def main():
    team = sys.argv[1]
    paths = sys.argv[2:]

    # chances and choices: key is (stack bucket, position), value is counts per action
    choices = defaultdict(lambda: defaultdict(int))
    choices_by_size = defaultdict(lambda: defaultdict(int))
    choices_by_behind = defaultdict(lambda: defaultdict(int))
    # results: key is (action, stack bucket),
    # value is [count, total points change, everyone folded, got called, got re-raised]
    results = defaultdict(lambda: [0, 0.0, 0, 0, 0])
    result_by_outcome = defaultdict(lambda: [0, 0.0])
    shown = defaultdict(lambda: [0, 0, 0, 0])   # action -> [showdowns, pair, has an ace, both T+]
    tables = 0

    for path in paths:
        for names, table in read_tables(path):
            seat = -1
            for index in range(len(table["seats"])):
                if names.get(table["seats"][index]) == team and not table["fillers"][index]:
                    seat = index
            if seat < 0:
                continue
            tables += 1
            for hand in table["hands"]:
                before = hand["stacks_before"]
                if before[seat] <= 0:
                    continue
                big_blind = hand["blinds"][1]
                raises = 0
                opener = -1
                open_size = 0.0
                open_all_in = False
                my_action = None
                my_bucket = None
                continued = 0      # calls by others after my action
                reraised = 0       # re-raises by others after my action
                in_blinds = False
                folded = set()
                acted_after_open = set()
                events = hand["events"]
                done = False
                for event in events:
                    kind = event["kind"]
                    who = event.get("seat")
                    amount = event.get("amount", 0)
                    if kind == "board":
                        break
                    if kind == "blind":
                        if who == seat:
                            in_blinds = True
                        continue
                    if kind not in ("fold", "check", "call", "raise"):
                        continue
                    if my_action is not None and who != seat:
                        if kind == "call":
                            continued += 1
                        elif kind == "raise":
                            reraised += 1
                        continue
                    if who == seat and my_action is None and raises == 1 and not open_all_in:
                        my_bucket = bucket(before[seat], big_blind)
                        position = "in the blinds" if in_blinds else "not in the blinds"
                        alive = 0
                        for other in range(len(before)):
                            if before[other] > 0 and other != seat and other != opener \
                                    and other not in folded and other not in acted_after_open:
                                alive += 1
                        if kind == "fold":
                            name = "fold"
                        elif kind == "call":
                            name = "call"
                        elif kind == "raise" and amount >= 0.9 * before[seat]:
                            name = "re-shove"
                        else:
                            name = "small re-raise"
                        choices[(my_bucket, position)][name] += 1
                        size_key = "raise under 2.3x" if open_size < 2.3 else (
                            "2.3x to 3x" if open_size <= 3.0 else "over 3x")
                        choices_by_size[(my_bucket, size_key)][name] += 1
                        behind_key = "nobody behind" if alive == 0 else (
                            "1 behind" if alive == 1 else "2+ behind")
                        choices_by_behind[(my_bucket, behind_key)][name] += 1
                        if name in ("re-shove", "small re-raise"):
                            my_action = name
                        else:
                            done = True
                        continue
                    if kind == "fold":
                        folded.add(who)
                    if raises == 1 and who != opener:
                        acted_after_open.add(who)
                    if kind == "raise":
                        raises += 1
                        if raises == 1:
                            opener = who
                            open_size = amount / float(big_blind)
                            open_all_in = amount >= 0.9 * before[who]
                    if done:
                        break

                if my_action is None:
                    continue
                delta = hand["equity_after"][seat] - hand["equity_before"][seat]
                record = results[(my_action, my_bucket)]
                record[0] += 1
                record[1] += delta
                if reraised > 0:
                    outcome = "re-raised or shoved on"
                    record[4] += 1
                elif continued > 0:
                    outcome = "called"
                    record[3] += 1
                else:
                    outcome = "everyone folds"
                    record[2] += 1
                item = result_by_outcome[(my_action, outcome)]
                item[0] += 1
                item[1] += delta
                for event in events:
                    if event["kind"] == "show" and event.get("seat") == seat:
                        cards = event.get("cards", [])
                        if len(cards) == 2:
                            stat = shown[my_action]
                            stat[0] += 1
                            first = RANKS.index(cards[0][0])
                            second = RANKS.index(cards[1][0])
                            if first == second:
                                stat[1] += 1
                            if first == 12 or second == 12:
                                stat[2] += 1
                            if first >= 8 and second >= 8:
                                stat[3] += 1
                        break

    print("=== %s ===  %d tables" % (team, tables))
    print("Its choice after someone's small raise (by stack and position):"
          "   fold   call   small re-raise   re-shove   count")
    for name in BUCKETS:
        for position in ("not in the blinds", "in the blinds"):
            counts = choices[(name, position)]
            total = counts["fold"] + counts["call"] + counts["small re-raise"] + counts["re-shove"]
            if total:
                print("  %-6s %-6s   %s   %s     %s        %s     %6d"
                      % (name, position, pct(counts["fold"], total), pct(counts["call"], total),
                         pct(counts["small re-raise"], total), pct(counts["re-shove"], total), total))
    print("By the size of the raise it faces:")
    for name in BUCKETS:
        for size_key in ("raise under 2.3x", "2.3x to 3x", "over 3x"):
            counts = choices_by_size[(name, size_key)]
            total = counts["fold"] + counts["call"] + counts["small re-raise"] + counts["re-shove"]
            if total >= 30:
                print("  %-6s %-16s small re-raise %s   re-shove %s   count %6d"
                      % (name, size_key, pct(counts["small re-raise"], total),
                         pct(counts["re-shove"], total), total))
    print("By how many players are still to act behind it:")
    for name in BUCKETS:
        for behind_key in ("nobody behind", "1 behind", "2+ behind"):
            counts = choices_by_behind[(name, behind_key)]
            total = counts["fold"] + counts["call"] + counts["small re-raise"] + counts["re-shove"]
            if total >= 30:
                print("  %-6s %-14s small re-raise %s   re-shove %s   count %6d"
                      % (name, behind_key, pct(counts["small re-raise"], total),
                         pct(counts["re-shove"], total), total))
    print("Results:")
    for action in ("small re-raise", "re-shove"):
        for name in BUCKETS:
            count, total, folds, calls, fights = results[(action, name)]
            if count >= 20:
                print("  %-14s stack %-6s n %6d   %+6.3f pts/hand   all fold %s   called %s   re-raised %s"
                      % (action, name, count, total / count, pct(folds, count), pct(calls, count), pct(fights, count)))
        for outcome in ("everyone folds", "called", "re-raised or shoved on"):
            count, total = result_by_outcome[(action, outcome)]
            if count:
                print("      after %s, %-22s: n %6d, %+6.3f pts/hand"
                      % (action, outcome, count, total / count))
        stat = shown[action]
        if stat[0]:
            print("      cards shown at showdown after %s (%d times): pair %s, has an ace %s, both T+ %s"
                  % (action, stat[0], pct(stat[1], stat[0]), pct(stat[2], stat[0]), pct(stat[3], stat[0])))


if __name__ == "__main__":
    main()
