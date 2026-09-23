/* What the engine says about itself, remembered against the store it was asked for.
 *
 * ## The loop this exists to stop
 *
 * Every question the app puts to the engine is a **subprocess**. A surface that asks on
 * every draw asks on every store change, because the store watcher redraws every page when
 * the store moves. That closes a circle: the engine opens the store read-write, SQLite
 * checkpoints the write-ahead log when the last connection closes, the checkpoint changes
 * the length and the modification time of `prudence.db` and `prudence.db-wal`, and those
 * two files are exactly what `watcher.rs` fingerprints. One ask, one announcement, one
 * redraw, one ask.
 *
 * `store/readiness.js` was written when the readiness line was the only question asked
 * that way, and it holds the measurement that found it. The Settings screen then grew two
 * more: the Repositories tab runs `prudence init --scan --json` and the Model tab runs
 * `prudence config model`, both on every render of the screen, and the five panes are all
 * built whichever tab is open. Measured on 2026-09-22 by pressing Ingest now with the
 * window left on Settings: an ingest announces itself eight times as it works, so one
 * 230-second run cost fourteen extra processes, each `init --scan` walking every
 * repository on the machine while the engine was busy writing the store.
 *
 * ## The rule
 *
 * The answer is a function of what the engine has recorded, so it is remembered against
 * the store's own evidence of that: the last ingest's timestamp and the newest review's
 * id. A redraw that carries the same two is a redraw of the same store, and the remembered
 * answer is handed back without asking anything. An ingest or a review moves one of them
 * and the next draw asks again, which is what "it follows the store" means.
 *
 * **Not the payload's `revision`.** That moves whenever any figure moves, which during an
 * ingest is once per announcement, so a memo against it would ask eight times for one run.
 * These two values move once, when the run has finished writing.
 *
 * A failure is not remembered: the memo is dropped so the next draw tries again, and the
 * rejection still reaches the caller rather than being swallowed here.
 *
 * A command of the caller's own may change the answer without moving the store at all:
 * `prudence init --enable` writes `config.toml`, which no stamp sees. Such a caller hands
 * the engine's fresh answer back with `keep`, so the next draw serves that rather than the
 * answer from before the change.
 */

/**
 * The store's own evidence that anything the engine would answer differently has changed.
 *
 * Not a fingerprint of the file: the file moves when the engine merely reads it, which is
 * the whole defect above. These are two values the engine writes.
 *
 * @param {any} data the payload from `store/payload.js`
 * @returns {string}
 */
export function storeStamp(data) {
  const ingest = data?.status?.last_ingest_at ?? "";
  const review = data?.reviews?.[0]?.id ?? "";
  return `${ingest}|${review}`;
}

/**
 * One remembered answer, and the store it was taken against.
 *
 * @returns {{
 *   ask: (data: any, run: () => Promise<any>) => Promise<any>,
 *   keep: (data: any, answer: any) => void,
 *   forget: () => void,
 * }}
 */
export function memo() {
  /** The store the remembered answer was taken against. */
  let at = /** @type {string | null} */ (null);
  /** The answer, or the promise of one still in flight. */
  let asked = /** @type {Promise<any> | null} */ (null);

  return {
    ask(data, run) {
      const stamp = storeStamp(data);
      if (asked && at === stamp) return asked;
      at = stamp;
      const answer = Promise.resolve(run());
      asked = answer;
      answer.catch(() => {
        // Only if nothing else has asked since: a later draw's answer is not this one's to
        // throw away.
        if (asked === answer) {
          at = null;
          asked = null;
        }
      });
      return answer;
    },

    keep(data, answer) {
      at = storeStamp(data);
      asked = Promise.resolve(answer);
    },

    forget() {
      at = null;
      asked = null;
    },
  };
}

/* The two the Settings and Repositories screens ask. They are here rather than in either
   screen because the page contract lets a screen keep its **navigation** between renders
   and nothing else, and an answer from the engine is data. */

/** What `prudence config model` prints. */
export const MODEL_ANSWER = memo();

/** What `prudence init --scan --json` prints. */
export const REPOSITORY_SCAN = memo();
