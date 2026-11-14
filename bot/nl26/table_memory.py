"""Memory for one table: playing-style statistics for every opponent.

Competition rule: the bot cannot keep state in variables. On each decision the engine hands
back the bytes the bot returned last time: its only memory at this table. New tables start empty.

The stats are packed into 136 bytes (the limit is 64 KB), so reading and writing are fast.

Six counters per seat:
  hands         hands this seat was dealt into
  vpip          hands where it voluntarily put chips in preflop (call or raise)
  pfr           hands where it raised preflop
  faced_raise   times it had to act after someone raised preflop
  fold_to_raise how many of those times it folded
  showdowns     hands where it showed its cards

The event kind names (hand, blind, fold, raise, ...) follow the site's Getting started page
and should be checked against the starter kit's samples once it is available.
"""

import struct

MAGIC = 0xA7
VERSION = 1
MAX_SEATS = 10

# position of each counter in a seat's list
HANDS = 0
VPIP = 1
PFR = 2
FACED_RAISE = 3
FOLD_TO_RAISE = 4
SHOWDOWNS = 5
FLAGS = 6  # temporary flags for the current hand, see the _FLAG_ constants below
_FIELDS = 7

_FLAG_COUNTED = 1  # this hand is already counted in hands
_FLAG_VPIP = 2     # this hand is already counted in vpip
_FLAG_PFR = 4      # this hand is already counted in pfr
_FLAG_SHOWN = 8    # this hand is already counted in showdowns

_CODEC = struct.Struct("<BBHBB" + "6HB" * MAX_SEATS)
SIZE = _CODEC.size
_COUNTER_MAX = 65535


class TableStats:
    """Statistics for one table so far."""

    def __init__(self):
        self.hand_number = 0
        self.street = 0          # 0 = preflop, +1 each time board cards are dealt
        self.raise_seen = False  # whether someone has already raised preflop in the current hand
        self.seats = []
        for _ in range(MAX_SEATS):
            self.seats.append([0] * _FIELDS)

    def rate(self, seat, count_field, total_field, prior_rate, prior_weight):
        """Compute a rate, e.g. "how often this seat folds to a raise".

        With little data the rate is unreliable, so blend in a prior estimate:
        pretend we have already seen prior_weight samples with rate prior_rate.
        """
        row = self.seats[seat]
        return (row[count_field] + prior_rate * prior_weight) / (
            row[total_field] + prior_weight
        )


def decode(memory):
    """Rebuild TableStats from bytes. Empty, wrong-length or corrupt bytes give a fresh TableStats."""
    stats = TableStats()
    try:
        if len(memory) != SIZE:
            return stats
        values = _CODEC.unpack(memory)
    except Exception:
        return stats
    if values[0] != MAGIC or values[1] != VERSION:
        return stats
    stats.hand_number = values[2]
    state = values[3]
    stats.raise_seen = (state & 1) == 1
    stats.street = state >> 1
    position = 5
    for seat in range(MAX_SEATS):
        row = stats.seats[seat]
        for field in range(_FIELDS):
            row[field] = values[position]
            position += 1
    return stats


def encode(stats):
    """Pack TableStats into bytes."""
    street = stats.street
    if street > 100:
        street = 100
    state = street << 1
    if stats.raise_seen:
        state |= 1
    hand_number = stats.hand_number
    if hand_number > _COUNTER_MAX:
        hand_number = _COUNTER_MAX
    values = [MAGIC, VERSION, hand_number, state, MAX_SEATS]
    for row in stats.seats:
        for field in range(_FIELDS):
            values.append(row[field])
    return _CODEC.pack(*values)


def _kind_name(kind):
    if type(kind) is str:
        return kind
    value = getattr(kind, "value", None)
    if type(value) is str:
        return value
    name = getattr(kind, "name", None)
    if type(name) is str:
        return name.lower()
    return str(kind)


def _bump(row, field):
    if row[field] < _COUNTER_MAX:
        row[field] += 1


def update(stats, events):
    """Record new events into the statistics.

    events is what the engine provides: everything public that happened since my last action.
    Each event has kind, seat (may be None), amount and cards.
    Unknown event kinds are skipped (the announced variant may add new ones).
    """
    seats = stats.seats
    for event in events:
        kind = _kind_name(event.kind)

        if kind == "hand":
            # a new hand starts: clear every seat's temporary flags
            amount = event.amount
            if type(amount) is int and amount >= 0:
                stats.hand_number = amount
            stats.street = 0
            stats.raise_seen = False
            for row in seats:
                row[FLAGS] = 0
            continue

        if kind == "board":
            stats.street += 1
            continue

        seat = event.seat
        if type(seat) is not int or seat < 0 or seat >= MAX_SEATS:
            continue
        row = seats[seat]
        flags = row[FLAGS]

        if kind == "show":
            if not flags & _FLAG_SHOWN:
                row[FLAGS] = flags | _FLAG_SHOWN
                _bump(row, SHOWDOWNS)
            continue

        if kind not in ("ante", "blind", "fold", "check", "call", "raise"):
            continue

        # this seat appeared in the hand, so count it as dealt in
        if not flags & _FLAG_COUNTED:
            flags |= _FLAG_COUNTED
            _bump(row, HANDS)

        if stats.street == 0:
            if kind == "fold":
                if stats.raise_seen:
                    _bump(row, FACED_RAISE)
                    _bump(row, FOLD_TO_RAISE)
            elif kind == "call":
                if stats.raise_seen:
                    _bump(row, FACED_RAISE)
                if not flags & _FLAG_VPIP:
                    flags |= _FLAG_VPIP
                    _bump(row, VPIP)
            elif kind == "raise":
                if stats.raise_seen:
                    _bump(row, FACED_RAISE)
                if not flags & _FLAG_VPIP:
                    flags |= _FLAG_VPIP
                    _bump(row, VPIP)
                if not flags & _FLAG_PFR:
                    flags |= _FLAG_PFR
                    _bump(row, PFR)
                stats.raise_seen = True

        row[FLAGS] = flags
