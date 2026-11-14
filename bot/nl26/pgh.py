"""Math for the Pittsburgh variant (3 hole cards, two boards, one hidden discard after the turn,
each board pays half the pot).

Three things:
  1. keep_scores  : which two hole cards to keep, and how strong they are on each board.
  2. push_edge    : placement points gained by shoving preflop instead of folding, on average.
  3. call_edge    : placement points gained by calling a shove instead of folding, on average.

Unlike standard hold'em, an all-in has three outcomes:
  scoop (win both boards), lose both, or in between (mostly one board each, pot split in half).
The probability of each comes from data/pgh_tables.json (simulated by offline/build_pgh.py).
"""

import bisect
import json
import os
import random

import eval7

from . import icm

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class Tables:
    """Tables looked up during play. Read once at import time."""

    def __init__(self):
        with open(os.path.join(_DATA, "pgh_tables.json"), "r") as handle:
            data = json.load(handle)
        self.grid = data["grid"]      # opponent range buckets: top 3%, 6%, ..., 100% of hands
        self.pct = data["pct"]        # pct[class] = this hand ranks within the top how-many percent
        self.share = data["share"]    # share[bucket][class] = average share of the pot
        self.scoop = data["scoop"]    # scoop[bucket][class] = probability of scooping
        self.lose = data["lose"]      # lose[bucket][class] = probability of losing both boards

        with open(os.path.join(_DATA, "pgh_ranges.json"), "r") as handle:
            ranges = json.load(handle)
        self.range_stacks = ranges["stacks"]
        self.push_pct = {}
        for key in ranges["push_pct"]:
            self.push_pct[int(key)] = ranges["push_pct"][key]
        self.call_pct = {}
        for key in ranges["call_pct"]:
            self.call_pct[int(key)] = ranges["call_pct"][key]

        with open(os.path.join(_DATA, "quantiles.json"), "r") as handle:
            quantiles = json.load(handle)
        # quantiles[number of cards] = distribution of hand scores, to turn a score into a percentile
        self.quantiles = {}
        for key in quantiles:
            self.quantiles[int(key)] = quantiles[key]
        self.slots = float(len(self.quantiles[7]))

        self.cards = {}
        for rank in "23456789TJQKA":
            for suit in "shdc":
                self.cards[rank + suit] = eval7.Card(rank + suit)
        self.evaluate = eval7.evaluate
        self.names = []
        for rank in "23456789TJQKA":
            for suit in "shdc":
                self.names.append(rank + suit)
        self.rng = random.Random()

    def _stack_slot(self, stack_bb):
        """The largest stack bucket in the table that does not exceed stack_bb."""
        stacks = self.range_stacks
        slot = 0
        for index in range(len(stacks)):
            if stacks[index] <= stack_bb:
                slot = index
        return slot

    def default_push_pct(self, players_behind, stack_bb):
        """With no opponent data, assume a shover uses this top percentage of hands."""
        if players_behind < 1:
            players_behind = 1
        if players_behind > 7:
            players_behind = 7
        return self.push_pct[players_behind][self._stack_slot(stack_bb)]

    def default_call_pct(self, players_behind, role, stack_bb):
        """With no opponent data, the top percentage a player behind calls with. role: bb, sb, other."""
        if players_behind < 1:
            players_behind = 1
        if players_behind > 7:
            players_behind = 7
        by_role = self.call_pct[players_behind]
        if role not in by_role:
            role = "bb"
        return by_role[role][self._stack_slot(stack_bb)]

    def outcome(self, hand, percent):
        """My class against "the top percent%": returns (average pot share, P(scoop), P(lose both)).

        The table only has a few buckets; percentages in between are interpolated linearly.
        """
        grid = self.grid
        last = len(grid) - 1
        if percent <= grid[0]:
            return self.share[0][hand], self.scoop[0][hand], self.lose[0][hand]
        if percent >= grid[last]:
            return self.share[last][hand], self.scoop[last][hand], self.lose[last][hand]
        slot = 0
        while grid[slot + 1] < percent:
            slot += 1
        weight = (percent - grid[slot]) / float(grid[slot + 1] - grid[slot])
        low = self.share[slot][hand]
        share = low + (self.share[slot + 1][hand] - low) * weight
        low = self.scoop[slot][hand]
        scoop = low + (self.scoop[slot + 1][hand] - low) * weight
        low = self.lose[slot][hand]
        lose = low + (self.lose[slot + 1][hand] - low) * weight
        return share, scoop, lose


