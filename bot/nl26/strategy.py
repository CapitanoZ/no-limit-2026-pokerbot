"""Strategy for the Pittsburgh variant (v11 = v10 plus two tightenings based on round 4 data:
  open-raise only the top 8% to 22% of hands; below 20 big blinds, re-shove only the top 30%).

Notes for v10:

Pittsburgh strategy (v10 = v6 with one change: re-raise much wider when nobody is left to act behind).

What changed in v10 (only this; everything else is identical to v6):
  After someone's small raise, the top percentage I re-raise with now depends on how many
  players are still to act behind me:
  top 75% with nobody behind, top 50% with 1 behind, and v6's top 14% with 2 or more.
  The re-raise is only 2x their raise (was 2.7x).
  Also: when I was the last preflop raiser and nobody bets the flop, bet 30% of the pot
  (against at most 2 opponents).
  All three move toward the "keep applying pressure with small raises" style of the round 3 winner.
  Evidence: in round 3 our own 10%-28% hands doing this still made 0.14 to 0.43 points per hand,
  not far from the strongest hands, so the profit comes mostly from folds, not from the cards.
  Three of the top four teams in round 3 did this with 44% to 79% of hands in that spot.

Notes for v6:

Pittsburgh strategy (v6 = v4 plus four preflop adjustments based on the round 1 hand histories).

Adjustments in v6:
  1. No more small raises with 12 to 20 big blinds (it lost 0.04 points per hand in round 1):
  shove or fold only, except with the strongest hands.
  2. Call shoves wider (calls made over 1 point per hand in round 1, yet we called less than
  half as often as the round winner).
  3. Re-shove threshold back from 0.45 to 0.30 points (tightening cut the volume without
  raising the profit per hand).
  4. Open-raise size down from 2.5 to 2.2 big blinds, to lose a little less when re-raised.

Notes for v4:

Pittsburgh strategy (v4 = v3 plus four changes copied from Pluto, the winner of practice round 3).

Changes in v4:
  1. With more than 20 big blinds, re-raise small (to 2.7x) with strong hands after a small raise.
  2. Stricter requirements for re-shoving over a raise.
  3. Postflop, bet more often and smaller when nobody has bet; fold more readily facing a bet.
  4. Call shoves slightly wider.


Three parts:
  Discard : keep the two cards that are strongest across the two boards combined.
  Preflop : compute in placement points how much shoving gains over folding. How often opponents
            call and what they shove with are numbers measured in practice round 1, not theory.
  Postflop: look at how strong the two kept cards are on each board. Bet only when strong on both;
            facing a bet, compare "estimated share of the pot" with "price of the call".

Opponent habits seen in practice round 1 (2500 tables, about 420k hands):
  - After a small raise each player folds over 80% of the time; more than half the time all fold.
  - After a shove each player calls less than 20% of the time; a shove of 8 to 12 big blinds
  gets called only one time in four.
  - A raiser who gets re-raised folds 70% to 80% of the time.
  - A postflop bet makes everyone fold only 27% of the time. So no postflop bluffing.

All tunable numbers sit at the top of the file, easy to adjust after reading hand histories.
"""

from poker_agent_sdk import Action

from . import hands3, pgh, table_memory

