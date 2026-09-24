//! Which repositories Prudence records, and at what level.
//!
//! ## Why the engine is asked rather than the store
//!
//! The store knows which repositories it has **sessions from**. The question this answers
//! is the founder's own, asked of the app on 2026-09-21: "why are only three repositories
//! recorded?" The answer is not in the store, because it is about the repositories that
//! are *not* in it: recording is opt-in per repository, and `prudence init --scan` is the
//! one thing that knows both halves, the history found on disk and the consent recorded
//! in `config.toml`.
//!
//! So this module decodes `prudence init --scan --json` and builds the command line that
//! changes one repository. Nothing here computes: every figure on the Repositories tab is
//! a field of the scan.
//!
//! ## The page sends a key, never a path
//!
//! `prudence init --enable` takes a display name or an identity key and **refuses a
//! path**: `--enable /Users/someone/code/thing` ends in "No repository called ... in the
//! scan". The scan carries `repo_key` for exactly this, so that is what crosses the
//! bridge. The level that reaches the command line is one of [`LEVELS`], matched here, so
//! no string from a page is ever an argument.

use serde::{Deserialize, Serialize};

/// The three positions of the capture control, as the interface offers them.
///
/// `off` is not one of the engine's levels: it is `--disable`. It belongs in the same list
/// because it is the same question asked of one repository, and a switch beside a level
/// picker would be two controls for one answer.
pub const LEVELS: &[&str] = &["off", "metadata-only", "full"];

/// One row of `prudence init --scan --json`, as the engine wrote it.
///
/// `#[serde(default)]` throughout: a scan from an engine that has not learned a field yet
/// is still a scan, and a missing field must not cost the whole list. The group of
/// sessions that belong to no repository arrives with `path: null` and cannot be enabled;
/// the interface draws it as the row it is and offers no control on it.
#[derive(Debug, Clone, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Repository {
    #[serde(default)]
    pub path: Option<String>,
    #[serde(default, alias = "repo_key")]
    pub repo_key: String,
    #[serde(default)]
    pub sessions: i64,
    #[serde(default, alias = "first_at")]
    pub first_at: Option<String>,
    #[serde(default, alias = "last_at")]
    pub last_at: Option<String>,
    #[serde(default)]
    pub enabled: bool,
    /// `full`, `metadata-only`, or nothing at all where the repository is not enabled.
    #[serde(default)]
    pub level: Option<String>,
    /// Whether the path is still on disk. A repository that has been moved or deleted is
    /// still on record and still has sessions, and the tab says so.
    #[serde(default)]
    pub exists: bool,
    /// Which AI coding agents wrote the sessions found in this repository.
    ///
    /// Recording is per repository and covers every agent that worked in it.
    #[serde(default)]
    pub sources: Vec<String>,
}

/// `prudence init --scan --json`, decoded.
pub fn parse(printed: &str) -> Result<Vec<Repository>, String> {
    serde_json::from_str::<Vec<Repository>>(printed).map_err(|error| error.to_string())
}

