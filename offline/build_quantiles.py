"""Build the "hand score -> percentile" tables, one each for flop, turn and river.

eval7.evaluate gives a hand an integer score, higher is better, but the scale is not uniform.
This deals many random "2 hole cards + 3/4/5 board cards" hands and records the distribution.
During play, a score is looked up to find its percentile among random hands.

Output: bot/nl26/data/quantiles.json.
Run:  python offline/build_quantiles.py
"""

import json
import os
import random

import eval7

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "bot", "nl26", "data", "quantiles.json")
SLOTS = 1024
SAMPLES = 200000


def main():
    cards = []
    for rank in "23456789TJQKA":
        for suit in "shdc":
            cards.append(eval7.Card(rank + suit))
    rng = random.Random(11)
    data = {}
    for size in (5, 6, 7):
        values = []
        for _ in range(SAMPLES):
            values.append(eval7.evaluate(rng.sample(cards, size)))
        values.sort()
        table = []
        for slot in range(SLOTS):
            table.append(values[int((slot + 0.5) * SAMPLES / SLOTS)])
        data[str(size)] = table
    with open(OUT_PATH, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    main()