# ---- tunable numbers ----
SHORT_STACK_BB = 12.0     # at or below this many big blinds: shove or fold only, preflop
PUSH_MAX_BB = 25.0        # at or below this many big blinds: consider open-shoving
RESHOVE_MAX_BB = 30.0     # at or below this many big blinds: consider re-shoving over a raise
OPEN_SIZE_BB = 2.2        # open-raise to this many big blinds
OPEN_MIN_BB = 20.0        # small raises only above this many big blinds (strongest hands exempt)
TRAP_PCT = 6.0            # when deep, the top x% raise small instead of shoving, to invite action
# With no raise yet, the top percentage I open-raise with, keyed by how many players can still
# act behind me.
# In round 4, open-raising anything outside our top 10% lost money (opponents learned to fight
# back), so this is much tighter now.
OPEN_PCT = {1: 22.0, 2: 16.0, 3: 12.0, 4: 10.0, 5: 10.0, 6: 9.0, 7: 8.0}
THREEBET_MIN_BB = 20.0    # small re-raises only above this many big blinds
# After a small raise, the top percentage I re-raise with, keyed by players yet to act behind me.
THREEBET_PCT = {0: 75.0, 1: 50.0, 2: 14.0}
THREEBET_SIZE = 2.0       # re-raise to this multiple of their raise (small, so a re-raise costs less)
CBET_SIZE = 0.30          # as the last preflop raiser, bet this fraction of the pot on an unbet flop
CALL_RAISE_PCT = 9.0      # when deep, the top percentage I just call a raise with
CALL_RAISE_COST = 0.08    # calling a raise may cost at most this fraction of my stack
EDGE_MARGIN = 0.05        # shove or call only if it beats folding by this many placement points
PUSH_DEEP_MARGIN = 0.03   # extra points required per big blind above 12 before shoving
RESHOVE_MARGIN = 0.30     # re-shove over a raise only if it beats folding by this many points
RESHOVE_SHORT_PCT = 30.0  # below 20 bb, re-shove only this top percentage (weaker hands lost in round 4)
OPENER_CALL_CHANCE = 22.0 # percent chance the raiser calls my re-shove
OPENER_CALL_RANGE = 6.0   # when they call, they hold this top percentage of all hands
TYPICAL_RAISE_RATE = 0.22 # share of hands a typical opponent raises preflop (practice 1 average)
BET_SHARE = 0.50          # postflop: bet only with at least this estimated share of the pot
BET_WEAK_SIDE = 0.25      # ...and at least this strength on the weaker of the two boards
BET_SIZE = 0.45           # bet size as a fraction of the pot
RAISE_SHARE = 0.88        # postflop: raise only with at least this estimated share of the pot
CALL_MARGIN = 0.10        # a call needs estimated share to exceed the required share by this much


def _call_chance(pusher_bb, role):
    """Percent chance that one opponent calls my shove. pusher_bb is my stack in big blinds.

    Numbers from practice round 1: shorter shoves get called more; the big blind calls more often.
    """
    if pusher_bb < 4:
        base = 25.0
    elif pusher_bb < 8:
        base = 10.5
    elif pusher_bb < 12:
        base = 7.5
    elif pusher_bb < 20:
        base = 6.2
    elif pusher_bb < 40:
        base = 5.8
    else:
        base = 5.2
    if role == "bb":
        return base * 1.6
    return base * 0.9


def _push_range(their_bb, live, reshove, stats, seat_number):
    """Someone shoved: estimate the top percentage of hands they are doing it with.

    their_bb : their stack in big blinds.
    live     : opponents still in the hand. The fewer there are, the wider the shove.
    reshove  : True if I had already raised and they shoved over my raise; such shoves are stronger.
    stats    : this table's memory. The more this seat usually raises, the wider its shove range.
    """
    if reshove:
        if their_bb < 12:
            base = 13.0
        elif their_bb < 20:
            base = 8.0
        else:
            base = 4.0
    else:
        if their_bb < 4:
            base = 55.0
        elif their_bb < 8:
            base = 42.0
        elif their_bb < 12:
            base = 38.0
        elif their_bb < 20:
            base = 20.0
        elif their_bb < 40:
            base = 11.0
        else:
            base = 6.0
        if live >= 5:
            base *= 0.75
        elif live == 2:
            base *= 1.3
        elif live <= 1:
            base *= 1.6

    # how often this seat raises at this table, compared with a typical opponent
    raise_rate = TYPICAL_RAISE_RATE
    if 0 <= seat_number < table_memory.MAX_SEATS:
        raise_rate = stats.rate(seat_number, table_memory.PFR, table_memory.HANDS, TYPICAL_RAISE_RATE, 8)
    ratio = raise_rate / TYPICAL_RAISE_RATE
    if ratio < 0.6:
        ratio = 0.6
    if ratio > 4.0:
        ratio = 4.0
    value = base * ratio
    if raise_rate > 0.6 and value < 70.0:
        # this player raises almost every hand, so their shove is basically any hand
        value = 70.0
    if value < 2.0:
        value = 2.0
    if value > 100.0:
        value = 100.0
    return value


def _passive(state):
    """Check if possible, otherwise fold."""
    if state.can("check"):
        return Action.check()
    if state.can("fold"):
        return Action.fold()
    first = state.legal_actions[0]
    return Action(first.kind, first.min_amount)


def _call(state):
    if state.can("call"):
        return Action.call()
    return _passive(state)


