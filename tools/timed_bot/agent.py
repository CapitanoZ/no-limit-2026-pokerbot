"""For timing: wraps the real bot and logs every decision's time to /tmp/nl26_times.txt."""

import importlib.util
import os
import time

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "bot", "agent.py")
_SPEC = importlib.util.spec_from_file_location("real_agent", _PATH)
_REAL = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_REAL)


class Agent(_REAL.Agent):
    def act(self, state, memory):
        start = time.perf_counter_ns()
        result = super().act(state, memory)
        spent = time.perf_counter_ns() - start
        boards = state.variant.get("boards") or [[]]
        with open("/tmp/nl26_times.txt", "a") as handle:
            handle.write("%s %d %d\n" % (state.phase, len(boards[0]), spent))
        return result
