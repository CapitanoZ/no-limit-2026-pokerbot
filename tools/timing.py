"""Timing helper: run a function once on each of many inputs and report how long it took.

Each decision in the competition gets only 1 ms (1000 microseconds). The site recommends looking
at the slowest cases (p99 = the slowest 1 in 100, max = the single slowest), not the average.
"""

import time


def measure(func, inputs, rounds=1):
    """Call func(item) for every item in inputs, rounds times. Returns timing stats in microseconds."""
    clock = time.perf_counter_ns
    samples = []
    for _ in range(rounds):
        for item in inputs:
            start = clock()
            func(item)
            samples.append(clock() - start)
    samples.sort()
    count = len(samples)
    total = 0
    for value in samples:
        total += value
    p99_slot = int(count * 0.99)
    if p99_slot >= count:
        p99_slot = count - 1
    return {
        "count": count,
        "mean": total / count / 1000.0,
        "p50": samples[count // 2] / 1000.0,
        "p99": samples[p99_slot] / 1000.0,
        "max": samples[count - 1] / 1000.0,
    }


def report(label, result):
    print(
        "%-34s n %6d   mean %7.1f   median %7.1f   p99 %7.1f   max %7.1f  (us)"
        % (label, result["count"], result["mean"], result["p50"], result["p99"], result["max"])
    )
