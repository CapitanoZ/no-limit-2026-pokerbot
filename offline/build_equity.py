"""Step 1: win probability of every hand class against every other, all in, in standard hold'em.

169 classes pair up into about 14k matchups; each gets 200k random boards and the wins are counted.
The result goes to offline/out/equity169.json for step 2, build_tables.py.

Runs on your own machine only; it is not uploaded. Uses the eval7 library (a hand evaluator).
If the announced variant is not standard hold'em, this is the file to change.

Run:  python offline/build_equity.py
"""

import json
import os
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands  # noqa: E402

ITERATIONS = 200000
OUT_PATH = os.path.join(ROOT, "offline", "out", "equity169.json")


def one_row(my_index):
    """Win rates of class my_index against every class with a higher index."""
    import eval7

    mine = hands.representative(my_index)
    hero = [eval7.Card(mine[0]), eval7.Card(mine[1])]
    row = []
    for other_index in range(my_index + 1, 169):
        villain = eval7.HandRange(hands.class_name(other_index))
        equity = eval7.py_hand_vs_range_monte_carlo(hero, villain, [], ITERATIONS)
        row.append(equity)
    return my_index, row


def main():
    start = time.time()
    matrix = []
    for _ in range(169):
        matrix.append([0.5] * 169)

    done = 0
    with Pool() as pool:
        for my_index, row in pool.imap_unordered(one_row, range(169)):
            other_index = my_index + 1
            for equity in row:
                matrix[my_index][other_index] = equity
                # seen from the other side, this is the opponent's win rate
                matrix[other_index][my_index] = 1.0 - equity
                other_index += 1
            done += 1
            if done % 20 == 0:
                print("done", done, "/ 169 rows, elapsed", round(time.time() - start), "s")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump({"iterations": ITERATIONS, "matrix": matrix}, handle)
    print("wrote", OUT_PATH, "total time", round(time.time() - start), "s")


if __name__ == "__main__":
    main()
