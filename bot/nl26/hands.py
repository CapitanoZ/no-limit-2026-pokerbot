"""The 169 starting-hand classes of standard two-card hold'em.

Two hole cards have 1326 concrete combos, but grouped by rank and suitedness there are only 169:
13 pairs (e.g. AA), 78 suited hands (e.g. AKs) and 78 offsuit hands (e.g. AKo).

Each class is an index from 0 to 168: index = a * 13 + b.
  pair:    a == b
  suited:  a is the high card, b the low card (a > b)
  offsuit: b is the high card, a the low card (a < b)
Ranks are numbered from 2 -> 0 up to A -> 12.

Note: this file only fits standard hold'em. If the announced variant deals differently, rewrite it.
"""

RANKS = "23456789TJQKA"
SUITS = "shdc"

_RANK_INDEX = {}
for _i in range(13):
    _RANK_INDEX[RANKS[_i]] = _i


def class_index(card1, card2):
    """Class index (0..168) of two cards such as "As" and "Td"."""
    r1 = _RANK_INDEX[card1[0]]
    r2 = _RANK_INDEX[card2[0]]
    if r1 == r2:
        return r1 * 13 + r1
    if r1 > r2:
        hi = r1
        lo = r2
    else:
        hi = r2
        lo = r1
    if card1[1] == card2[1]:
        return hi * 13 + lo
    return lo * 13 + hi


def class_name(index):
    """Name of a class index, e.g. "AA", "AKs", "AKo"."""
    a = index // 13
    b = index % 13
    if a == b:
        return RANKS[a] + RANKS[a]
    if a > b:
        return RANKS[a] + RANKS[b] + "s"
    return RANKS[b] + RANKS[a] + "o"


def class_combos(index):
    """Number of concrete combos in this class: 6 for a pair, 4 suited, 12 offsuit."""
    a = index // 13
    b = index % 13
    if a == b:
        return 6
    if a > b:
        return 4
    return 12


def all_combos(index):
    """List every concrete combo of this class as (card1, card2)."""
    a = index // 13
    b = index % 13
    result = []
    if a == b:
        rank = RANKS[a]
        for i in range(4):
            for j in range(i + 1, 4):
                result.append((rank + SUITS[i], rank + SUITS[j]))
        return result
    if a > b:
        hi = RANKS[a]
        lo = RANKS[b]
        for i in range(4):
            result.append((hi + SUITS[i], lo + SUITS[i]))
        return result
    hi = RANKS[b]
    lo = RANKS[a]
    for i in range(4):
        for j in range(4):
            if i != j:
                result.append((hi + SUITS[i], lo + SUITS[j]))
    return result


def representative(index):
    """One representative combo of this class, used for calculations."""
    return all_combos(index)[0]


def compatible_combos(my_index, other_index):
    """How many combos of other_index the opponent can still hold when I hold my_index.

    The opponent cannot hold my two cards, so the count is lower than class_combos.
    E.g. when I hold AK, the opponent's AA combos drop from 6 to 3.
    """
    mine = representative(my_index)
    count = 0
    for combo in all_combos(other_index):
        if combo[0] != mine[0] and combo[0] != mine[1]:
            if combo[1] != mine[0] and combo[1] != mine[1]:
                count += 1
    return count
