/**
 * Card stocks.
 *
 * Every card sits on a slightly different tint of the same pale green-grey,
 * the way a stack of chart paper does when it's come from different batches.
 * The full class strings are written out here rather than built from a
 * template so Tailwind's scanner can see them.
 *
 * Sequences below are hand-ordered rather than cycled from one array: a plain
 * cycle makes adjacent sections repeat the same tint in the same slot, which
 * reads as a pattern instead of as variation.
 */

export const STOCK = {
  1: "bg-stock-1",
  2: "bg-stock-2",
  3: "bg-stock-3",
  4: "bg-stock-4",
  5: "bg-stock-5",
} as const;

/*
 * Ordering rule: neighbours are chosen for the widest gap available, because
 * two of these tints sitting side by side is the only place the difference
 * has to actually register. Stocks 2 and 5 are near-identical in brightness
 * and differ mainly in hue, so they never end up adjacent.
 */

/** Landing — "Who it's for", three across. */
export const STOCKS_AUDIENCE = [STOCK[2], STOCK[1], STOCK[3]];

/** Landing — "What it checks", three across. No position repeats the tint
 *  used in the same slot above, so the two grids don't rhyme down the page. */
export const STOCKS_CHECKS = [STOCK[4], STOCK[3], STOCK[1]];

/** Results — long lists of issue cards. Four tints that step through the
 *  brightness range, so a run of cards varies at every hand-off including
 *  where the sequence wraps. */
export const STOCKS_ISSUES = [STOCK[1], STOCK[3], STOCK[4], STOCK[5]];

export function stockFor(sequence: string[], index: number): string {
  return sequence[index % sequence.length];
}
