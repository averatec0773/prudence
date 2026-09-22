//! What `prudence config model` says, and the one thing the app may change about it.
//!
//! ## The app never calls a model
//!
//! Nothing in this module talks to a model, and nothing in the app does. The Model tab
//! exists so a reader can see which model the **engine** would use if they asked it to
//! write prose, and so they can set the language that prose is written in. Every other
//! field on that tab is read.
//!
//! **The key is never read, only its name.** `prudence config model` prints the name of
//! the environment variable and whether it is set, and never the value; this module keeps
//! that property by keeping every field as the CLI printed it and adding nothing.
//!
//! ## Why this is parsed and not decoded
//!
//! `prudence config model` has no `--json`. Every other call the app makes to the engine
//! asks for one, which is the rule this file breaks and the reason it is small: the format
//! is seven fixed labels, each followed by two or more spaces and a value, and
//! [`parse`] is tested against the exact output recorded from the CLI. Registered in
//! `DESIGN.md` under Known compromises, to be removed when the command grows `--json`.

use serde::Serialize;

/// The languages `prudence config model --language` accepts. The page sends one of these
/// three words and nothing else can reach the command line.
pub const LANGUAGES: &[&str] = &["system", "en", "zh-Hans"];

/// The model settings, as the engine printed them.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelSettings {
    pub backend: Option<String>,
    pub model_id: Option<String>,
    /// The **name** of the variable holding the key, with the engine's own note about
    /// whether it is set. Never a key.
    pub key_variable: Option<String>,
    pub max_tokens: Option<String>,
    /// The setting and, in the engine's own parentheses, what it resolves to now.
    pub language: Option<String>,
    pub explain: Option<String>,
    /// Where `config.toml` is, as the engine reported it.
    pub config_path: Option<String>,
    /// The word `settings.js` needs to tick the right button: `system`, `en` or
    /// `zh-Hans`. It is the first word of `language`, which is the setting itself rather
    /// than what it currently resolves to.
    pub language_key: Option<String>,
}

/// Every label `prudence config model` prints, in the order it prints them.
///
/// The labels are the parse, not the whitespace. The CLI pads each one to a column, so
/// most are followed by a run of spaces and `key variable` by exactly one, because the
/// label is already as wide as the column: a rule about how many spaces separate the two
/// halves reads six of the seven lines and drops the seventh. None of these is a prefix of
/// another, which is what makes matching on them unambiguous.
const LABELS: &[&str] = &[
    "backend",
    "model id",
    "key variable",
    "max tokens",
    "language",
    "explain",
    "written to",
];

/// `prudence config model`'s output, read.
///
/// A line that does not begin with one of [`LABELS`] is not a setting: the command ends
/// with a sentence or two of advice when no key is set, and those are left out rather than
/// shown as a field with no name.
pub fn parse(text: &str) -> ModelSettings {
    let mut found = ModelSettings::default();
    for line in text.lines() {
        let Some((label, value)) = split(line) else {
            continue;
        };
        match label {
            "backend" => found.backend = Some(value.to_string()),
            "model id" => found.model_id = Some(value.to_string()),
            "key variable" => found.key_variable = Some(value.to_string()),
            "max tokens" => found.max_tokens = Some(value.to_string()),
            "language" => {
                found.language_key = value.split_whitespace().next().map(str::to_string);
                found.language = Some(value.to_string());
            }
            "explain" => found.explain = Some(value.to_string()),
            "written to" => found.config_path = Some(value.to_string()),
            _ => {}
        }
    }
    found
}

/// A label and its value, or nothing when the line is not one of the seven.
fn split(line: &str) -> Option<(&'static str, &str)> {
    let label = LABELS.iter().find(|label| line.starts_with(**label))?;
    let value = line[label.len()..].trim();
    (!value.is_empty()).then_some((*label, value))
}

