"""Late-stage "shove or fold" math.

Once the blinds are high, almost every hand has only two options: move all in (shove) or fold.
This computes how many placement points shoving (or calling a shove) gains over folding
on average. A positive result means it is worth doing.

Three steps:
  1. List every outcome: nobody calls, an opponent calls and I win, an opponent calls and I lose.
  2. For each outcome, use icm.my_points to get my points.
  3. Take the probability-weighted average and subtract the points for folding.

Two outside inputs are needed:
  - How wide opponents call or shove (expressed as "the top x% of hands").
    Defaults come from the tables built by offline/build_tables.py; they can later be replaced
    by real numbers measured from hand histories.
  - My win probability against "the top x% of hands". That table was computed for standard
    hold'em; if the announced variant differs, data/holdem_tables.json must be regenerated.

Simplification: at most one opponent calls; two simultaneous callers are not modelled.
"""

import json
import os

from . import icm

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "holdem_tables.json"
)


class Tables:
    """Tables read from the json file. Loaded once at import time, then only looked up."""

    def __init__(self, path=None):
        if path is None:
            path = _DEFAULT_PATH
        with open(path, "r") as handle:
            data = json.load(handle)

        # eq_top[r][class index] = win probability of this hand against "the top r%", r from 1 to 100
        self.eq_top = data["eq_top"]
        # pct[class index] = this hand ranks within the top how-many percent
        self.pct = data["pct"]
        # order = class indexes sorted from strongest to weakest
        self.order = data["order"]
        self.max_stack_bb = data["max_stack_bb"]

        # push_pct[k][stack-1] = with k players still to act behind and a stack of that many big blinds,
        # the top percentage of hands that should shove in theory
        self.push_pct = {}
        for key in data["push_pct"]:
            self.push_pct[int(key)] = data["push_pct"][key]

        # call_pct[k][role][stack-1] = the top percentage a player behind should call with in that spot.
        # role is "bb" (big blind), "sb" (small blind) or "other"
        self.call_pct = {}
        for key in data["call_pct"]:
            self.call_pct[int(key)] = data["call_pct"][key]

    def _stack_slot(self, stack_bb):
        slot = int(stack_bb + 0.5)
        if slot < 1:
            slot = 1
        if slot > self.max_stack_bb:
            slot = self.max_stack_bb
        return slot - 1

    def _players_behind(self, players_behind):
        if players_behind < 1:
            return 1
        if players_behind > 7:
            return 7
        return players_behind

    def default_push_pct(self, players_behind, stack_bb):
        """With no opponent data, assume a shover uses this top percentage of hands."""
        k = self._players_behind(players_behind)
        return self.push_pct[k][self._stack_slot(stack_bb)]

    def default_call_pct(self, players_behind, role, stack_bb):
        """With no opponent data, assume a player behind calls with this top percentage of hands.

        players_behind: players still to act behind the shover; role: the caller's position.
        """
        k = self._players_behind(players_behind)
        by_role = self.call_pct[k]
        if role not in by_role:
            role = "bb"
        return by_role[role][self._stack_slot(stack_bb)]


def _eq_row(tables, pct):
    slot = int(pct + 0.5)
    if slot < 1:
        slot = 1
    if slot > 100:
        slot = 100
    return tables.eq_top[slot]


def push_edge(tables, hand, stacks, posted, me, callers, call_pcts, payouts):
    """Points gained by shoving now instead of folding, on average. Shove if positive.

    hand      : my hand class index (from hands.class_index).
    stacks    : each seat's chips at the start of the hand (before blinds); 0 for busted seats.
    posted    : chips each seat has already put into the pot this hand (blinds etc.).
    me        : index of my seat.
    callers   : seats still to act behind me, in action order.
    call_pcts : parallel to callers; the top percentage of hands each one calls with.
    payouts   : points by place, e.g. [50, 30, 20].
    """
    my_points = icm.my_points
    seats = len(stacks)

    dead = 0
    work = []
    for i in range(seats):
        dead += posted[i]
        work.append(stacks[i] - posted[i])

    # Outcome 1: I fold. The pot goes to someone else; assume it is the seat that posted the most
    # (usually the big blind).
    receiver = -1
    biggest = 0
    for i in range(seats):
        if i != me and posted[i] > biggest:
            biggest = posted[i]
            receiver = i
    if receiver >= 0:
        work[receiver] += dead
        value_fold = my_points(work, me, payouts)
        work[receiver] -= dead
    else:
        value_fold = my_points(work, me, payouts)

    # Outcome 2: I shove, nobody calls, the pot is mine.
    my_base = work[me]
    work[me] = my_base + dead
    value_steal = my_points(work, me, payouts)
    work[me] = my_base

    # Outcome 3: someone calls. Go through "who is the first caller" in action order.
    my_stack = stacks[me]
    my_posted = posted[me]
    nobody_yet = 1.0
    total = 0.0
    index = 0
    for seat in callers:
        pct = call_pcts[index]
        index += 1
        their_stack = stacks[seat]
        if pct <= 0 or their_stack <= 0:
            continue
        if pct > 100:
            pct = 100
        chance = pct / 100.0
        win_chance = _eq_row(tables, pct)[hand]

        # the shorter of the two stacks decides how much is at stake
        if my_stack < their_stack:
            at_risk = my_stack
        else:
            at_risk = their_stack
        other_dead = dead - my_posted - posted[seat]
        their_base = work[seat]

        work[me] = my_stack + at_risk + other_dead
        work[seat] = their_stack - at_risk
        value_win = my_points(work, me, payouts)

        work[me] = my_stack - at_risk
        work[seat] = their_stack + at_risk + other_dead
        value_lose = my_points(work, me, payouts)

        work[me] = my_base
        work[seat] = their_base

        total += nobody_yet * chance * (
            win_chance * value_win + (1.0 - win_chance) * value_lose
        )
        nobody_yet *= 1.0 - chance

    total += nobody_yet * value_steal
    return total - value_fold


def call_edge(tables, hand, stacks, posted, me, pusher, push_pct, payouts):
    """Points gained by calling someone's shove instead of folding, on average. Call if positive.

    pusher   : the seat that shoved.
    push_pct : estimate of the top percentage of hands they shove with.
    Other arguments are the same as push_edge. posted must include the chips they shoved.

    Simplification: players behind me calling as well is ignored. With players still behind,
    the result should be clearly above 0 before calling.
    """
    my_points = icm.my_points
    seats = len(stacks)

    dead = 0
    work = []
    for i in range(seats):
        dead += posted[i]
        work.append(stacks[i] - posted[i])

    # I fold: the pot goes to the shover
    pusher_base = work[pusher]
    work[pusher] = pusher_base + dead
    value_fold = my_points(work, me, payouts)
    work[pusher] = pusher_base

    my_stack = stacks[me]
    their_stack = stacks[pusher]
    if my_stack < their_stack:
        at_risk = my_stack
    else:
        at_risk = their_stack
    other_dead = dead - posted[me] - posted[pusher]
    win_chance = _eq_row(tables, push_pct)[hand]

    work[me] = my_stack + at_risk + other_dead
    work[pusher] = their_stack - at_risk
    value_win = my_points(work, me, payouts)

    work[me] = my_stack - at_risk
    work[pusher] = their_stack + at_risk + other_dead
    value_lose = my_points(work, me, payouts)

    return win_chance * value_win + (1.0 - win_chance) * value_lose - value_fold
