"""Step 2: turn the equity table into the lookup tables the bot uses during play.

Reads offline/out/equity169.json (the output of step 1, build_equity.py) and
writes bot/nl26/data/holdem_tables.json, which holds:

  order     the 169 classes from strongest to weakest (by win rate against a random hand)
  pct       the top-percent rank of each class
  eq_top    win rate of each class against "the top r%", r from 1 to 100
  push_pct  top percentage to shove in theory (by players left behind and stack in big blinds)
  call_pct  top percentage to call a shove with in theory

Where push_pct and call_pct come from:
assume equal stacks and chip EV only (no placement points), and let the shover and the caller
keep adjusting their ranges against each other until neither wants to change. This is the
default when there is no opponent data; real numbers from hand histories can replace it later.

Run:  python offline/build_tables.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands  # noqa: E402

IN_PATH = os.path.join(ROOT, "offline", "out", "equity169.json")
OUT_PATH = os.path.join(ROOT, "bot", "nl26", "data", "holdem_tables.json")

TOTAL_COMBOS = 1326
MAX_STACK_BB = 20      # the tables go up to 20 big blinds
SMALL_BLIND = 0.5      # in big blinds
BIG_BLIND = 1.0
ANTE_BB = 0.0          # ante per player per hand, in big blinds; set once the rules are out
TABLE_PLAYERS = 8


def load_matrix():
    with open(IN_PATH, "r") as handle:
        return json.load(handle)["matrix"]


def build_weights():
    """weights[me][opponent] = combos of that class the opponent can still hold when I hold mine."""
    weights = []
    for mine in range(169):
        row = []
        for other in range(169):
            row.append(hands.compatible_combos(mine, other))
        weights.append(row)
    return weights


def equity_vs_classes(matrix, weights, mine, members):
    """Win rate of my hand against a set of classes (members), weighted by available combos."""
    top = 0.0
    bottom = 0.0
    for other in members:
        weight = weights[mine][other]
        top += weight * matrix[mine][other]
        bottom += weight
    if bottom == 0:
        return 0.5
    return top / bottom


def build_order(matrix, weights):
    """Sort the 169 classes by win rate against a random hand, best first."""
    everything = list(range(169))
    strength = []
    for mine in range(169):
        strength.append(equity_vs_classes(matrix, weights, mine, everything))

    def by_strength(index):
        return strength[index]

    order = sorted(everything, key=by_strength, reverse=True)
    return order


def build_pct(order):
    """pct[class] = this class ranks within the top how-many percent."""
    pct = [0.0] * 169
    running = 0
    for index in order:
        running += hands.class_combos(index)
        pct[index] = round(100.0 * running / TOTAL_COMBOS, 2)
    return pct


def top_members(order, percent):
    """Which classes make up "the top percent%". Always includes at least the strongest one."""
    target = percent / 100.0 * TOTAL_COMBOS
    members = []
    running = 0
    for index in order:
        combos = hands.class_combos(index)
        if len(members) > 0 and running + combos / 2.0 > target:
            break
        members.append(index)
        running += combos
    return members


def build_eq_top(matrix, weights, order):
    """eq_top[r][class] = win rate of the class against "the top r%". Row 0 is unused (copy of row 1)."""
    eq_top = []
    for percent in range(0, 101):
        if percent == 0:
            members = top_members(order, 1)
        else:
            members = top_members(order, percent)
        row = []
        for mine in range(169):
            row.append(round(equity_vs_classes(matrix, weights, mine, members), 4))
        eq_top.append(row)
    return eq_top


def caller_roles(players_behind):
    """Positions of the players_behind players acting after the shover, in action order.

    The last two to act are the small and big blind; with 1 player left the shover is the small
    blind and only the big blind is behind.
    """
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


def percent_slot(percent):
    slot = int(percent + 0.5)
    if slot < 1:
        slot = 1
    if slot > 100:
        slot = 100
    return slot


def solve_one(eq_top, players_behind, stack_bb):
    """Solve one spot until neither side wants to change. Returns (push percent, {role: call percent})."""
    roles = caller_roles(players_behind)
    pusher_posted = 0.0
    if players_behind == 1:
        pusher_posted = SMALL_BLIND
    dead = SMALL_BLIND + BIG_BLIND + ANTE_BB * TABLE_PLAYERS

    push = 50.0
    call = {}
    for role in roles:
        call[role] = 20.0

    rounds = 300
    for step_number in range(rounds):
        # change less on each later iteration so that it settles
        step = 1.0 / (2.0 + step_number * 0.25)

        # caller: which hands do not lose by calling when the shover uses the top push%
        push_row = eq_top[percent_slot(push)]
        new_call = {}
        for role in call:
            mine = already_posted(role)
            need = (stack_bb - mine) / (2.0 * stack_bb + dead - pusher_posted - mine)
            good = 0
            for index in range(169):
                if push_row[index] >= need:
                    good += hands.class_combos(index)
            new_call[role] = 100.0 * good / TOTAL_COMBOS

        # shover: which hands do better shoving than folding when players behind use the call ranges
        good = 0
        for index in range(169):
            nobody_yet = 1.0
            value = 0.0
            for role in roles:
                chance = call[role] / 100.0
                win_chance = eq_top[percent_slot(call[role])][index]
                win_amount = stack_bb + dead - already_posted(role)
                lose_amount = stack_bb - pusher_posted
                value += nobody_yet * chance * (
                    win_chance * win_amount - (1.0 - win_chance) * lose_amount
                )
                nobody_yet *= 1.0 - chance
            value += nobody_yet * dead
            if value > 0:
                good += hands.class_combos(index)
        new_push = 100.0 * good / TOTAL_COMBOS

        push += (new_push - push) * step
        for role in call:
            call[role] += (new_call[role] - call[role]) * step

    result_call = {}
    for role in call:
        result_call[role] = round(call[role], 1)
    return round(push, 1), result_call


def build_ranges(eq_top):
    push_pct = {}
    call_pct = {}
    for players_behind in range(1, 8):
        push_list = []
        call_lists = {}
        for stack_bb in range(1, MAX_STACK_BB + 1):
            push, call = solve_one(eq_top, players_behind, float(stack_bb))
            push_list.append(push)
            for role in call:
                if role not in call_lists:
                    call_lists[role] = []
                call_lists[role].append(call[role])
        push_pct[str(players_behind)] = push_list
        call_pct[str(players_behind)] = call_lists
        print("behind:", players_behind, "players, shove range (1 to 20 big blinds):", push_list)
    return push_pct, call_pct


def main():
    matrix = load_matrix()
    weights = build_weights()
    order = build_order(matrix, weights)
    pct = build_pct(order)
    eq_top = build_eq_top(matrix, weights, order)

    names = []
    for index in order[:25]:
        names.append(hands.class_name(index))
    print("strongest 25 classes:", " ".join(names))

    push_pct, call_pct = build_ranges(eq_top)

    data = {
        "version": 1,
        "variant": "holdem",
        "max_stack_bb": MAX_STACK_BB,
        "ante_bb": ANTE_BB,
        "order": order,
        "pct": pct,
        "eq_top": eq_top,
        "push_pct": push_pct,
        "call_pct": call_pct,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    print("wrote", OUT_PATH, round(os.path.getsize(OUT_PATH) / 1024), "KB")


if __name__ == "__main__":
    main()