/// The command line that puts one repository at one level.
///
/// `None` for a level this app does not offer and for a row with no key, which is the
/// group of sessions that belong to no repository: there is nothing to enable.
pub fn arguments(repo_key: &str, level: &str) -> Option<Vec<String>> {
    if repo_key.trim().is_empty() {
        return None;
    }
    let matched = LEVELS.iter().find(|allowed| **allowed == level)?;
    if *matched == "off" {
        return Some(vec!["init".into(), "--disable".into(), repo_key.into()]);
    }
    Some(vec![
        "init".into(),
        "--enable".into(),
        repo_key.into(),
        "--level".into(),
        (*matched).into(),
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Three rows of `prudence init --scan --json`, copied from a run against a copy of
    /// the founder's store on 2026-09-22: one enabled at a level, one never enabled, and
    /// the group of sessions that belong to no repository.
    const PRINTED: &str = r#"[
      {"path": "/Users/someone/code/beatos", "repo_key": "root:df32e8a9",
       "sessions": 65, "first_at": "2026-05-14T18:02:11.855000+00:00",
       "last_at": "2026-08-06T05:06:51.273000+00:00", "enabled": true,
       "level": "full", "exists": true},
      {"path": "/Users/someone/code/offeros", "repo_key": "root:2c3f8baf",
       "sessions": 23, "first_at": "2026-07-14T23:12:11.815000+00:00",
       "last_at": "2026-08-18T01:31:25.008000+00:00", "enabled": false,
       "level": null, "exists": true},
      {"path": null, "repo_key": "no repository", "sessions": 115,
       "first_at": "2026-04-22T21:12:03.542000+00:00",
       "last_at": "2026-09-22T06:46:17.434000+00:00", "enabled": false,
       "level": null, "exists": false}
    ]"#;

    #[test]
    fn every_field_the_tab_shows_is_read_from_the_engines_own_scan() {
        let found = parse(PRINTED).expect("the scan decodes");
        assert_eq!(found.len(), 3);

        assert_eq!(found[0].path.as_deref(), Some("/Users/someone/code/beatos"));
        assert_eq!(found[0].repo_key, "root:df32e8a9");
        assert_eq!(found[0].sessions, 65);
        assert!(found[0].enabled && found[0].exists);
        assert_eq!(found[0].level.as_deref(), Some("full"));

        // Never enabled: no level at all, which is a different statement from `off`.
        assert!(!found[1].enabled);
        assert_eq!(found[1].level, None);

        // The group that cannot be enabled, and is still a row with a count on it.
        assert_eq!(found[2].path, None);
        assert_eq!(found[2].sessions, 115);
        assert!(!found[2].exists);
    }

    /// Today's engine prints no `sources`, and the scan still decodes: the field is empty
    /// and the page draws its own constant. An engine that grows the field is decoded
    /// here too, which is the whole reason it is declared before it exists.
    #[test]
    fn a_scan_without_sources_decodes_and_one_with_them_keeps_them() {
        let found = parse(PRINTED).expect("the scan decodes");
        assert!(found[0].sources.is_empty());

        let later = parse(
            r#"[{"path": "/Users/someone/code/beatos", "repo_key": "root:df32e8a9",
                 "sessions": 65, "enabled": true, "level": "full", "exists": true,
                 "sources": ["claude-code", "codex"]}]"#,
        )
        .expect("a scan that carries sources decodes");
        assert_eq!(later[0].sources, vec!["claude-code", "codex"]);
    }

    #[test]
    fn a_scan_that_is_not_a_list_is_an_error_rather_than_an_empty_tab() {
        assert!(parse("not json").is_err());
        assert!(parse("{}").is_err());
        assert!(parse("[]").expect("an empty scan is a scan").is_empty());
    }

    /// The key is what reaches the command line, because a path is refused by the engine.
    #[test]
    fn the_command_line_names_the_key_and_a_level_this_app_offers() {
        assert_eq!(
            arguments("root:df32e8a9", "metadata-only"),
            Some(vec![
                "init".into(),
                "--enable".into(),
                "root:df32e8a9".into(),
                "--level".into(),
                "metadata-only".into()
            ])
        );
        assert_eq!(
            arguments("root:df32e8a9", "full"),
            Some(vec![
                "init".into(),
                "--enable".into(),
                "root:df32e8a9".into(),
                "--level".into(),
                "full".into()
            ])
        );
        // Off is a disable, and `--level` has no part in it.
        assert_eq!(
            arguments("root:df32e8a9", "off"),
            Some(vec![
                "init".into(),
                "--disable".into(),
                "root:df32e8a9".into()
            ])
        );
    }

    #[test]
    fn nothing_a_page_invents_becomes_an_argument() {
        for level in ["", "FULL", "--force", "metadata", "full --json"] {
            assert_eq!(arguments("root:df32e8a9", level), None, "{level} was taken");
        }
        // The no-repository group has no key to name.
        assert_eq!(arguments("", "full"), None);
        assert_eq!(arguments("   ", "full"), None);
    }
}