def _raise_to(state, amount):
    """Raise to amount (total bet this round), clamped to the legal range; call if raising is illegal."""
    legal = state.can("raise")
    if legal is None:
        return _call(state)
    value = int(amount)
    if value < legal.min_amount:
        value = legal.min_amount
    if value > legal.max_amount:
        value = legal.max_amount
    return Action.raise_to(value)


def _all_in(state):
    legal = state.can("raise")
    if legal is None:
        return _call(state)
    return Action.raise_to(legal.max_amount)


def decide(state, stats, tables):
    """Decide what to do on this turn; returns an Action."""
    if state.phase == "discard":
        return _discard(state, tables)
    if state.phase != "betting":
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)
    boards = state.variant.get("boards")
    if not boards or len(boards) < 2 or len(boards[0]) == 0:
        return _preflop(state, stats, tables)
    return _postflop(state, stats, tables, boards)


def _discard(state, tables):
    boards = state.variant["boards"]
    drop, _, _ = pgh.sampled_strength(tables, state.cards, boards, 3)
    if drop < 0:
        drop = 0
    return Action("discard", cards=(drop,))


def _table_view(state):
    """Collect the table state into a few lists indexed by position in state.seats."""
    seats = state.seats
    count = len(seats)
    stacks = [0] * count      # chips at the start of this round (current stack + bet this round)
    posted = [0] * count      # chips bet this round
    active = []               # opponents who can still act
    live = 0                  # opponents still in the hand (including those already all in)
    me = -1
    top_bet = 0
    top_seat = -1
    posted_total = 0
    for i in range(count):
        seat = seats[i]
        if seat.seat == state.seat:
            me = i
        if seat.status == "busted":
            continue
        stacks[i] = seat.stack + seat.bet
        posted[i] = seat.bet
        posted_total += seat.bet
        if seat.seat != state.seat:
            if seat.status == "active":
                active.append(i)
                live += 1
            elif seat.status == "all_in":
                live += 1
            if seat.status != "folded" and seat.bet > top_bet:
                top_bet = seat.bet
                top_seat = i
    extra_dead = state.pot - posted_total
    if extra_dead < 0:
        extra_dead = 0
    return me, stacks, posted, extra_dead, active, live, top_bet, top_seat


def _role(posted_amount, state):
    if posted_amount == state.blinds.big_blind:
        return "bb"
    if posted_amount == state.blinds.small_blind:
        return "sb"
    return "other"


