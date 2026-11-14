"""Break down one team's style and where its points come from, to compare with our own.

Only public information is visible: every action, bet sizes and the two cards shown at
showdown. Its code and its discards are not.
Only tables where the team sat with us are counted.

Run:  python tools/profile_team.py history/practice3.jsonl.gz "Pluto" "Team 41"
"""

import gzip
import json
import sys
from collections import defaultdict

BUCKET_NAMES = ["<8", "8-12", "12-20", "20-40", "40+"]


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


def read_tables(path):
    with gzip.open(path, "rt") as handle:
        header = json.loads(handle.readline())
        while True:
            line = handle.readline()
            if not line:
                break
            table = json.loads(line)
            if not handle.readline():
                break
            yield header, table


def median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def share(count, total):
    if total == 0:
        return "  - "
    return "%3.0f%%" % (100.0 * count / total)


class Profile:
    def __init__(self):
        self.tables = 0
        self.points = 0.0
        self.delta = defaultdict(lambda: [0, 0.0])
        self.open_sizes = defaultdict(list)       # open-raise size in big blinds
        self.reraise_sizes = []                   # re-raise size as a multiple of the raise it faces
        self.first_bet = defaultdict(lambda: [0, 0])   # postflop, its turn, nobody has bet: [chances, bets]
        self.bet_sizes = defaultdict(list)        # bet size as a fraction of the pot
        self.facing_bet = defaultdict(lambda: defaultdict(int))
        self.cbet = [0, 0]                        # it raised preflop and the flop is unbet: [chances, bets]
        self.saw_flop = 0
        self.hands = 0
        self.showdowns = 0
        self.places = defaultdict(int)            # place -> tables
        self.bust_before = defaultdict(int)       # busted before hand N -> tables
        self.phase = defaultdict(lambda: [0, 0.0])  # stage of the table -> [hands, total points change]
        self.phase_detail = defaultdict(lambda: [0, 0.0])  # (stage, kind of hand) -> [hands, points change]


