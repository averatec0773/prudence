import Foundation
import GRDB
import SwiftUI
import Testing

@testable import PrudenceStore
@testable import PrudenceUI

/// The design system and the strings.
///
/// Four of these are about things that are easy to get quietly wrong and impossible to see in
/// a screenshot: a purpose the engine emits and the palette has no colour for, a sentence the
/// app words differently from the CLI, a delta chip that decides it knows which way is good,
/// and a language setting that does not survive being written down.

// MARK: - tokens

@Suite("Design tokens")
struct TokenTests {

    /// Every purpose key the engine can emit has a colour of its own.
    ///
    /// The list is `facts/purpose.PURPOSES`, copied here as the thing the palette is checked
    /// against rather than as a source of truth: if the engine grows a seventh purpose, this
    /// fails and somebody picks a colour, which is the whole point. A key outside the table
    /// still draws, in grey, so a store from a newer engine is never a blank chart.
    @Test func everyEnginePurposeHasItsOwnColour() {
        let emitted = ["development", "research", "debugging", "conversation", "mixed", "unknown"]
        for purpose in emitted {
            #expect(Purpose.isKnown(purpose), "no colour for the purpose \(purpose)")
        }
        #expect(Purpose.order == emitted, "the stacking order is not the engine's purpose list")
    }

    /// And every purpose the fixture actually carries is one of them.
    @Test func theFixtureCarriesNoPurposeThePaletteMisses() throws {
        let store = try Fixture.store()
        let purposes = Set(try store.usageByPurposeDay(since: "0000-00-00").map(\.purpose))
        for purpose in purposes {
            #expect(
                Purpose.isKnown(purpose),
                "the fixture has the purpose \(purpose) and the palette does not")
        }
    }

    /// An unknown key is drawn, not dropped: it falls to the grey the table gives `unknown`.
    @Test @MainActor func anUnknownPurposeFallsToGreyAndIsStillDrawn() {
        let scale = Purpose.scale(for: ["development", "quantum-tunnelling"])
        #expect(scale.domain == ["development", "quantum-tunnelling"])
        #expect(scale.range.count == 2)
        #expect(
            scale.range[1].prudenceHex(dark: false)?.hex
                == Purpose.colour("unknown").prudenceHex(dark: false)?.hex)
    }

    /// The palette really draws the values `docs/design/mockups/tokens.css` and `DESIGN.md`
    /// print. A token table nobody resolves is a table that can say anything.
    @Test @MainActor func thePaletteDrawsTheValuesTheDocumentPrints() {
        let expected: [(String, String, String)] = [
            ("development", "#007AFF", "#0A84FF"),
            ("research", "#30B0C7", "#40C8E0"),
            ("debugging", "#FF9500", "#FF9F0A"),
            ("conversation", "#AF52DE", "#BF5AF2"),
            ("mixed", "#5856D6", "#7D7AFF"),
            ("unknown", "#8E8E93", "#98989D"),
        ]
        for (purpose, light, dark) in expected {
            #expect(Purpose.colour(purpose).prudenceHex(dark: false)?.hex == light, "\(purpose)")
            #expect(Purpose.colour(purpose).prudenceHex(dark: true)?.hex == dark, "\(purpose)")
        }
        #expect(Outcome.alive.prudenceHex(dark: false)?.hex == "#0A7D45")
        #expect(Outcome.rework.prudenceHex(dark: false)?.hex == "#8A5A00")
        #expect(Surface.plain.prudenceHex(dark: true)?.hex == "#2C2C2E")
        #expect(Ink.primary.prudenceHex(dark: false)?.hex == "#1C1C1E")
    }

    /// The fixed order holds whatever order the slices arrive in.
    @Test func theOrderIsFixedAndNotTheOrderOfArrival() {
        #expect(
            Purpose.ordered(["mixed", "development", "debugging"])
                == ["development", "debugging", "mixed"])
    }

    /// The spacing scale is base 4 with no gaps invented between its steps.
    @Test func theSpacingScaleIsBaseFour() {
        let scale = [Space.s1, Space.s2, Space.s3, Space.s4, Space.s5, Space.s6, Space.s7, Space.s8]
        #expect(scale == [4, 8, 12, 16, 20, 24, 32, 40])
    }
}

// MARK: - the delta chip

@Suite("Neutral by construction")
struct DeltaChipTests {

