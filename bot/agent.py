"""Entry point of the competition bot.

Each time it is the bot's turn, the engine calls Agent.act once:
  1. Prepare a fallback action first; if any later step fails, return the fallback.
  2. Record what just happened at the table into memory (per-opponent statistics).
  3. Ask the strategy (nl26/strategy.py) for an action and return it if it is legal.
"""

import os
import sys

# The competition machines pin these math libraries to a single thread. These lines must come
# before any other import so that local timings match the competition.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"

# Make sure the nl26 package sitting next to agent.py can be imported
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import poker_agent_sdk  # noqa: E402
from poker_agent_sdk import Action  # noqa: E402
from poker_agent_protocol.game import is_legal, passive_action  # noqa: E402

from nl26 import pgh, strategy, table_memory  # noqa: E402

# Load the tables once here; every decision afterwards is just a lookup
TABLES = pgh.Tables()
# Run one throwaway computation so the libraries finish initializing before the first decision
pgh.keep_scores(TABLES, ("As", "Kd", "7c"), (["2s", "9h", "Jd", "4c"], ["3s", "8h", "Qd", "5c"]))
pgh.sampled_strength(TABLES, ("As", "Kd", "7c"), (["2s", "9h", "Jd", "4c"], ["3s", "8h", "Qd", "5c"]), 2)


class Agent(poker_agent_sdk.Agent):
    def act(self, state, memory):
        # Step 1: fallback (check if possible, otherwise fold; in the discard phase, drop the lowest card)
        legal_actions = state.legal_actions
        fallback = passive_action(legal_actions)

        # Step 2: update memory. If the memory is corrupt, start over instead of failing every time
        try:
            stats = table_memory.decode(memory)
            table_memory.update(stats, state.events)
            new_memory = table_memory.encode(stats)
        except Exception:
            stats = table_memory.TableStats()
            new_memory = b""

        # Step 3: decide. On any error, or if the chosen action is illegal, return the fallback
        try:
            action = strategy.decide(state, stats, TABLES)
            if action is None or not is_legal(action, legal_actions):
                return fallback, new_memory
            return action, new_memory
        except Exception:
            return fallback, new_memory