def _preflop(state, stats, tables):
    me, stacks, posted, extra_dead, active, live, top_bet, top_seat = _table_view(state)
    big_blind = state.blinds.big_blind
    if big_blind <= 0:
        big_blind = 1
    my_stack = stacks[me]
    stack_bb = my_stack / float(big_blind)
    cards = state.cards
    hand = hands3.class_index3(cards[0], cards[1], cards[2])
    pct = tables.pct[hand]
    payouts = state.config.payouts
    raised = top_bet > big_blind

    if not raised:
        # ---- nobody has raised yet ----
        behind = len(active)
        if behind < 1:
            behind = 1
        if behind > 7:
            behind = 7
        if stack_bb > SHORT_STACK_BB and pct <= TRAP_PCT:
            # deep stack, very strong hand: raise small to invite action
            return _raise_to(state, OPEN_SIZE_BB * big_blind)
        if stack_bb <= PUSH_MAX_BB:
            call_pcts = []
            for seat in active:
                call_pcts.append(_call_chance(stack_bb, _role(posted[seat], state)))
            edge = pgh.push_edge(
                tables, hand, stacks, posted, extra_dead, me, active, call_pcts, payouts
            )
            margin = EDGE_MARGIN
            if stack_bb > SHORT_STACK_BB:
                margin += PUSH_DEEP_MARGIN * (stack_bb - SHORT_STACK_BB)
            if edge > margin:
                return _all_in(state)
            if stack_bb <= OPEN_MIN_BB:
                return _passive(state)
        if pct <= OPEN_PCT[behind]:
            return _raise_to(state, OPEN_SIZE_BB * big_blind)
        return _passive(state)

    # ---- someone has raised ----
    their_stack = stacks[top_seat]
    their_bb = their_stack / float(big_blind)
    big_raise = top_bet >= 0.4 * their_stack or top_bet >= 0.3 * my_stack
    i_raised = posted[me] > big_blind
    seat_number = state.seats[top_seat].seat

    if big_raise:
        # they shoved or made a very large bet: is calling better than folding?
        push_pct = _push_range(their_bb, live, i_raised, stats, seat_number)
        trial = list(posted)
        if trial[top_seat] < their_stack:
            # treat them as having put their whole stack in
            trial[top_seat] = their_stack
        edge = pgh.call_edge(
            tables, hand, stacks, trial, extra_dead, me, top_seat, push_pct, payouts
        )
        margin = EDGE_MARGIN
        if len(active) > 1:
            # players behind me have yet to act, so be more careful
            margin += 0.3
        if edge > margin:
            if posted[top_seat] >= their_stack or state.can("raise") is None:
                return _call(state)
            return _all_in(state)
        return _passive(state)

    # they made a small raise
    to_call = state.to_call
    # players yet to act behind me: still active, not the raiser, and not yet matched to the top bet
    behind = 0
    for seat in active:
        if seat != top_seat and posted[seat] < top_bet:
            behind += 1
    if behind > 2:
        behind = 2

    if stack_bb > THREEBET_MIN_BB and not i_raised and pct <= THREEBET_PCT[behind]:
        # small re-raise: most opponents fold to a re-raise, and it does not risk my whole stack
        target = THREEBET_SIZE * top_bet
        if target >= 0.35 * my_stack:
            return _all_in(state)
        return _raise_to(state, target)

    if stack_bb <= RESHOVE_MAX_BB and not i_raised and (stack_bb >= 20.0 or pct <= RESHOVE_SHORT_PCT):
        # consider a re-shove: the raiser usually folds and the pot already holds their raise and the blinds
        call_pcts = []
        call_ranges = []
        for seat in active:
            if seat == top_seat:
                call_pcts.append(OPENER_CALL_CHANCE)
                call_ranges.append(OPENER_CALL_RANGE)
            else:
                chance = _call_chance(stack_bb, _role(posted[seat], state))
                call_pcts.append(chance)
                call_ranges.append(chance)
        edge = pgh.push_edge(
            tables, hand, stacks, posted, extra_dead, me, active, call_pcts, payouts, call_ranges
        )
        margin = RESHOVE_MARGIN
        if stack_bb > SHORT_STACK_BB:
            margin += PUSH_DEEP_MARGIN * (stack_bb - SHORT_STACK_BB)
        if edge > margin:
            return _all_in(state)

    if stack_bb > SHORT_STACK_BB and pct <= CALL_RAISE_PCT and to_call <= CALL_RAISE_COST * my_stack:
        return _call(state)
    return _passive(state)


def _i_raised_last_preflop(state):
    """Whether I was the last player to raise preflop in this hand."""
    last_raiser = None
    for event in state.history:
        if event.kind == "board":
            break
        if event.kind == "raise":
            last_raiser = event.seat
    return last_raiser == state.seat


def _postflop(state, stats, tables, boards):
    me, stacks, posted, extra_dead, active, live, top_bet, top_seat = _table_view(state)
    _, strength_a, strength_b = pgh.sampled_strength(tables, state.cards, boards, 2)
    if strength_a > strength_b:
        strong = strength_a
        weak = strength_b
    else:
        strong = strength_b
        weak = strength_a

    # the more opponents, the harder it is to beat all of them, so discount strength by their number
    if live < 1:
        live = 1
    power = 1.5 + 0.75 * live
    win_strong = strong ** power
    win_weak = weak ** power
    share = (win_strong + win_weak) / 2.0

    pot = state.pot
    to_call = state.to_call
    my_left = state.seats[me].stack

    if to_call <= 0:
        if share >= BET_SHARE and win_weak >= BET_WEAK_SIDE:
            return _raise_to(state, posted[me] + BET_SIZE * pot)
        if len(boards[0]) == 3 and live <= 2 and _i_raised_last_preflop(state):
            # I was the last preflop raiser: bet small on the flop to keep up the pressure, hit or miss
            return _raise_to(state, posted[me] + CBET_SIZE * pot)
        return _passive(state)

    need = to_call / float(pot + to_call)
    if to_call >= 0.4 * my_left:
        # this call commits a large part of my stack and losing may bust me, so require more
        need += 0.08
    if share >= RAISE_SHARE and win_weak >= 0.5:
        return _raise_to(state, top_bet + pot + to_call)
    if share >= need + CALL_MARGIN:
        return _call(state)
    return _passive(state)
