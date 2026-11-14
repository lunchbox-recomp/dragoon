import DragoonCore
import Testing

@testable import DragoonViews

/// Library's sentences end in a full stop, or an ellipsis while something runs, and never in
/// "!". A snapshot can't see that: "play." to "play!" moves fewer pixels than it allows.
struct StringsTests {
    static let crash = GameProblem.exited(.signal(11), panic: nil)

    static let librarySentences: [String] = [
        Strings.playStatus(.ready), Strings.playStatus(.checkingDisc),
        Strings.playStatus(.playing), Strings.rebuildOffer(.otherVersion),
        Strings.rebuildOffer(.unknownVersion), Strings.gameFailed(crash),
        Strings.gameFailed(.exited(.status(1), panic: nil)),
        Strings.gameFailed(.couldNotStart(
            reason: Strings.gameStart(.missing(path: "/Users/Test Player/Dragoon.app")))),
        Strings.panicCut,
    ] + [Flow.HandOff.charging, .launched, .hidden].compactMap(Strings.launchCard)

    /// The Settings sheet's sentences, which follow Library's rule.
    static let settingsSentences: [String] =
        PictureSettings.aspects.map(Strings.aspectNote) + [
            Strings.windowNote(PictureSettings(aspect: "16:9"), display: nil),
            Strings.windowNote(PictureSettings(aspect: "16:9", fullscreen: true), display: nil),
            Strings.windowNote(PictureSettings(aspect: "4:3", fullscreen: true), display: testDisplay),
            Strings.windowNote(PictureSettings(aspect: "window", fullscreen: true), display: testDisplay),
            Strings.scaleNote(2), Strings.settingsWhen, Strings.pictureFailure(.refused),
            Strings.pictureFailure(.unreadable("Permission denied.")),
            Strings.pictureFailure(.notWritten("No space left on device.")),
        ]

    @Test(arguments: librarySentences + settingsSentences)
    func aLibrarySentenceEndsInAFullStop(_ sentence: String) {
        #expect(sentence.hasSuffix(".") || sentence.hasSuffix("…"))
        #expect(!sentence.contains("!"))
    }
}