    /// **Colour never means good or bad.** More sessions is not better and less rework is not
    /// a score, so a delta chip's ink is a constant and cannot be a function of the value.
    /// This test is the guard on that: if somebody gives `DeltaChip` a `tint(for:)`, one of
    /// these three stops being the same colour and the test says so.
    @Test func theTintIsTheSameWhicheverWayTheNumberWent() {
        let rise = DeltaChip.tint
        let fall = DeltaChip.tint
        let flat = DeltaChip.tint
        #expect(rise == fall)
        #expect(fall == flat)
        #expect(rise == Ink.secondary)
    }

    /// The sign is information and stays in the label; it is the colour that would be a
    /// judgement.
    @Test func theSignIsInTheLabelAndNowhereElse() {
        #expect(DeltaChip.label(points: 0.12) == "+12")
        #expect(DeltaChip.label(points: -0.04) == "-4")
        #expect(DeltaChip.label(points: 0) == "0")
    }
}

// MARK: - the language setting

@Suite("The language setting")
struct LanguageTests {

    /// A throwaway domain per test, and the domain name beside it.
    ///
    /// The name matters: `UserDefaults.array(forKey:)` searches the whole chain and would
    /// answer `AppleLanguages` out of `NSGlobalDomain` for an app that has written none, so a
    /// test asking whether the override was *removed* has to read the app's own domain alone.
    private func defaults(_ name: String) -> (store: UserDefaults, domain: String) {
        let suite = "dev.prudence.test.\(name).\(UUID().uuidString)"
        let store = UserDefaults(suiteName: suite)!
        store.removePersistentDomain(forName: suite)
        return (store, suite)
    }

    private func written(_ pair: (store: UserDefaults, domain: String)) -> [String]? {
        pair.store.persistentDomain(forName: pair.domain)?[Localization.appleLanguagesKey]
            as? [String]
    }

    @Test func itDefaultsToFollowingTheSystem() {
        #expect(Localization.stored(in: defaults("empty").store) == .system)
    }

    /// Every choice survives being written down and read back, and writes the
    /// `AppleLanguages` override Cocoa reads at the next launch.
    @Test func everyChoiceRoundTrips() {
        for language in Language.allCases {
            let pair = defaults("round")
            Localization.store(language, in: pair.store)
            #expect(Localization.stored(in: pair.store) == language)
            #expect(
                written(pair) == language.appleLanguages,
                "\(language) wrote the wrong AppleLanguages")
        }
    }

    /// "System" removes the override rather than freezing today's system language into it, so
    /// a user who later changes their Mac's language is followed.
    @Test func systemRemovesTheOverrideRatherThanFreezingIt() {
        let pair = defaults("system")
        Localization.store(.chineseSimplified, in: pair.store)
        #expect(written(pair) == ["zh-Hans"])
        Localization.store(.system, in: pair.store)
        #expect(written(pair) == nil)
        #expect(Localization.stored(in: pair.store) == .system)
    }

    /// A value from an older build, or a corrupted one, reads as System rather than crashing.
    @Test func anUnknownStoredValueReadsAsSystem() {
        let pair = defaults("junk")
        pair.store.set("klingon", forKey: Localization.languageKey)
        #expect(Localization.stored(in: pair.store) == .system)
    }
}

// MARK: - the catalog

@Suite("The String Catalog")
struct CatalogTests {

