"""Pittsburgh variant: how wide to assume opponents shove and call when there is no opponent data.

Same method as the standard hold'em version (build_tables.py): assume equal stacks and chip EV
only, and let the shover and the caller keep adjusting their ranges against each other until
neither wants to change.
The difference is that this uses the three-hole-card, two-board outcome table (pgh_tables.json).

Output: bot/nl26/data/pgh_ranges.json.
Run:  python offline/solve_pgh.py
"""

import json
import os
import sys
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands3  # noqa: E402

IN_PATH = os.path.join(ROOT, "bot", "nl26", "data", "pgh_tables.json")
OUT_PATH = os.path.join(ROOT, "bot", "nl26", "data", "pgh_ranges.json")

STACKS = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30]   # in big blinds
SMALL_BLIND = 0.5
BIG_BLIND = 1.0
TOTAL_COMBOS = 22100
ROUNDS = 160

_GRID = []
_SHARE = []
_COMBOS = []


def init_worker():
    global _GRID, _SHARE
    with open(IN_PATH, "r") as handle:
        data = json.load(handle)
    _GRID = data["grid"]
    _SHARE = data["share"]
    for index in range(hands3.CLASS_COUNT):
        _COMBOS.append(hands3.class_combos3(index))


def share_row(percent):
    """Average pot share of every class against "the top percent%", interpolated between buckets."""
    if percent <= _GRID[0]:
        return _SHARE[0]
    last = len(_GRID) - 1
    if percent >= _GRID[last]:
        return _SHARE[last]
    slot = 0
    while _GRID[slot + 1] < percent:
        slot += 1
    weight = (percent - _GRID[slot]) / float(_GRID[slot + 1] - _GRID[slot])
    low = _SHARE[slot]
    high = _SHARE[slot + 1]
    row = []
    for index in range(len(low)):
        row.append(low[index] + (high[index] - low[index]) * weight)
    return row


def caller_roles(players_behind):
    if players_behind == 1:
        return ["bb"]
    roles = []
    for _ in range(players_behind - 2):
        roles.append("other")
    roles.append("sb")
    roles.append("bb")
    return roles


def already_posted(role):
    if role == "bb":
        return BIG_BLIND
    if role == "sb":
        return SMALL_BLIND
    return 0.0


def solve_one(task):
    players_behind, stack_bb = task
    roles = caller_roles(players_behind)
    pusher_posted = 0.0
    if players_behind == 1:
        pusher_posted = SMALL_BLIND
    dead = SMALL_BLIND + BIG_BLIND
    count = hands3.CLASS_COUNT

    push = 50.0
    call = {}
    for role in roles:
        call[role] = 25.0

    for step_number in range(ROUNDS):
        step = 1.0 / (2.0 + step_number * 0.25)

        # caller: which hands do not lose by calling when the shover uses the top push%
        push_row = share_row(push)
        new_call = {}
        for role in call:
            mine = already_posted(role)
            need = (stack_bb - mine) / (2.0 * stack_bb + dead - pusher_posted - mine)
            good = 0
            for index in range(count):
                if push_row[index] >= need:
                    good += _COMBOS[index]
            new_call[role] = 100.0 * good / TOTAL_COMBOS

        # shover: which hands do better shoving than folding when players behind use the call ranges
        rows = {}
        for role in call:
            rows[role] = share_row(call[role])
        good = 0
        for index in range(count):
            nobody_yet = 1.0
            value = 0.0
            for role in roles:
                chance = call[role] / 100.0
                my_share = rows[role][index]
                pot = 2.0 * stack_bb + dead - already_posted(role) - pusher_posted
                # shoving returns my_share of the pot, minus the chips I put in
                value += nobody_yet * chance * (my_share * pot - (stack_bb - pusher_posted))
                nobody_yet *= 1.0 - chance
            value += nobody_yet * dead
            if value > 0:
                good += _COMBOS[index]
        new_push = 100.0 * good / TOTAL_COMBOS

        push += (new_push - push) * step
        for role in call:
            call[role] += (new_call[role] - call[role]) * step

    result_call = {}
    for role in call:
        result_call[role] = round(call[role], 1)
    return players_behind, stack_bb, round(push, 1), result_call


def main():
    tasks = []
    for players_behind in range(1, 8):
        for stack_bb in STACKS:
            tasks.append((players_behind, float(stack_bb)))

    solved = {}
    with Pool(initializer=init_worker) as pool:
        for players_behind, stack_bb, push, call in pool.imap_unordered(solve_one, tasks):
            solved[(players_behind, stack_bb)] = (push, call)

    push_pct = {}
    call_pct = {}
    for players_behind in range(1, 8):
        push_list = []
        call_lists = {}
        for stack_bb in STACKS:
            push, call = solved[(players_behind, float(stack_bb))]
            push_list.append(push)
            for role in call:
                if role not in call_lists:
                    call_lists[role] = []
                call_lists[role].append(call[role])
        push_pct[str(players_behind)] = push_list
        call_pct[str(players_behind)] = call_lists
        print("behind:", players_behind, "players, shove:", push_list)
        print("        big blind calls:", call_lists["bb"])

    with open(OUT_PATH, "w") as handle:
        json.dump(
            {"stacks": STACKS, "push_pct": push_pct, "call_pct": call_pct},
            handle,
            separators=(",", ":"),
        )
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    main()
