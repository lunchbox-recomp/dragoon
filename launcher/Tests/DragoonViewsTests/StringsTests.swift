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

    @Test(arguments: librarySentences)
    func aLibrarySentenceEndsInAFullStop(_ sentence: String) {
        #expect(sentence.hasSuffix(".") || sentence.hasSuffix("…"))
        #expect(!sentence.contains("!"))
    }
}