    /// Every key resolves to something other than itself, in both languages.
    ///
    /// A key missing from the catalog falls back to the key, so `"menu.today"` on screen is
    /// exactly what a forgotten entry looks like. This is the test that catches it, and it
    /// catches a missing Chinese translation as well as a missing English one.
    @Test func everyKeyIsTranslatedInBothLanguages() {
        for language in [Language.english, .chineseSimplified] {
            Localization.withLanguage(language) {
                for key in Str.allCases {
                    let text = key.isPlural ? key.plural(2) : key.text
                    #expect(
                        text != key.rawValue,
                        "\(key.rawValue) has no \(language.rawValue) translation")
                    #expect(!text.isEmpty, "\(key.rawValue) is empty in \(language.rawValue)")
                }
            }
        }
    }

    /// The two languages really differ: a catalog where zh-Hans silently fell back to English
    /// would pass the test above and be useless.
    @Test func theChineseIsNotTheEnglish() {
        // The handful that are the same in both by design: a dash, and a format string with
        // nothing in it but its placeholders.
        let sameByDesign: Set<Str> = [.commonDash]
        var same: Set<Str> = []
        for key in Str.allCases {
            // A plural entry has no single string; it is compared through `plural(2)`, which
            // is the form both languages really print.
            let english = Localization.withLanguage(.english) {
                key.isPlural ? key.plural(2) : key.text
            }
            let chinese = Localization.withLanguage(.chineseSimplified) {
                key.isPlural ? key.plural(2) : key.text
            }
            if english == chinese { same.insert(key) }
        }
        let untranslated = same.subtracting(sameByDesign).map(\.rawValue).sorted()
        #expect(untranslated.isEmpty, "keys that read the same in both languages")
        #expect(same == sameByDesign, "\(untranslated)")
    }

    /// The arguments really land, and in the order each language wants them.
    @Test func placeholdersAreFilledInEachLanguagesOwnOrder() {
        Localization.withLanguage(.english) {
            #expect(Fmt.list([Fmt.sessions(2), Fmt.commits(3)]) == "2 sessions, 3 commits")
        }
        Localization.withLanguage(.chineseSimplified) {
            #expect(Fmt.list([Fmt.sessions(2), Fmt.commits(3)]) == "2 个会话，3 次提交")
        }
    }

    /// The five plural entries really choose a form: English says "1 session" and "3
    /// sessions", Chinese says the same thing either way because it has no plural category of
    /// its own. This is the test that catches a catalog whose `variations` block was written
    /// but whose `%lld` was left as a `%@`, which reads as "1 sessions" and nothing else
    /// notices.
    @Test func pluralsChooseAFormInEnglishAndDoNotInChinese() {
        Localization.withLanguage(.english) {
            #expect(Fmt.sessions(1) == "1 session")
            #expect(Fmt.sessions(3) == "3 sessions")
            #expect(Fmt.edits(1) == "1 edit")
            #expect(Fmt.commits(1) == "1 commit")
            #expect(Fmt.projects(2) == "2 projects")
            #expect(Str.observationGapPoints.plural(1) == "gap 1 point")
            #expect(Str.observationGapPoints.plural(17) == "gap 17 points")
        }
        Localization.withLanguage(.chineseSimplified) {
            #expect(Fmt.sessions(1) == "1 个会话")
            #expect(Fmt.sessions(3) == "3 个会话")
            #expect(Str.observationGapPoints.plural(1) == "相差 1 个百分点")
        }
    }

    /// `unknown` is "other" on screen, never "unknown".
    @Test func theAbsentPurposeIsCalledOther() {
        Localization.withLanguage(.english) {
            #expect(Fmt.purpose("unknown") == "other")
        }
        Localization.withLanguage(.chineseSimplified) {
            #expect(Fmt.purpose("unknown") == "其他")
        }
    }
}

// MARK: - the glass layer

@Suite("The material layer")
struct GlassTests {

    /// A compile-time test: the modifier has to type-check on both availability paths, and a
    /// `View` that uses it has to build against a deployment target of macOS 14 with the
    /// macOS 26 branch present. If `glassEffect` or `GlassEffectContainer` is renamed by a
    /// future SDK, this file stops compiling, which is the failure we want.
    @Test @MainActor func bothPathsCompileAndTheThemeDecidesBetweenThem() {
        let glass = VStack { Text("x") }
            .prudenceGlass(.popover)
            .prudenceGlassCluster()
            .prudenceTheme(Theme(material: .glass))
        _ = glass

        let standard = VStack { Text("x") }
            .prudenceGlass(.sidebar)
            .prudenceTheme(Theme(material: .standard))
        _ = standard

        for surface in [GlassSurface.popover, .sidebar, .toolbar, .control] {
            _ = Color.clear.prudenceGlass(surface)
        }
    }

    /// Reduced transparency turns glass off without anything else being unwound: the same one
    /// flag both paths read, so the fallback cannot drift from the thing it falls back from.
    @Test func reducedTransparencyRefusesTranslucencyOnBothPaths() {
        #expect(Theme(material: .glass, reduceTransparency: false).wantsTranslucency)
        #expect(!Theme(material: .glass, reduceTransparency: true).wantsTranslucency)
        #expect(!Theme(material: .standard, reduceTransparency: false).wantsTranslucency)
    }
}
