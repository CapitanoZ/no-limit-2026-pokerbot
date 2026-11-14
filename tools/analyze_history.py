"""Statistics for one round of hand histories: where our bot loses points, how the field plays.

Run:  python tools/analyze_history.py history/practice1.jsonl.gz [team name ...]
Team names given after the file get their own playing-style breakdown.

Terms:
  stack in bb   = chips at the start of the hand / big blind
  unopened      = when the player acts, everyone before has folded or limped (called the big blind)
  shove         = a raise of at least 90% of the player's own stack
  points change = change in ICM-expected placement points over the hand (included in the history)
"""

import gzip
import json
import sys
from collections import defaultdict

BUCKETS = [(4, "<4"), (8, "4-8"), (12, "8-12"), (20, "12-20"), (40, "20-40"), (10 ** 9, "40+")]
BUCKET_NAMES = ["<4", "4-8", "8-12", "12-20", "20-40", "40+"]


def bucket(stack, big_blind):
    value = stack / float(big_blind)
    for limit, name in BUCKETS:
        if value < limit:
            return name
    return "40+"


def read_tables(path):
    """Read the history table by table, yielding (file header, public table record, our private record)."""
    with gzip.open(path, "rt") as handle:
        header = json.loads(handle.readline())
        while True:
            line = handle.readline()
            if not line:
                break
            table = json.loads(line)
            own_line = handle.readline()
            if not own_line:
                break
            yield header, table, json.loads(own_line)["you"]


def new_counts():
    return defaultdict(int)


def rate(counts, key):
    total = 0
    for name in counts:
        total += counts[name]
    if total == 0:
        return "   - "
    return "%4.0f%%" % (100.0 * counts[key] / total)


def total_of(counts):
    total = 0
    for name in counts:
        total += counts[name]
    return total


