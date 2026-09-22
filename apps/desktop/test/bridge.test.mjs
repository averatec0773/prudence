/* The seam between the page and the shell.
 *
 * This is the riskiest thing in the app and nothing was checking it. A command's name
 * and its argument names have to match `lib.rs` exactly; rename a Rust parameter and the
 * page breaks at runtime with no error on either side, because neither language can see
 * the other. So the two files are parsed and compared.
 *
 * And the rule the whole Electron exit rests on: no Tauri API outside `bridge.js`.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, "..");

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const frontend = walk(join(app, "src")).filter((path) => path.endsWith(".js"));
const bridgeSource = readFileSync(join(app, "src/bridge.js"), "utf8");
const shellSource = readFileSync(join(app, "src-tauri/src/lib.rs"), "utf8");
const watcherSource = readFileSync(join(app, "src-tauri/src/watcher.rs"), "utf8");
const installerSource = readFileSync(join(app, "src-tauri/src/installer.rs"), "utf8");

/** Every `invoke("name", { a, b })` in the bridge, as name -> sorted argument names. */
function commandsTheBridgeCalls() {
  /** @type {Record<string, string[]>} */
  const found = {};
  const pattern = /invoke\(\s*"([a-z_]+)"\s*(?:,\s*\{([^}]*)\})?\s*\)/g;
  for (const [, name, args] of bridgeSource.matchAll(pattern)) {
    found[name] = (args ?? "")
      .split(",")
      .map((pair) => pair.split(":")[0].trim())
      .filter(Boolean)
      .sort();
  }
  return found;
}

/** Every `#[tauri::command] fn name(...)` in the shell, as name -> sorted argument
 *  names, leaving out the ones Tauri injects (`app`, `window`, and managed state). */
function commandsTheShellOffers() {
  /** @type {Record<string, string[]>} */
  const found = {};
  const pattern = /#\[tauri::command[^\]]*\]\s*(?:async\s+)?fn\s+([a-z_]+)\s*\(([^)]*)\)/g;
  for (const [, name, params] of shellSource.matchAll(pattern)) {
    // `shell: State<'_, Shell>` carries a comma inside its generics, so the parameter
    // list cannot be split until they are gone.
    found[name] = params
      .replace(/<[^<>]*>/g, "")
      .split(",")
      .map((param) => param.split(":")[0].trim())
      .filter(Boolean)
      .filter((arg) => !["app", "window", "shell", "webview"].includes(arg))
      .sort();
  }
  return found;
}

test("every command the bridge calls exists in the shell, with the same arguments", () => {
  const bridge = commandsTheBridgeCalls();
  const shell = commandsTheShellOffers();
  assert.ok(Object.keys(bridge).length >= 8, "the bridge should call the shell's commands");
  for (const [name, args] of Object.entries(bridge)) {
    assert.ok(shell[name], `the shell has no command called ${name}`);
    assert.deepEqual(
      args,
      shell[name],
      `${name}: the page sends ${JSON.stringify(args)} and the shell wants ${JSON.stringify(shell[name])}`
    );
  }
});

test("every command the shell offers is reachable through the bridge", () => {
  const bridge = commandsTheBridgeCalls();
  const shell = commandsTheShellOffers();
  const unreachable = Object.keys(shell).filter((name) => !bridge[name]);
  assert.deepEqual(unreachable, [], `commands nothing can call: ${unreachable.join(", ")}`);
});

test("every command in the handler list is a command, and every command is in it", () => {
  const listed = shellSource
    .slice(shellSource.indexOf("generate_handler!["), shellSource.indexOf("])", shellSource.indexOf("generate_handler![")))
    .split("\n")
    .slice(1)
    .map((line) => line.trim().replace(/,$/, ""))
    .filter((line) => /^[a-z_]+$/.test(line))
    .sort();
  assert.deepEqual(listed, Object.keys(commandsTheShellOffers()).sort());
});

/* The rule the Electron exit rests on. If this fails, the frontend can no longer be
   moved to another shell by rewriting one file. */
test("no file in the frontend except bridge.js touches a Tauri API", () => {
  const offenders = frontend
    .filter((path) => !path.endsWith("bridge.js"))
    .filter((path) => /__TAURI__|@tauri-apps|\binvoke\s*\(/.test(readFileSync(path, "utf8")))
    .map((path) => relative(app, path));
  assert.deepEqual(offenders, []);
});


/* Commands are only half the seam. The shell also **emits**, and an event name is a
   string on both sides with nothing to catch a rename: `cargo test` green, `node --test`
   green, CI green, and the window quietly stops following the store. This test exists
   because that was the one direction the bridge test did not cover. */
test("every event the shell emits is an event the bridge listens for", () => {
  const listened = [...bridgeSource.matchAll(/event\.listen\(\s*"([^"]+)"/g)].map((m) => m[1]);

  // One row per event: where it is declared, what the constant is called, and where the
  // shell emits it. Three events now, and each one is a string on both sides with nothing
  // but this to catch a rename.
  const events = [
    ["watcher.rs", watcherSource, "STORE_CHANGED", watcherSource],
    ["lib.rs", shellSource, "SETTINGS_CHANGED", shellSource],
    ["installer.rs", installerSource, "INSTALL_PROGRESS", shellSource],
  ];

  for (const [file, declared, name, emitter] of events) {
    const found = declared.match(new RegExp(`const ${name}: &str = "([^"]+)"`));
    assert.ok(found, `${file} no longer declares ${name}`);
    assert.ok(
      listened.includes(found[1]),
      `the shell emits "${found[1]}" and bridge.js listens for ${JSON.stringify(listened)}`
    );
    // And the shell must actually emit the constant, not a literal that drifted from it.
    assert.ok(
      new RegExp(`emit\\(\\s*(?:installer::)?${name}`).test(emitter),
      `${name} is declared and never emitted`
    );
  }
});
