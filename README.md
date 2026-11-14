# NO LIMIT '26 poker bot

My bot for Sequoia's NO LIMIT '26 poker bot competition (Pittsburgh regional, November 2026).
This is the final version, the one that played the last two scored rounds.

## Rules

The game is "Pittsburgh", a no-limit hold'em variant:

- Every player gets three hole cards, and two boards are dealt side by side.
- After the turn betting, everyone discards one hole card face down. The two cards that are
  left play on both boards.
- Each board pays half the pot.

Bots play 8-handed sit-and-go tables: 2,000 starting chips, blinds from 10/20 going up every
20 hands, at most 250 hands. First place scores 50 points, second 30, third 20, the rest 0.
Every decision has to come back within 1 ms.

## Strategy

- **Discard.** Sample opponent hands and run-outs, and keep the two cards with the best combined
  chance of winning the two boards.
- **Preflop, short stack.** With 12 big blinds or fewer, shove or fold. The choice is made in
  expected placement points (ICM), not chips, using call frequencies measured from hand histories.
- **Preflop, deep stack.** Open-raise only the top 8% to 22% of hands, depending on how many
  players are left to act. When someone else raises small and nobody is left behind, re-raise to
  2x with the top 75% of hands: most raisers fold to a re-raise, and this was the most
  profitable play of the day. Re-shove over a raise or call a shove when ICM says it beats folding.
- **Postflop.** Estimate the chance of winning each board by sampling. Bet only when strong on
  both boards; call when the estimated share of the pot beats the price of the call; otherwise
  check or fold. Almost no bluffing, apart from a small flop bet after being the last preflop raiser.
- **Safety.** Every decision starts with a check-or-fold fallback, which is returned if anything
  fails or the chosen action is illegal.

The strategy and all its tunable numbers are in `bot/nl26/strategy.py`. `offline/` builds the
lookup tables the bot uses, and `tools/` holds the timing and hand-history analysis scripts.