/// The command line for setting the language.
///
/// The word that reaches the command line is the one out of [`LANGUAGES`], not the string
/// the page sent: the page's string is only ever compared. So there is no path by which a
/// value from a page becomes an argument, which is the same rule `installer.rs` keeps.
pub fn language_arguments(language: &str) -> Option<[&'static str; 4]> {
    let matched = LANGUAGES.iter().find(|allowed| **allowed == language)?;
    Some(["config", "model", "--language", matched])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Copied from a terminal on 2026-09-22, `prudence config model` with no key set.
    const PRINTED: &str = "\
backend      anthropic
model id     claude-sonnet-5
key variable ANTHROPIC_API_KEY (not set)
max tokens   1024
language     system (now en, English; model prose only)
explain      off (review.explain)
written to   /Users/someone/Library/Application Support/prudence/config.toml
ANTHROPIC_API_KEY is not set, so no model call can be made. Everything else works without one.
Change it with `prudence config model --backend ... --model-id ...`.
";

    #[test]
    fn every_field_the_model_tab_shows_is_read_from_the_engines_own_output() {
        let found = parse(PRINTED);
        assert_eq!(found.backend.as_deref(), Some("anthropic"));
        assert_eq!(found.model_id.as_deref(), Some("claude-sonnet-5"));
        assert_eq!(
            found.key_variable.as_deref(),
            Some("ANTHROPIC_API_KEY (not set)")
        );
        assert_eq!(found.max_tokens.as_deref(), Some("1024"));
        assert_eq!(
            found.language.as_deref(),
            Some("system (now en, English; model prose only)")
        );
        assert_eq!(found.explain.as_deref(), Some("off (review.explain)"));
        assert_eq!(
            found.config_path.as_deref(),
            Some("/Users/someone/Library/Application Support/prudence/config.toml")
        );
    }

    /// The control on the tab is set from the **setting**, not from what it resolves to.
    /// Ticking English because a machine in English resolved `system` to English would
    /// make the control lie the moment the machine's language changed.
    #[test]
    fn the_language_control_reads_the_setting_and_not_what_it_resolves_to() {
        assert_eq!(parse(PRINTED).language_key.as_deref(), Some("system"));
        assert_eq!(
            parse("language     zh-Hans (now zh-Hans, 简体中文; model prose only)")
                .language_key
                .as_deref(),
            Some("zh-Hans")
        );
    }

    /// `key variable` is the one label already as wide as the column it is padded to, so
    /// exactly one space follows it where the others have a run. A rule about how many
    /// spaces separate the two halves read six lines and dropped this one, which is the
    /// line the whole tab's promise rests on.
    #[test]
    fn the_label_that_is_followed_by_one_space_is_read_like_the_rest() {
        assert_eq!(
            parse("key variable ANTHROPIC_API_KEY (not set)")
                .key_variable
                .as_deref(),
            Some("ANTHROPIC_API_KEY (not set)")
        );
    }

    /// The advice the command prints when no key is set is prose, not a setting. A split
    /// on the first space would have made "ANTHROPIC_API_KEY" a field.
    #[test]
    fn the_sentences_under_the_settings_are_not_fields() {
        let found = parse(PRINTED);
        let printed = format!("{found:?}");
        assert!(
            !printed.contains("no model call can be made"),
            "a sentence was read as a setting: {printed}"
        );
    }

    /// The whole promise of this tab. The engine prints the variable's name and whether it
    /// is set, and this module adds nothing, so there is no path by which a key value
    /// could reach a screen.
    #[test]
    fn the_key_variable_is_a_name_and_the_engine_never_prints_a_value() {
        let found = parse(PRINTED);
        let variable = found.key_variable.unwrap();
        assert!(variable.starts_with("ANTHROPIC_API_KEY"));
        assert!(variable.ends_with("(not set)"));
    }

    #[test]
    fn output_this_build_cannot_read_is_empty_rather_than_wrong() {
        assert_eq!(parse(""), ModelSettings::default());
        assert_eq!(parse("something went wrong\n"), ModelSettings::default());
    }

    /// Only the three words the tab offers can become a command line.
    #[test]
    fn only_the_three_languages_the_tab_offers_reach_the_command_line() {
        assert_eq!(
            language_arguments("zh-Hans"),
            Some(["config", "model", "--language", "zh-Hans"])
        );
        assert_eq!(
            language_arguments("system"),
            Some(["config", "model", "--language", "system"])
        );
        for other in ["", "fr", "--force", "en; rm -rf /"] {
            assert_eq!(language_arguments(other), None, "{other} is not a language");
        }
    }
}
