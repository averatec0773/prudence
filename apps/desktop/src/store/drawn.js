/* What is on screen, and whether a new payload would change it.
 *
 * ## The redraw this exists to stop
 *
 * A page's only way to update is to throw its DOM away and build it again: `boot.js`
 * calls `page.render`, and `render` begins with `container.innerHTML = ""`. That is the
 * right shape for a page whose drawn state is a pure function of the store, and it is the
 * wrong thing to do when the store has not moved.
 *
 * It was being done anyway, on every launch and after every ingest. Asking the engine
 * whether a review is ready runs `prudence status`, which opens the store read-write;
 * SQLite checkpoints the write-ahead log when that connection closes; the checkpoint
 * changes the length and modification time of `prudence.db` and `prudence.db-wal`, which
 * is what `watcher.rs` fingerprints. So the watcher announced a change, both pages read
 * the store again, and both rebuilt themselves whole to draw the figures already on the
 * screen. Measured on 2026-09-22 against a copy of the founder's 851 MB store: 440 ms of
 * reading and a 586-node rebuild in the window, 59 nodes in the panel, per launch.
 *
 * ## The rule
 *
 * The shell reads the store once per change and stamps the answer with a `revision`
 * (`src-tauri/src/store.rs`), which moves only when the figures do. A page that is handed
 * the revision it already drew draws nothing.
 *
 * **A setting is not the store.** Language and appearance change what is drawn without
 * touching a single view, so that path passes `force` and redraws whatever the revision
 * says. Anything that changes the drawing without changing the store has to do the same.
 *
 * A shell that stamps no revision is drawn every time. That is what an older build of the
 * shell against a newer page looks like, and drawing too often is the safe end of it.
 */

/** The revision currently on screen, or null for a page that has not drawn yet. */
let drawn = /** @type {number | null} */ (null);

/**
 * Would drawing this payload change anything?
 *
 * @param {any} payload the payload from `store/payload.js`
 * @param {{ force?: boolean }} [options] `force` for a change that is not the store's
 * @returns {boolean}
 */
export function worthDrawing(payload, { force = false } = {}) {
  const revision = payload?.revision;
  if (force) return true;
  if (typeof revision !== "number") return true;
  return revision !== drawn;
}

/** Remember what has just been drawn. Called only once the page has actually drawn it. */
export function nowDrawn(payload) {
  const revision = payload?.revision;
  drawn = typeof revision === "number" ? revision : null;
}

/** Forget it. For a test, and for nothing else: a page draws one store. */
export function forget() {
  drawn = null;
}
