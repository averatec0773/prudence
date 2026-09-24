//! Source locations are configured by the engine. The shell only validates the CLI shape.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Source {
    pub id: String,
    pub kind: String,
    pub label: String,
    pub home: String,
    pub enabled: bool,
    pub exists: bool,
}

pub fn parse(printed: &str) -> Result<Vec<Source>, String> {
    serde_json::from_str(printed).map_err(|error| error.to_string())
}

pub fn add_arguments(kind: &str, name: &str, home: &str) -> Option<Vec<String>> {
    if !["claude_code", "codex"].contains(&kind) || name.trim().is_empty() || home.trim().is_empty()
    {
        return None;
    }
    Some(vec![
        "sources".into(),
        "add".into(),
        "--kind".into(),
        kind.into(),
        "--name".into(),
        name.trim().into(),
        "--home".into(),
        home.trim().into(),
        "--json".into(),
    ])
}

pub fn set_arguments(
    id: &str,
    enabled: bool,
    name: Option<&str>,
    home: Option<&str>,
) -> Option<Vec<String>> {
    if id.trim().is_empty()
        || name.is_some_and(|value| value.trim().is_empty())
        || home.is_some_and(|value| value.trim().is_empty())
    {
        return None;
    }
    let mut args = vec![
        "sources".into(),
        "set".into(),
        id.into(),
        if enabled { "--enabled" } else { "--paused" }.into(),
    ];
    if let Some(name) = name {
        args.extend(["--name".into(), name.trim().into()]);
    }
    if let Some(home) = home {
        args.extend(["--home".into(), home.trim().into()]);
    }
    args.push("--json".into());
    Some(args)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_commands_use_allowlisted_arguments() {
        assert!(add_arguments("other", "x", "/tmp/x").is_none());
        assert!(add_arguments("codex", "", "/tmp/x").is_none());
        assert_eq!(
            add_arguments("codex", "Work", "/tmp/a home").unwrap(),
            vec![
                "sources",
                "add",
                "--kind",
                "codex",
                "--name",
                "Work",
                "--home",
                "/tmp/a home",
                "--json"
            ]
        );
        assert_eq!(
            set_arguments("codex", false, None, None).unwrap(),
            vec!["sources", "set", "codex", "--paused", "--json"]
        );
        assert!(set_arguments("", true, None, None).is_none());
    }

    #[test]
    fn source_list_decodes_exact_cli_fields() {
        let rows = parse(r#"[{"id":"codex","kind":"codex","label":"Codex","home":"/tmp/codex","enabled":false,"exists":true}]"#).unwrap();
        assert_eq!(rows[0].label, "Codex");
        assert!(!rows[0].enabled);
    }
}
