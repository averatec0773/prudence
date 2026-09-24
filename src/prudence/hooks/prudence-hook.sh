#!/bin/sh
# Prudence capture hook. Claude Code runs it once per hook event, synchronously, with
# the hook JSON on standard input and the event name as the first argument.
#
# Four rules shape every line below.
#
#   1. It never fails. Nothing here uses `set -e`, every command that can fail is
#      guarded, and the script always exits 0. A hook that errors interrupts the
#      developer's session, and no recorder is worth that.
#   2. It writes no message text. Only ids, the working directory, a git HEAD, a branch
#      name, a fingerprint of `git status --porcelain` and two numbers ever reach the
#      spool. The prompt itself arrives on stdin at `UserPromptSubmit` and is never read
#      out of the JSON.
#   3. It writes nothing at all unless the working directory sits under a repository the
#      user enabled. The enabled list is a plain text file, one absolute path per line,
#      written by `prudence hooks install`, so this script never parses TOML.
#   4. `PRUDENCE_INTERNAL=1` short-circuits it before anything else happens, so
#      Prudence's own `claude -p` calls (decision T6) never record themselves.
#
# Parsing is done with one `awk` pass over five known top-level keys rather than with a
# JSON parser, because there is no portable one in a shell and spawning an interpreter
# costs more than everything else here put together. The values are sanitised to a
# small character set, which both keeps the output valid JSON without escaping and
# means a crafted value cannot inject a field. A value containing an escaped quote
# would be truncated; none of the five keys ever carries one.

[ -n "${PRUDENCE_INTERNAL:-}" ] && exit 0

event_arg=${1:-}
source_kind=${2:-claude_code}
source_id=${3:-claude}
case "$source_kind" in claude_code|codex) ;; *) exit 0 ;; esac
case "$source_id" in *[!A-Za-z0-9_-]*) exit 0 ;; esac
# Codex Stop requires a JSON response; no instruction or blocking decision is returned.
if [ "$source_kind" = codex ]; then
    trap 'printf "{}\n"' EXIT
fi

# The data directory. This script is installed at <data dir>/hooks/prudence-hook.sh, so
# it can find its own store with no configuration at all; the variable is for tests.
if [ -n "${PRUDENCE_DATA_DIR:-}" ]; then
    data_dir=$PRUDENCE_DATA_DIR
else
    self=$0
    case "$self" in
        /*) ;;
        *) self=$(pwd)/$self ;;
    esac
    data_dir=$(dirname "$(dirname "$self")")
fi
enabled_file=$data_dir/hooks/enabled.txt
spool=$data_dir/spool.jsonl
sources_file=$data_dir/hooks/sources-enabled.txt
if [ -f "$sources_file" ]; then
    grep -Fxq "$source_id" "$sources_file" 2>/dev/null || exit 0
fi

# A millisecond clock, from whatever this machine has. GNU date does it alone; BSD date
# (macOS) does not, so perl's Time::HiRes stands in, and seconds are the last resort.
# One call returns the ISO timestamp and the epoch milliseconds together, so the two
# never disagree and the elapsed measurement costs one extra process, not two.
clock=seconds
probe=$(date -u +%s%3N 2>/dev/null)
case "$probe" in
    '' | *[!0-9]*) ;;
    *) clock=gnu ;;
esac
if [ "$clock" = seconds ] && command -v perl >/dev/null 2>&1; then
    clock=perl
fi

now() {
    case $clock in
        gnu)
            date -u '+%Y-%m-%dT%H:%M:%S.%3NZ %s%3N' 2>/dev/null
            ;;
        perl)
            perl -MTime::HiRes -e 'my $t = Time::HiRes::time(); my @g = gmtime(int($t)); printf("%04d-%02d-%02dT%02d:%02d:%02d.%03dZ %.0f", $g[5] + 1900, $g[4] + 1, $g[3], $g[2], $g[1], $g[0], ($t - int($t)) * 1000, $t * 1000)' 2>/dev/null
            ;;
        *)
            printf '%s %s000' "$(date -u '+%Y-%m-%dT%H:%M:%S.000Z' 2>/dev/null)" \
                "$(date -u +%s 2>/dev/null)"
            ;;
    esac
}

started=$(now)
ts=${started% *}
start_ms=${started##* }
case "$start_ms" in
    '' | *[!0-9]*) start_ms=0 ;;
esac

payload=$(cat 2>/dev/null)
fields=$(printf '%s' "$payload" | tr '\n\t' '  ' | awk '
function pull(key,   at, rest, end, out) {
    at = index($0, "\"" key "\"")
    if (at == 0) return ""
    rest = substr($0, at + length(key) + 2)
    sub(/^[ ]*:[ ]*/, "", rest)
    if (substr(rest, 1, 1) != "\"") return ""
    rest = substr(rest, 2)
    end = index(rest, "\"")
    if (end == 0) return ""
    out = substr(rest, 1, end - 1)
    gsub(/[^A-Za-z0-9 _.\/:+@-]/, "", out)
    return out
}
{
    printf "%s|%s|%s|%s|%s|%s|%s", pull("session_id"), pull("prompt_id"),
        pull("tool_use_id"), pull("cwd"), pull("hook_event_name"), pull("tool_name"), pull("turn_id")
}
' 2>/dev/null)

