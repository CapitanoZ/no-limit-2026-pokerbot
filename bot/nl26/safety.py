"""Small helpers that keep the bot from making mistakes.

Competition rule: a timeout, an exception or an illegal action counts as a "failed decision",
and the engine then checks or folds for the bot. Too many failures and the upload is rejected.
The functions here make sure the action the bot returns is always legal.

They only require a "legal action" object to have kind, min_amount and max_amount
(as described on the competition site); they do not depend on the starter kit directly.
"""

import time


def kind_name(kind):
    """Normalize an action kind to a lowercase string such as "fold", "check", "call", "raise".

    The site did not say whether kind is a string or an enum, so both are handled.
    """
    if type(kind) is str:
        return kind.lower()
    value = getattr(kind, "value", None)
    if type(value) is str:
        return value.lower()
    name = getattr(kind, "name", None)
    if type(name) is str:
        return name.lower()
    return str(kind).lower()


def find_legal(legal_actions, name):
    """Find the legal action called name; return None if there is none."""
    for legal in legal_actions:
        if kind_name(legal.kind) == name:
            return legal
    return None


def pick_fallback(legal_actions):
    """Fallback when something goes wrong: check if possible, else fold, else the first legal action.

    Returns a legal-action object, or None if the list is empty.
    """
    legal = find_legal(legal_actions, "check")
    if legal is not None:
        return legal
    legal = find_legal(legal_actions, "fold")
    if legal is not None:
        return legal
    if len(legal_actions) > 0:
        return legal_actions[0]
    return None


def clamp_amount(amount, min_amount, max_amount):
    """Turn a desired bet into a legal integer.

    Rules: a fractional amount is rounded down and may end up 1 below the minimum;
    an amount outside [min_amount, max_amount] is not corrected for you and counts as a failure.
    So round first, then clamp into the legal range.
    """
    value = int(amount)
    if value < min_amount:
        value = int(min_amount)
    if value > max_amount:
        value = int(max_amount)
    return value


def resolve(legal_actions, name, amount):
    """Turn "the action I want" into a guaranteed-legal (legal action object, integer amount).

    name   : "fold", "check", "call" or "raise".
    amount : only used by "raise"; the total bet for this betting round.

    When the wanted action is not legal right now, step down in this order:
      want to raise but cannot -> call -> fallback
      want to call but cannot  -> check (when nothing is owed the engine offers check) -> fallback
      anything else -> fallback
    Returns None when there is not even a fallback (the legal action list is empty).
    """
    legal = find_legal(legal_actions, name)
    if legal is None and name == "raise":
        legal = find_legal(legal_actions, "call")
        name = "call"
    if legal is None and name == "call":
        legal = find_legal(legal_actions, "check")
        name = "check"
    if legal is None:
        legal = pick_fallback(legal_actions)
        if legal is None:
            return None
        return legal, int(legal.min_amount)
    if name == "raise":
        return legal, clamp_amount(amount, legal.min_amount, legal.max_amount)
    return legal, int(legal.min_amount)


class Deadline:
    """Timer. A decision gets 1 ms; if time is nearly up midway, bail out to the fallback."""

    def __init__(self, budget_microseconds):
        self.end = time.perf_counter_ns() + int(budget_microseconds * 1000)

    def expired(self):
        return time.perf_counter_ns() >= self.end
