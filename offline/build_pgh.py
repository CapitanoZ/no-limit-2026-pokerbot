"""Hand-strength tables for the Pittsburgh variant.

The game: 3 hole cards each and two boards of 5 cards. After the turn betting every player
discards one hole card face down; the other 2 play on both boards. Each board pays half the pot.

This script simulates what happens to each of the 1755 three-card classes when all in preflop:
  share  average share of the pot (0 to 1)
  scoop  probability of winning both boards
  lose   probability of losing both boards
against two kinds of opponent: random cards, and only "the top r%" of hands (r from GRID).

Discard rule (both sides use it in the simulation, and the bot uses the same rule in play):
for each of the three ways to keep two cards, rank "2 kept cards + the 4 cards of each board"
as a percentile among random hands; the pair with the highest total over both boards wins.

Output: bot/nl26/data/pgh_tables.json.
Run:  python offline/build_pgh.py
"""

import bisect
import json
import os
import random
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bot"))

from nl26 import hands3  # noqa: E402

OUT_PATH = os.path.join(ROOT, "bot", "nl26", "data", "pgh_tables.json")

SAMPLES_RANDOM = 10000  # simulations per class against a random opponent
SAMPLES_RANGE = 4000    # simulations per class against "the top r%"
GRID = [3, 6, 10, 15, 22, 30, 45, 65, 100]
QUANTILES = 1024
TOTAL_COMBOS = 22100

_CARDS = {}
_QUANT = []
_TOP = []


def all_card_names():
    names = []
    for rank in hands3.RANKS:
        for suit in hands3.SUITS:
            names.append(rank + suit)
    return names


def init_worker(quantiles, top):
    """Runs once when each worker process starts: prepare the card objects and the two big tables."""
    global _QUANT, _TOP
    import eval7

    for name in all_card_names():
        _CARDS[name] = eval7.Card(name)
    _QUANT = quantiles
    _TOP = top


def choose_keep(hole, board_a, board_b, evaluate):
    """Choose which two hole cards to keep. board_a / board_b: the 4 cards dealt so far on each board."""
    best_score = -1
    best_pair = None
    for drop in range(3):
        if drop == 0:
            pair = [hole[1], hole[2]]
        elif drop == 1:
            pair = [hole[0], hole[2]]
        else:
            pair = [hole[0], hole[1]]
        score = bisect.bisect_left(_QUANT, evaluate(pair + board_a))
        score += bisect.bisect_left(_QUANT, evaluate(pair + board_b))
        if score > best_score:
            best_score = score
            best_pair = pair
    return best_pair


def run_class(task):
    """Simulate one class. task = (class index, opponent's top-combo count (0 = random), samples)."""
    import eval7

    evaluate = eval7.evaluate
    index, top_count, samples = task
    hero_names = hands3.representative3(index)
    hero = []
    for name in hero_names:
        hero.append(_CARDS[name])
    rest = []
    for name in all_card_names():
        if name not in hero_names:
            rest.append(_CARDS[name])

    rng = random.Random(index * 100003 + top_count)
    total = 0
    scoop = 0
    lose = 0
    done = 0
    while done < samples:
        if top_count > 0:
            names = _TOP[rng.randrange(top_count)]
            if names[0] in hero_names or names[1] in hero_names or names[2] in hero_names:
                continue
            o0 = _CARDS[names[0]]
            o1 = _CARDS[names[1]]
            o2 = _CARDS[names[2]]
            pool = []
            for card in rest:
                if card is not o0 and card is not o1 and card is not o2:
                    pool.append(card)
            opp = [o0, o1, o2]
            draw = rng.sample(pool, 10)
        else:
            dealt = rng.sample(rest, 13)
            opp = dealt[0:3]
            draw = dealt[3:13]

        a4 = draw[0:4]
        b4 = draw[5:9]
        hero_keep = choose_keep(hero, a4, b4, evaluate)
        opp_keep = choose_keep(opp, a4, b4, evaluate)
        board_a = draw[0:5]
        board_b = draw[5:10]

        points = 0
        mine = evaluate(hero_keep + board_a)
        theirs = evaluate(opp_keep + board_a)
        if mine > theirs:
            points += 2
        elif mine == theirs:
            points += 1
        mine = evaluate(hero_keep + board_b)
        theirs = evaluate(opp_keep + board_b)
        if mine > theirs:
            points += 2
        elif mine == theirs:
            points += 1

        total += points
        if points == 4:
            scoop += 1
        elif points == 0:
            lose += 1
        done += 1

    return index, top_count, total / (4.0 * samples), scoop / float(samples), lose / float(samples)