def main():
    path = sys.argv[1]
    teams = sys.argv[2:]
    profiles = {}
    for team in teams:
        profiles[team] = Profile()

    for header, table in read_tables(path):
        names = {}
        for entry in header["entries"]:
            names[entry["entry_id"]] = entry["team_name"]
        seat_team = []
        for entry_id in table["seats"]:
            seat_team.append(names.get(entry_id, "?"))
        watched = {}
        for seat in range(len(seat_team)):
            if seat_team[seat] in profiles and not table["fillers"][seat]:
                watched[seat] = profiles[seat_team[seat]]
        if not watched:
            continue
        hands = table["hands"]
        for seat in watched:
            watched[seat].tables += 1
            final = hands[-1]["equity_after"][seat]
            watched[seat].points += final
            payouts = table["payouts"]
            place = "outside top 3"
            for index in range(len(payouts)):
                if abs(final - payouts[index]) < 0.01:
                    place = "place %d" % (index + 1)
            watched[seat].places[place] += 1
            for hand in hands:
                if hand["stacks_before"][seat] > 0 and hand["stacks_after"][seat] == 0:
                    number = hand["hand"]
                    if number <= 40:
                        watched[seat].bust_before[40] += 1
                    if number <= 80:
                        watched[seat].bust_before[80] += 1
                    if number <= 120:
                        watched[seat].bust_before[120] += 1

        for hand in hands:
            big_blind = hand["blinds"][1]
            before = hand["stacks_before"]
            pot = 0
            street = 0
            street_bets = defaultdict(int)
            top_bet = 0
            raises = 0
            preflop_raiser = -1
            category = {}
            for seat in watched:
                category[seat] = "folded or never entered"
            shown = set()

            for event in hand["events"]:
                kind = event["kind"]
                seat = event.get("seat")
                amount = event.get("amount", 0)
                if kind == "board":
                    if amount == 1:
                        street += 1
                        street_bets = defaultdict(int)
                        top_bet = 0
                    continue
                if kind == "show":
                    shown.add(seat)
                    continue
                if kind in ("blind", "ante"):
                    pot += amount
                    if kind == "blind":
                        street_bets[seat] += amount
                        if street_bets[seat] > top_bet:
                            top_bet = street_bets[seat]
                    continue
                if kind not in ("fold", "check", "call", "raise"):
                    continue

                profile = watched.get(seat)
                stack = before[seat]
                is_all_in = kind == "raise" and amount >= 0.9 * stack

                if street == 0:
                    if profile is not None:
                        name = bucket(stack, big_blind)
                        if kind == "raise":
                            if is_all_in:
                                if raises == 0:
                                    category[seat] = "preflop all-in (shoves first)"
                                else:
                                    category[seat] = "preflop all-in (re-shoves)"
                            else:
                                if raises == 0:
                                    profile.open_sizes[name].append(amount / float(big_blind))
                                    if category[seat] == "folded or never entered":
                                        category[seat] = "small raise, saw no flop"
                                else:
                                    profile.reraise_sizes.append(amount / float(max(1, top_bet)))
                                    if category[seat] in ("folded or never entered", "small raise, saw no flop"):
                                        category[seat] = "re-raise, saw no flop"
                        elif kind == "call":
                            if street_bets[seat] + amount >= 0.9 * stack:
                                category[seat] = "preflop all-in (calls)"
                            elif category[seat] == "folded or never entered":
                                category[seat] = "call, saw no flop"
                    if kind == "raise":
                        raises += 1
                        preflop_raiser = seat
                else:
                    if profile is not None:
                        key = "flop"
                        if street == 2:
                            key = "turn"
                        elif street >= 3:
                            key = "river"
                        if top_bet == 0:
                            record = profile.first_bet[key]
                            record[0] += 1
                            if street == 1 and preflop_raiser == seat:
                                profile.cbet[0] += 1
                            if kind == "raise":
                                record[1] += 1
                                if pot > 0:
                                    profile.bet_sizes[key].append(amount / float(pot))
                                if street == 1 and preflop_raiser == seat:
                                    profile.cbet[1] += 1
                        else:
                            profile.facing_bet[key][kind] += 1
                        if (kind in ("call", "raise", "check")
                                and not category[seat].startswith("preflop all-in")):
                            category[seat] = "reached the flop"

                if kind == "call":
                    pot += amount
                    street_bets[seat] += amount
                elif kind == "raise":
                    pot += amount - street_bets[seat]
                    street_bets[seat] = amount
                    if amount > top_bet:
                        top_bet = amount

            for seat in watched:
                if before[seat] <= 0:
                    continue
                profile = watched[seat]
                profile.hands += 1
                name = category[seat]
                if street > 0 and name.endswith("saw no flop") and seat in shown:
                    name = "reached the flop"
                if name == "reached the flop":
                    profile.saw_flop += 1
                if seat in shown:
                    profile.showdowns += 1
                record = profile.delta[name]
                record[0] += 1
                record[1] += hand["equity_after"][seat] - hand["equity_before"][seat]
                number = hand["hand"]
                if number <= 40:
                    stage = "hands 1-40"
                elif number <= 80:
                    stage = "hands 41-80"
                elif number <= 120:
                    stage = "hands 81-120"
                else:
                    stage = "hands 121+"
                record = profile.phase[stage]
                record[0] += 1
                record[1] += hand["equity_after"][seat] - hand["equity_before"][seat]
                record = profile.phase_detail[(stage, name)]
                record[0] += 1
                record[1] += hand["equity_after"][seat] - hand["equity_before"][seat]

    all_categories = set()
    for team in teams:
        for name in profiles[team].delta:
            all_categories.add(name)

    for team in teams:
        profile = profiles[team]
        if profile.tables == 0:
            print("team not found:", team)
            continue
        print()
        print("=== %s ===  %d tables shared with us, average %.2f points per table"
              % (team, profile.tables, profile.points / profile.tables))
        print("Where the placement points come from (average per table):")
        for name in sorted(all_categories):
            count, total = profile.delta[name]
            per_hand = 0.0
            if count:
                per_hand = total / count
            print("  %-30s %5.1f hands/table   %+6.2f pts/table   %+7.3f pts/hand"
                  % (name, count / float(profile.tables), total / profile.tables, per_hand))
        line = []
        for place in ("place 1", "place 2", "place 3", "outside top 3"):
            line.append("%s %s" % (place, share(profile.places[place], profile.tables)))
        print("places: " + "  ".join(line))
        print("busted within: 40 hands %s  80 hands %s  120 hands %s   average %.0f hands per table"
              % (share(profile.bust_before[40], profile.tables), share(profile.bust_before[80], profile.tables),
                 share(profile.bust_before[120], profile.tables), profile.hands / float(profile.tables)))
        line = []
        for stage in ("hands 1-40", "hands 41-80", "hands 81-120", "hands 121+"):
            count, total = profile.phase[stage]
            line.append("%s %+.2f" % (stage, total / profile.tables))
        print("Points gained per stage (per table, relative to the 12.5 start): " + "  ".join(line))
        for stage in ("hands 1-40", "hands 41-80"):
            print("  kinds of hand in %s (per table: hands / total points):" % stage)
            for name in sorted(all_categories):
                count, total = profile.phase_detail[(stage, name)]
                if count:
                    print("      %-30s %5.2f hands  %+6.2f pts"
                          % (name, count / float(profile.tables), total / profile.tables))
        print("share of hands reaching the flop %s, reaching showdown %s"
              % (share(profile.saw_flop, profile.hands), share(profile.showdowns, profile.hands)))
        line = []
        for name in BUCKET_NAMES:
            sizes = profile.open_sizes[name]
            if sizes:
                line.append("%s: %.1f big blinds (%d times)" % (name, median(sizes), len(sizes)))
        print("open-raise size (median): " + "; ".join(line))
        if profile.reraise_sizes:
            print("re-raises over a raise are to %.1fx the raise (median, %d times)"
                  % (median(profile.reraise_sizes), len(profile.reraise_sizes)))
        print("after raising preflop, it bets an unbet flop: %s (%d chances)"
              % (share(profile.cbet[1], profile.cbet[0]), profile.cbet[0]))
        for key in ("flop", "turn", "river"):
            record = profile.first_bet[key]
            facing = profile.facing_bet[key]
            facing_total = facing["fold"] + facing["call"] + facing["raise"]
            print("  %s: bets when nobody has %s (%d chances), bet size %.0f%% of the pot (median); "
                  "facing a bet it folds %s / calls %s / raises %s (%d times)"
                  % (key, share(record[1], record[0]), record[0], 100.0 * median(profile.bet_sizes[key]),
                     share(facing["fold"], facing_total), share(facing["call"], facing_total),
                     share(facing["raise"], facing_total), facing_total))


if __name__ == "__main__":
    main()
