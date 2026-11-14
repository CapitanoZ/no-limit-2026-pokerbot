"""Converting chip stacks into expected placement points (ICM).

The tournament pays by finishing place (by default 50 / 30 / 20 points for 1st / 2nd / 3rd).
The question answered here: given everyone's current stack, how many points do I get on average?

It uses the standard Malmuth-Harville model from poker:
the probability that a player finishes 1st = their stack / all chips on the table;
remove the winner and decide 2nd place among the rest the same way, and so on.

It only needs stacks and the payout table, never the cards, so it works for any variant.
"""


def my_points(stacks, me, payouts):
    """Expected points of seat me.

    stacks  : chips of every seat; write 0 for seats that are already out.
    me      : index of my seat.
    payouts : points by place, e.g. [50, 30, 20]. payouts[0] is the points for 1st place.

    If stacks[me] is 0, treat it as "I just busted on this hand":
    I finish behind everyone still alive and get the points of that place (0 if there are none).
    """
    alive = 0
    total = 0
    for s in stacks:
        if s > 0:
            alive += 1
            total += s

    mine = stacks[me]
    if mine <= 0:
        if alive < len(payouts):
            return float(payouts[alive])
        return 0.0
    if total <= 0:
        return 0.0

    # Only as many places as there are live players can still be won. Skip trailing 0-point places.
    paid = len(payouts)
    if paid > alive:
        paid = alive
    while paid > 0 and payouts[paid - 1] == 0:
        paid -= 1
    if paid == 0:
        return 0.0

    if paid > 3:
        used = [False] * len(stacks)
        return _points_general(stacks, me, payouts, paid, 0, total, used)

    # Fast path for at most 3 paid places (the competition default).
    value = payouts[0] * mine / total
    if paid == 1:
        return value

    second_pay = payouts[1]
    third_pay = 0
    if paid == 3:
        third_pay = payouts[2]

    j = 0
    for sj in stacks:
        if j != me and sj > 0:
            # suppose seat j finishes 1st
            rest = total - sj
            part = second_pay * mine / rest
            if third_pay:
                inner = 0.0
                k = 0
                for sk in stacks:
                    if k != me and k != j and sk > 0:
                        # then suppose seat k finishes 2nd and I finish 3rd
                        inner += sk / (rest - sk)
                    k += 1
                part += third_pay * inner * mine / rest
            value += sj / total * part
        j += 1
    return value


def _points_general(stacks, me, payouts, paid, place, total, used):
    """Generic version for more than 3 paid places (slow; rarely needed in the competition)."""
    mine = stacks[me]
    value = payouts[place] * mine / total
    if place + 1 >= paid:
        return value
    j = 0
    for sj in stacks:
        if j != me and sj > 0 and not used[j]:
            used[j] = True
            value += sj / total * _points_general(
                stacks, me, payouts, paid, place + 1, total - sj, used
            )
            used[j] = False
        j += 1
    return value


def all_points(stacks, payouts):
    """Expected points of every seat, as a list. Seats that are out get 0."""
    result = []
    for seat in range(len(stacks)):
        if stacks[seat] > 0:
            result.append(my_points(stacks, seat, payouts))
        else:
            result.append(0.0)
    return result