def keep_scores(tables, hole, boards):
    """Which two hole cards to keep.

    hole   : my hole cards (3, or 2 after the discard), e.g. ("As", "Td", "7d").
    boards : the two boards, each a list of cards (3, 4 or 5).

    Returns (index of the card to discard, strength on board 1, strength on board 2).
    Strength is 0..1: the percentile, among random hands, of the hand made by the two kept cards
    plus that board (higher is stronger).
    With only 2 hole cards the discard index is -1.
    """
    cards = tables.cards
    evaluate = tables.evaluate
    board_a = []
    for name in boards[0]:
        board_a.append(cards[name])
    board_b = []
    for name in boards[1]:
        board_b.append(cards[name])
    quant_a = tables.quantiles[len(board_a) + 2]
    quant_b = tables.quantiles[len(board_b) + 2]
    slots = tables.slots

    mine = []
    for name in hole:
        mine.append(cards[name])

    if len(mine) == 2:
        score_a = bisect.bisect_left(quant_a, evaluate(mine + board_a))
        score_b = bisect.bisect_left(quant_b, evaluate(mine + board_b))
        return -1, score_a / slots, score_b / slots

    best_drop = 0
    best_total = -1
    best_a = 0
    best_b = 0
    for drop in range(3):
        if drop == 0:
            pair = [mine[1], mine[2]]
        elif drop == 1:
            pair = [mine[0], mine[2]]
        else:
            pair = [mine[0], mine[1]]
        score_a = bisect.bisect_left(quant_a, evaluate(pair + board_a))
        score_b = bisect.bisect_left(quant_b, evaluate(pair + board_b))
        if score_a + score_b > best_total:
            best_total = score_a + score_b
            best_drop = drop
            best_a = score_a
            best_b = score_b
    return best_drop, best_a / slots, best_b / slots


def sampled_strength(tables, hole, boards, passes=2):
    """Which two hole cards to keep, and how likely they beat one random opponent on each board.

    Unlike keep_scores, this looks at the actual texture of the two boards in front of us.
    It samples a batch of "opponent's two hole cards + the board cards still to come", deals each
    sample out, checks whether each way of keeping two cards wins, ties or loses on each board,
    and counts. That way three-flush boards and one-card-away straight or flush draws all count.

    hole   : my hole cards (3, or 2 after the discard).
    boards : the two boards, each a list of cards (3, 4 or 5).
    passes : number of batches. Up to 12 samples per batch; more batches is more accurate, slower.

    Returns (index of the card to discard, win probability on board 1, win probability on board 2).
    With only 2 hole cards the discard index is -1.
    """
    cards = tables.cards
    evaluate = tables.evaluate

    used = {}
    mine = []
    for name in hole:
        mine.append(cards[name])
        used[name] = True
    board_a = []
    for name in boards[0]:
        board_a.append(cards[name])
        used[name] = True
    board_b = []
    for name in boards[1]:
        board_b.append(cards[name])
        used[name] = True
    unseen = []
    for name in tables.names:
        if name not in used:
            unseen.append(cards[name])

    need_a = 5 - len(board_a)   # how many cards board 1 is still missing
    need_b = 5 - len(board_b)
    per_sample = 2 + need_a + need_b
    count = len(unseen) // per_sample
    if count > 12:
        count = 12

    if len(mine) == 2:
        options = [mine]
    else:
        options = [[mine[1], mine[2]], [mine[0], mine[2]], [mine[0], mine[1]]]
    option_count = len(options)
    wins_a = [0] * option_count
    wins_b = [0] * option_count
    total = 0

    for _ in range(passes):
        draw = tables.rng.sample(unseen, count * per_sample)
        position = 0
        for _ in range(count):
            opponent = [draw[position], draw[position + 1]]
            position += 2
            full_a = board_a + draw[position:position + need_a]
            position += need_a
            full_b = board_b + draw[position:position + need_b]
            position += need_b
            their_a = evaluate(opponent + full_a)
            their_b = evaluate(opponent + full_b)
            for index in range(option_count):
                pair = options[index]
                value = evaluate(pair + full_a)
                if value > their_a:
                    wins_a[index] += 2
                elif value == their_a:
                    wins_a[index] += 1
                value = evaluate(pair + full_b)
                if value > their_b:
                    wins_b[index] += 2
                elif value == their_b:
                    wins_b[index] += 1
            total += 2

    best = 0
    for index in range(1, option_count):
        if wins_a[index] + wins_b[index] > wins_a[best] + wins_b[best]:
            best = index
    if total == 0:
        return (-1 if option_count == 1 else 0), 0.5, 0.5
    drop = best
    if option_count == 1:
        drop = -1
    return drop, wins_a[best] / float(total), wins_b[best] / float(total)