def make_quantiles():
    """Score distribution of many random "2 hole + 4 board cards" hands, used for percentiles."""
    import eval7

    cards = []
    for name in all_card_names():
        cards.append(eval7.Card(name))
    rng = random.Random(7)
    values = []
    for _ in range(80000):
        values.append(eval7.evaluate(rng.sample(cards, 6)))
    values.sort()
    quantiles = []
    for slot in range(QUANTILES):
        quantiles.append(values[int((slot + 0.5) * len(values) / QUANTILES)])
    return quantiles


def combos_by_class():
    """Group the 22100 concrete combos by class."""
    names = all_card_names()
    buckets = []
    for _ in range(hands3.CLASS_COUNT):
        buckets.append([])
    for i in range(52):
        for j in range(i + 1, 52):
            for k in range(j + 1, 52):
                index = hands3.class_index3(names[i], names[j], names[k])
                buckets[index].append((names[i], names[j], names[k]))
    return buckets


def run_phase(quantiles, top, tasks, label):
    start = time.time()
    results = []
    with Pool(initializer=init_worker, initargs=(quantiles, top)) as pool:
        done = 0
        for result in pool.imap_unordered(run_class, tasks, chunksize=16):
            results.append(result)
            done += 1
            if done % 2000 == 0:
                print(label, done, "/", len(tasks), "elapsed", round(time.time() - start), "s", flush=True)
    print(label, "done, elapsed", round(time.time() - start), "s", flush=True)
    return results


def rounded(values):
    result = []
    for value in values:
        result.append(round(value, 4))
    return result


def main():
    count = hands3.CLASS_COUNT
    quantiles = make_quantiles()

    # Phase 1: against a random opponent
    tasks = []
    for index in range(count):
        tasks.append((index, 0, SAMPLES_RANDOM))
    share_random = [0.0] * count
    scoop_random = [0.0] * count
    lose_random = [0.0] * count
    for index, _, share, scoop, lose in run_phase(quantiles, [], tasks, "phase 1"):
        share_random[index] = share
        scoop_random[index] = scoop
        lose_random[index] = lose

    # sort from strongest to weakest by pot share against a random opponent
    def by_share(index):
        return share_random[index]

    order = sorted(range(count), key=by_share, reverse=True)
    pct = [0.0] * count
    running = 0
    for index in order:
        running += hands3.class_combos3(index)
        pct[index] = round(100.0 * running / TOTAL_COMBOS, 2)

    names = []
    for index in order[:30]:
        names.append(hands3.class_name3(index) + "(" + str(round(share_random[index], 3)) + ")")
    print("strongest 30:", "; ".join(names))
    names = []
    for index in order[-10:]:
        names.append(hands3.class_name3(index) + "(" + str(round(share_random[index], 3)) + ")")
    print("weakest 10:", "; ".join(names))

    # Phase 2: against "the top r%"
    buckets = combos_by_class()
    top = []
    for index in order:
        for combo in buckets[index]:
            top.append(combo)

    share_table = []
    scoop_table = []
    lose_table = []
    tasks = []
    for percent in GRID:
        share_table.append([0.0] * count)
        scoop_table.append([0.0] * count)
        lose_table.append([0.0] * count)
        if percent < 100:
            top_count = int(TOTAL_COMBOS * percent / 100.0)
            for index in range(count):
                tasks.append((index, top_count, SAMPLES_RANGE))
    slot_of = {}
    for slot in range(len(GRID)):
        slot_of[int(TOTAL_COMBOS * GRID[slot] / 100.0)] = slot
    for index, top_count, share, scoop, lose in run_phase(quantiles, top, tasks, "phase 2"):
        slot = slot_of[top_count]
        share_table[slot][index] = share
        scoop_table[slot][index] = scoop
        lose_table[slot][index] = lose
    last = len(GRID) - 1
    share_table[last] = share_random
    scoop_table[last] = scoop_random
    lose_table[last] = lose_random

    data = {
        "version": 1,
        "variant": "pittsburgh",
        "grid": GRID,
        "pct": pct,
        "order": order,
        "quantiles": quantiles,
        "share": [],
        "scoop": [],
        "lose": [],
    }
    for slot in range(len(GRID)):
        data["share"].append(rounded(share_table[slot]))
        data["scoop"].append(rounded(scoop_table[slot]))
        data["lose"].append(rounded(lose_table[slot]))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    print("wrote", OUT_PATH, round(os.path.getsize(OUT_PATH) / 1024), "KB")


if __name__ == "__main__":
    main()