def main():
    path = sys.argv[1]
    watch = sys.argv[2:]

    # overall stats: key is (situation, stack bucket in big blinds), value is counts per action
    everyone = defaultdict(new_counts)
    by_team = defaultdict(lambda: defaultdict(new_counts))
    shove_called = defaultdict(new_counts)     # after a shove, did anyone call
    open_result = defaultdict(new_counts)      # after a small raise, did everyone fold
    postflop = new_counts()
    bet_result = new_counts()
    showdown_hands = 0
    total_hands = 0

    # our own stats
    my_tables = 0
    my_points = 0.0
    my_places = defaultdict(int)
    my_automatic = 0
    my_decisions = 0
    my_delta = defaultdict(lambda: [0, 0.0])        # category -> [hands, total points change]
    my_delta_bucket = defaultdict(lambda: [0, 0.0])
    my_delta_detail = defaultdict(lambda: [0, 0.0])
    my_bust_hand = defaultdict(int)
    table_lengths = []

    for header, table, own in read_tables(path):
        names = {}
        for entry in header["entries"]:
            names[entry["entry_id"]] = entry["team_name"]
        seats = table["seats"]
        me = own["seat"]
        scored = not table["fillers"][me]
        hands = table["hands"]
        if scored:
            my_tables += 1
            my_automatic += len(own.get("automatic", []))
            table_lengths.append(len(hands))
            final = hands[-1]["equity_after"][me]
            my_points += final
            payouts = table["payouts"]
            place = "outside top 3"
            for index in range(len(payouts)):
                if abs(final - payouts[index]) < 0.01:
                    place = "place %d" % (index + 1)
            my_places[place] += 1

        for hand in hands:
            total_hands += 1
            big_blind = hand["blinds"][1]
            before = hand["stacks_before"]
            events = hand["events"]

            raises = 0
            first_raise_kind = None
            first_raise_bucket = None
            first_raiser = -1
            callers_after_first = 0
            posted = defaultdict(int)
            street = 0
            had_show = False
            bet_open = False      # whether someone has already bet in this betting round
            last_bettor = -1
            bet_answered = False
            my_category = "folded or never entered"
            my_in_hand = before[me] > 0

            for event in events:
                kind = event["kind"]
                seat = event.get("seat")
                amount = event.get("amount", 0)

                if kind == "board":
                    if street == 0 or amount == 1:
                        # a new betting round starts: settle whether anyone responded to the last bet
                        # of the previous round
                        if last_bettor >= 0:
                            if bet_answered:
                                bet_result["called or raised"] += 1
                            else:
                                bet_result["everyone folds"] += 1
                        bet_open = False
                        last_bettor = -1
                        bet_answered = False
                    if amount == 1:
                        street += 1
                    continue
                if kind == "show":
                    had_show = True
                    continue
                if kind in ("blind", "ante"):
                    posted[seat] += amount
                    continue
                if kind not in ("fold", "check", "call", "raise"):
                    continue

                if seat == me:
                    my_decisions += 1

                if street > 0:
                    # postflop
                    postflop[kind] += 1
                    if kind == "raise":
                        if last_bettor >= 0:
                            bet_answered = True
                            bet_result["called or raised"] += 1
                        last_bettor = seat
                        bet_answered = False
                        bet_open = True
                    elif kind == "call" and last_bettor >= 0:
                        bet_answered = True
                    if (seat == me and kind in ("call", "raise")
                            and not my_category.startswith("preflop all-in")):
                        my_category = "reached the flop"
                    continue

                # preflop
                stack = before[seat]
                name = bucket(stack, big_blind)
                team = names.get(seats[seat], "?")
                is_all_in = False
                if kind == "raise" and amount >= 0.9 * stack:
                    is_all_in = True
                if kind == "call" and posted[seat] + amount >= 0.9 * stack:
                    is_all_in = True

                if raises == 0:
                    situation = "unopened"
                    if kind == "raise":
                        action = "shove" if is_all_in else "small raise"
                    elif kind == "call":
                        action = "limp"
                    elif kind == "check":
                        action = "check"
                    else:
                        action = "fold"
                elif raises == 1 and first_raise_kind == "shove":
                    situation = "facing a shove"
                    action = "fold" if kind == "fold" else "call"
                elif raises == 1:
                    situation = "facing a small raise"
                    if kind == "fold":
                        action = "fold"
                    elif kind == "call":
                        action = "call"
                    else:
                        action = "re-shove" if is_all_in else "re-raise"
                else:
                    situation = "after 2+ raises"
                    action = "fold" if kind == "fold" else "call or raise"

                everyone[(situation, name)][action] += 1
                by_team[team][(situation, name)][action] += 1

                if seat == me:
                    if kind == "raise" and is_all_in:
                        if raises == 0:
                            my_category = "preflop all-in (I shove first)"
                        else:
                            my_category = "preflop all-in (I re-shove)"
                    elif kind == "call" and is_all_in:
                        my_category = "preflop all-in (I call)"
                    elif kind == "raise" and my_category == "folded or never entered":
                        my_category = "raised, saw no flop"
                    elif kind == "call" and my_category == "folded or never entered":
                        my_category = "called, saw no flop"

                if raises >= 1 and kind in ("call", "raise") and seat != first_raiser:
                    callers_after_first += 1
                if kind == "raise":
                    raises += 1
                    if raises == 1:
                        first_raise_kind = "shove" if is_all_in else "small raise"
                        first_raise_bucket = name
                        first_raiser = seat
                posted[seat] += amount if kind == "call" else 0
                if kind == "raise":
                    posted[seat] = amount

            if last_bettor >= 0:
                if bet_answered:
                    bet_result["called or raised"] += 1
                else:
                    bet_result["everyone folds"] += 1
            if had_show:
                showdown_hands += 1
            if first_raise_kind == "shove":
                key = "called" if callers_after_first > 0 else "not called"
                shove_called[first_raise_bucket][key] += 1
            elif first_raise_kind == "small raise":
                key = "called or raised" if callers_after_first > 0 else "everyone folds"
                open_result[first_raise_bucket][key] += 1

            if scored and my_in_hand:
                delta = hand["equity_after"][me] - hand["equity_before"][me]
                if my_category in ("raised, saw no flop", "called, saw no flop") and street > 0:
                    my_category = "reached the flop"
                record = my_delta[my_category]
                record[0] += 1
                record[1] += delta
                record = my_delta_bucket[bucket(before[me], big_blind)]
                record[0] += 1
                record[1] += delta
                record = my_delta_detail[(my_category, bucket(before[me], big_blind))]
                record[0] += 1
                record[1] += delta
                if hand["stacks_after"][me] == 0:
                    my_bust_hand[(hand["hand"] - 1) // 20] += 1

    print("=== Our bot ===")
    print("tables scored: %d, average %.2f points per table (field average 12.5)"
          % (my_tables, my_points / max(1, my_tables)))
    line = []
    for place in ("place 1", "place 2", "place 3", "outside top 3"):
        line.append("%s: %d tables (%.0f%%)"
                    % (place, my_places[place], 100.0 * my_places[place] / max(1, my_tables)))
    print("places: " + ", ".join(line))
    print("  note: tables that hit the hand limit are scored by chips and count as 'outside top 3'")
    print("failed decisions: %d of %d decisions" % (my_automatic, my_decisions))
    table_lengths.sort()
    if table_lengths:
        print("hands per table: median %d, longest %d"
              % (table_lengths[len(table_lengths) // 2], table_lengths[-1]))
    line = []
    for slot in sorted(my_bust_hand):
        line.append("hands %d-%d: %d tables" % (slot * 20 + 1, slot * 20 + 20, my_bust_hand[slot]))
    print("when we busted: " + ", ".join(line))

    print()
    print("Where placement points were won or lost, by kind of hand (average per table):")
    for category in sorted(my_delta, key=lambda name: my_delta[name][1]):
        count, total = my_delta[category]
        print("  %-30s %5.1f hands/table   %+6.2f pts/table   %+7.3f pts/hand"
              % (category, count / float(my_tables), total / my_tables, total / max(1, count)))
    print("By stack at the time (in big blinds):")
    for name in BUCKET_NAMES:
        count, total = my_delta_bucket[name]
        print("  %-6s %5.1f hands/table   %+6.2f pts/table   %+7.3f pts/hand"
              % (name, count / float(max(1, my_tables)), total / max(1, my_tables), total / max(1, count)))

    print("Each kind of hand by stack (placement points per hand / hands per table):")
    for category in sorted(my_delta):
        parts = []
        for name in BUCKET_NAMES:
            count, total = my_delta_detail[(category, name)]
            if count > 0:
                parts.append("%s: %+.3f/%.1f hands" % (name, total / count, count / float(max(1, my_tables))))
        print("  %-22s %s" % (category, "   ".join(parts)))

    def print_style(title, stats):
        print()
        print("=== " + title + " ===")
        print("Unopened pot (by stack in big blinds):  fold/check   limp   small raise   shove    count")
        for name in BUCKET_NAMES:
            counts = stats[("unopened", name)]
            passive = defaultdict(int)
            passive["a"] = counts["fold"] + counts["check"]
            passive["b"] = counts["limp"] + counts["small raise"] + counts["shove"]
            print("  %-6s                    %s      %s    %s     %s   %6d"
                  % (name, rate(passive, "a"), rate(counts, "limp"), rate(counts, "small raise"),
                     rate(counts, "shove"), total_of(counts)))
        print("Facing a shove:  call rate    count")
        for name in BUCKET_NAMES:
            counts = stats[("facing a shove", name)]
            print("  %-6s        %s     %6d" % (name, rate(counts, "call"), total_of(counts)))
        print("Facing a small raise:  fold    call    re-raise   re-shove   count")
        for name in BUCKET_NAMES:
            counts = stats[("facing a small raise", name)]
            print("  %-6s        %s  %s   %s     %s    %6d"
                  % (name, rate(counts, "fold"), rate(counts, "call"), rate(counts, "re-raise"),
                     rate(counts, "re-shove"), total_of(counts)))

    print_style("All players combined (including us)", everyone)
    print("After two or more raises (e.g. raising and then facing a shove):  fold rate    count")
    for name in BUCKET_NAMES:
        counts = everyone[("after 2+ raises", name)]
        print("  %-6s        %s     %6d" % (name, rate(counts, "fold"), total_of(counts)))

    print()
    print("=== Per hand ===")
    print("When the first raise is a shove, does anyone call (by the shover's stack in big blinds):")
    for name in BUCKET_NAMES:
        counts = shove_called[name]
        print("  %-6s called %s   count %6d" % (name, rate(counts, "called"), total_of(counts)))
    print("When the first raise is a small raise, does everyone fold:")
    for name in BUCKET_NAMES:
        counts = open_result[name]
        print("  %-6s everyone folds %s   count %6d"
              % (name, rate(counts, "everyone folds"), total_of(counts)))
    print("Postflop action mix: check %s  bet or raise %s  call %s  fold %s   total %d"
          % (rate(postflop, "check"), rate(postflop, "raise"), rate(postflop, "call"),
             rate(postflop, "fold"), total_of(postflop)))
    print("Postflop bets that make everyone else fold: %s   total %d"
          % (rate(bet_result, "everyone folds"), total_of(bet_result)))
    print("Hands that reach showdown: %.0f%%   total %d hands"
          % (100.0 * showdown_hands / max(1, total_hands), total_hands))

    for team in watch:
        if team in by_team:
            print_style("Team: " + team, by_team[team])
        else:
            print()
            print("team not found:", team)


if __name__ == "__main__":
    main()