def _showdown_value(work, me, seat, my_stack, their_stack, other_dead, result, payouts):
    """My average placement points after an all-in showdown against seat.

    work       : current chips of every seat (modified temporarily, restored before returning).
    my_stack   : my chips at the start of the hand; their_stack is the opponent's.
    other_dead : chips already in the pot from players other than the two of us.
    result     : (average pot share, scoop probability, lose-both probability).
    """
    my_points = icm.my_points
    share = result[0]
    scoop = result[1]
    lose = result[2]
    middle = 1.0 - scoop - lose
    if middle < 0.0:
        middle = 0.0

    # the shorter of the two stacks decides how much is at stake
    if my_stack < their_stack:
        at_risk = my_stack
    else:
        at_risk = their_stack
    pot = 2 * at_risk + other_dead
    my_left = my_stack - at_risk
    their_left = their_stack - at_risk
    my_before = work[me]
    their_before = work[seat]

    # scoop: the whole pot is mine
    work[me] = my_left + pot
    work[seat] = their_left
    value = scoop * my_points(work, me, payouts)

    # lose both: the whole pot goes to the opponent
    work[me] = my_left
    work[seat] = their_left + pot
    value += lose * my_points(work, me, payouts)

    # in between: back out my pot share in this case from the average share (usually close to half)
    if middle > 0.0:
        part = (share - scoop) / middle
        if part < 0.0:
            part = 0.0
        if part > 1.0:
            part = 1.0
        mine = int(pot * part)
        work[me] = my_left + mine
        work[seat] = their_left + pot - mine
        value += middle * my_points(work, me, payouts)

    work[me] = my_before
    work[seat] = their_before
    return value


def push_edge(tables, hand, stacks, posted, extra_dead, me, callers, call_pcts, payouts,
              call_ranges=None):
    """Points gained by shoving now instead of folding, on average. Shove if positive.

    hand       : my hand class index (from hands3.class_index3).
    stacks     : each seat's chips at the start of the hand; 0 for busted seats.
    posted     : chips each seat has put into the pot this betting round (blinds etc.).
    extra_dead : other chips in the pot that are not part of posted (e.g. antes).
    me         : index of my seat.
    callers    : seats that may call, in action order.
    call_pcts  : parallel to callers; the percent chance that each one calls.
    payouts    : points by place.
    call_ranges: parallel to callers; the top percentage of hands each one holds when calling.
                 Defaults to call_pcts. Example where they differ: an opponent raised first (so their
                 hand is already better than random), I shove, they call 22% of the time, but when
                 they call they hold the top 5% of all hands.

    Simplification: at most one opponent calls.
    """
    my_points = icm.my_points
    seats = len(stacks)

    dead = extra_dead
    work = []
    for i in range(seats):
        dead += posted[i]
        work.append(stacks[i] - posted[i])

    # I fold: the pot goes to someone else; assume the seat that posted the most (usually the big blind)
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

    # I shove and nobody calls: the pot is mine
    my_base = work[me]
    work[me] = my_base + dead
    value_steal = my_points(work, me, payouts)
    work[me] = my_base

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
        range_pct = pct
        if call_ranges is not None:
            range_pct = call_ranges[index - 1]
        other_dead = dead - my_posted - posted[seat]
        value = _showdown_value(
            work, me, seat, my_stack, their_stack, other_dead,
            tables.outcome(hand, range_pct), payouts,
        )
        total += nobody_yet * chance * value
        nobody_yet *= 1.0 - chance

    total += nobody_yet * value_steal
    return total - value_fold


def call_edge(tables, hand, stacks, posted, extra_dead, me, pusher, push_pct, payouts):
    """Points gained by calling someone's shove instead of folding, on average. Call if positive.

    pusher   : the seat that shoved. posted must include the chips they shoved.
    push_pct : estimate of the top percentage of hands they shove with.
    Other arguments are the same as push_edge.

    Simplification: players behind me calling as well is ignored.
    """
    my_points = icm.my_points
    seats = len(stacks)

    dead = extra_dead
    work = []
    for i in range(seats):
        dead += posted[i]
        work.append(stacks[i] - posted[i])

    # I fold: the pot goes to the shover
    pusher_base = work[pusher]
    work[pusher] = pusher_base + dead
    value_fold = my_points(work, me, payouts)
    work[pusher] = pusher_base

    other_dead = dead - posted[me] - posted[pusher]
    value = _showdown_value(
        work, me, pusher, stacks[me], stacks[pusher], other_dead,
        tables.outcome(hand, push_pct), payouts,
    )
    return value - value_fold