# A non-whitespace separator, so an empty id stays an empty field instead of shifting
# every later one along. The separator itself was sanitised out of the values above.
IFS='|' read -r session_id prompt_id tool_use_id cwd event_name tool_name turn_id <<SPOOL_FIELDS
$fields
SPOOL_FIELDS

[ -n "$prompt_id" ] || prompt_id=$turn_id

event=$event_arg
[ -n "$event" ] || event=$event_name
[ -n "$cwd" ] || cwd=$(pwd 2>/dev/null)

[ -f "$enabled_file" ] || exit 0
enabled=0
while IFS= read -r root || [ -n "$root" ]; do
    case $root in
        '' | '#'*) continue ;;
    esac
    case $cwd in
        "$root" | "$root"/*)
            enabled=1
            break
            ;;
    esac
done <"$enabled_file"
[ "$enabled" = 1 ] || exit 0

hasher=
if command -v shasum >/dev/null 2>&1; then
    hasher=shasum
elif command -v sha256sum >/dev/null 2>&1; then
    hasher=sha256sum
fi

head_hash=$(git -C "$cwd" rev-parse HEAD 2>/dev/null)
case "$head_hash" in
    *[!0-9a-f]*) head_hash= ;;
esac
branch=$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null |
    tr -cd 'A-Za-z0-9._/-' 2>/dev/null)
porcelain=$(git -C "$cwd" status --porcelain 2>/dev/null)

dirty_count=0
if [ -n "$porcelain" ]; then
    dirty_count=$(printf '%s\n' "$porcelain" | grep -c '^' 2>/dev/null)
    case "$dirty_count" in
        '' | *[!0-9]*) dirty_count=0 ;;
    esac
fi

# The clean tree hashes too, so a clean fingerprint is a value and not an absence.
fingerprint=
if [ -n "$hasher" ]; then
    if [ "$hasher" = shasum ]; then
        fingerprint=$(printf '%s' "$porcelain" | shasum -a 256 2>/dev/null | cut -c1-16)
    else
        fingerprint=$(printf '%s' "$porcelain" | sha256sum 2>/dev/null | cut -c1-16)
    fi
    case "$fingerprint" in
        *[!0-9a-f]*) fingerprint= ;;
    esac
fi

ended=$(now)
end_ms=${ended##* }
case "$end_ms" in
    '' | *[!0-9]*) end_ms=$start_ms ;;
esac
elapsed_ms=$((end_ms - start_ms))
[ "$elapsed_ms" -ge 0 ] || elapsed_ms=0

mkdir -p "$data_dir" 2>/dev/null
# One printf of one short line to a file opened O_APPEND, so two hooks firing at once
# cannot interleave. Every value below was sanitised, so none of them needs escaping.
printf '{"event":"%s","ts":"%s","session_id":"%s","prompt_id":"%s","tool_use_id":"%s","cwd":"%s","head":"%s","branch":"%s","dirty_fingerprint":"%s","dirty_count":%s,"elapsed_ms":%s,"source":"%s","source_id":"%s","tool_name":"%s","capture_version":2}\n' \
    "$event" "$ts" "$session_id" "$prompt_id" "$tool_use_id" "$cwd" "$head_hash" \
    "$branch" "$fingerprint" "$dirty_count" "$elapsed_ms" \
    "$source_kind" "$source_id" "$tool_name" >>"$spool" 2>/dev/null

exit 0
