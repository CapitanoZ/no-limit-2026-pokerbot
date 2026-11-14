"""Benchmark the generic building blocks. Runs locally or remotely; no starter kit needed.

Run:  python3.12 tools/bench_core.py
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import timing  # noqa: E402
from nl26 import icm, pushfold, table_memory  # noqa: E402

PAYOUTS = [50, 30, 20]
BIG_BLIND = 200


class FakeEvent:
    """Imitates the events the engine sends; only for benchmarks and tests."""

    __slots__ = ("kind", "seat", "amount", "cards")

    def __init__(self, kind, seat, amount):
        self.kind = kind
        self.seat = seat
        self.amount = amount
        self.cards = None


def random_stacks(rng, alive):
    """Random stacks for 8 seats totalling 16000, with alive players still in."""
    cuts = []
    for _ in range(alive - 1):
        cuts.append(rng.randint(1, 15999))
    cuts.sort()
    stacks = []
    previous = 0
    for cut in cuts:
        stacks.append(max(1, cut - previous))
        previous = cut
    stacks.append(max(1, 16000 - previous))
    while len(stacks) < 8:
        stacks.append(0)
    rng.shuffle(stacks)
    return stacks


def make_cases(rng, count):
    cases = []
    for _ in range(count):
        alive = rng.randint(4, 8)
        stacks = random_stacks(rng, alive)
        seats = []
        for seat in range(8):
            if stacks[seat] > 0:
                seats.append(seat)
        me = seats[0]
        others = seats[1:]
        posted = [0] * 8
        posted[others[-1]] = min(BIG_BLIND, stacks[others[-1]])
        posted[others[-2]] = min(BIG_BLIND // 2, stacks[others[-2]])
        call_pcts = []
        for _ in others:
            call_pcts.append(rng.uniform(5, 30))
        hand = rng.randint(0, 168)
        cases.append((hand, stacks, posted, me, others, call_pcts))
    return cases


def make_events(rng):
    events = [FakeEvent("hand", None, rng.randint(1, 250))]
    events.append(FakeEvent("blind", 0, 100))
    events.append(FakeEvent("blind", 1, 200))
    for seat in range(2, 8):
        events.append(FakeEvent(rng.choice(["fold", "call", "raise"]), seat, 400))
    events.append(FakeEvent("board", None, 0))
    for seat in range(0, 8):
        events.append(FakeEvent(rng.choice(["check", "fold", "call"]), seat, 0))
    events.append(FakeEvent("show", 3, 0))
    events.append(FakeEvent("win", 3, 900))
    return events


def main():
    rng = random.Random(2026)
    tables = pushfold.Tables()
    cases = make_cases(rng, 2000)

    def run_icm(case):
        icm.my_points(case[1], case[3], PAYOUTS)

    def run_push(case):
        pushfold.push_edge(tables, case[0], case[1], case[2], case[3], case[4], case[5], PAYOUTS)

    def run_call(case):
        pushfold.call_edge(tables, case[0], case[1], case[2], case[3], case[4][-1], 30.0, PAYOUTS)

    memory_cases = []
    for _ in range(2000):
        memory_cases.append(make_events(rng))
    saved = [table_memory.encode(table_memory.TableStats())]

    def run_memory(events):
        stats = table_memory.decode(saved[0])
        table_memory.update(stats, events)
        saved[0] = table_memory.encode(stats)

    def run_whole(index):
        run_memory(memory_cases[index])
        run_push(cases[index])

    timing.report("placement points (one call)", timing.measure(run_icm, cases, 5))
    timing.report("shove math (up to 7 opponents)", timing.measure(run_push, cases, 5))
    timing.report("call math", timing.measure(run_call, cases, 5))
    timing.report("read memory + 18 events + write", timing.measure(run_memory, memory_cases, 5))
    timing.report("memory + shove math (one decision)", timing.measure(run_whole, list(range(2000)), 5))
    print("Competition limit: 1000 microseconds per decision.")


if __name__ == "__main__":
    main()
