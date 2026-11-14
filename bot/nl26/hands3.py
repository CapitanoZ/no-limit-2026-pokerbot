"""Pittsburgh variant: starting-hand classes for three hole cards.

In this competition every player is dealt 3 hole cards. Three cards have 22100 concrete combos,
which fall into 1755 classes by rank and suit pattern. Each class is an index from 0 to 1754.

The suit pattern is a small number (code). Sort the three cards high to low as 1st, 2nd, 3rd:
  three different ranks:
    0 = all three suits differ    1 = 1st and 2nd suited
    2 = 1st and 3rd suited        3 = 2nd and 3rd suited
    4 = all three suited
  a pair plus a kicker:
    0 = kicker shares no suit with the pair   1 = kicker suited with one card of the pair
  three of the same rank: only 0
"""

RANKS = "23456789TJQKA"
SUITS = "shdc"

_RANK = {}
for _i in range(13):
    _RANK[RANKS[_i]] = _i

_INDEX = {}
_KEYS = []


def _build():
    for r0 in range(12, -1, -1):
        for r1 in range(r0, -1, -1):
            for r2 in range(r1, -1, -1):
                if r0 == r1 and r1 == r2:
                    codes = 1
                elif r0 == r1 or r1 == r2:
                    codes = 2
                else:
                    codes = 5
                for code in range(codes):
                    key = ((r0 * 13 + r1) * 13 + r2) * 5 + code
                    _INDEX[key] = len(_KEYS)
                    _KEYS.append((r0, r1, r2, code))


_build()
CLASS_COUNT = len(_KEYS)  # 1755


def class_index3(card1, card2, card3):
    """Class index (0..1754) of three cards such as "As", "Td", "7d"."""
    r0 = _RANK[card1[0]]
    r1 = _RANK[card2[0]]
    r2 = _RANK[card3[0]]
    s0 = card1[1]
    s1 = card2[1]
    s2 = card3[1]
    # sort by rank, high to low
    if r0 < r1:
        r0, r1 = r1, r0
        s0, s1 = s1, s0
    if r1 < r2:
        r1, r2 = r2, r1
        s1, s2 = s2, s1
    if r0 < r1:
        r0, r1 = r1, r0
        s0, s1 = s1, s0

    if r0 == r1:
        if r1 == r2:
            code = 0
        elif s2 == s0 or s2 == s1:
            code = 1
        else:
            code = 0
    elif r1 == r2:
        if s0 == s1 or s0 == s2:
            code = 1
        else:
            code = 0
    else:
        if s0 == s1:
            if s1 == s2:
                code = 4
            else:
                code = 1
        elif s0 == s2:
            code = 2
        elif s1 == s2:
            code = 3
        else:
            code = 0
    return _INDEX[((r0 * 13 + r1) * 13 + r2) * 5 + code]


def representative3(index):
    """One representative combo of this class, returned as three card strings."""
    r0, r1, r2, code = _KEYS[index]
    a = RANKS[r0]
    b = RANKS[r1]
    c = RANKS[r2]
    if r0 == r1 and r1 == r2:
        return (a + "s", b + "h", c + "d")
    if r0 == r1:
        if code == 1:
            return (a + "s", b + "h", c + "s")
        return (a + "s", b + "h", c + "d")
    if r1 == r2:
        if code == 1:
            return (a + "s", b + "s", c + "h")
        return (a + "s", b + "h", c + "d")
    if code == 0:
        return (a + "s", b + "h", c + "d")
    if code == 1:
        return (a + "s", b + "s", c + "h")
    if code == 2:
        return (a + "s", b + "h", c + "s")
    if code == 3:
        return (a + "s", b + "h", c + "h")
    return (a + "s", b + "s", c + "s")


def class_combos3(index):
    """Number of concrete combos in this class."""
    r0, r1, r2, code = _KEYS[index]
    if r0 == r1 and r1 == r2:
        return 4
    if r0 == r1 or r1 == r2:
        return 12
    if code == 0:
        return 24
    if code == 4:
        return 4
    return 12


def class_name3(index):
    """Human-readable name, e.g. "AAK", "AKQ suited", "AK7 1st+2nd suited"."""
    r0, r1, r2, code = _KEYS[index]
    name = RANKS[r0] + RANKS[r1] + RANKS[r2]
    if r0 == r1 and r1 == r2:
        return name
    if r0 == r1 or r1 == r2:
        if code == 1:
            return name + " kicker suited with pair"
        return name
    if code == 1:
        return name + " 1st+2nd suited"
    if code == 2:
        return name + " 1st+3rd suited"
    if code == 3:
        return name + " 2nd+3rd suited"
    if code == 4:
        return name + " suited"
    return name
