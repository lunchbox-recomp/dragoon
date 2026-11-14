import DragoonCore
import Foundation
import Testing

private let shownSettings = LauncherSettings(welcomeSeen: true, disc: flowBookmark, pictureCardShown: true)

/// From a launch with no game to the first build's last event, its end left out.
private let firstBuildToDone: [Flow.Event] = [
    .toolsDetected(.ready(flowToolchain)), .chooseDiscPressed,
    .discChosen(path: flowDisc, bookmark: flowBookmark), .discChecked(path: flowDisc, check: .ok),
    .buildPressed, .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc)),
    .discChecked(path: flowDisc, check: .ok), .toolsDetected(.ready(flowToolchain)),
    .build(.done(game: "/x/game/current/Dragoon.app")),
]

/// The one-time "Picture: 4:3 or 16:9" card on the Ready to Play page. It shows once, after the
/// build that made the first game, when settings.txt has no aspect line, and never while a game
/// runs. A pick saves as the Settings sheet's does, and only while the card is idle.
@Suite struct FlowPictureCardTests {
    /// A launch with no game, through the first build to its last event, the build's end left
    /// to the test.
    private func firstBuildDone(
        settings: LauncherSettings = LauncherSettings(welcomeSeen: true, disc: flowBookmark),
        earlierGame: Int32? = nil
    ) -> FlowRun {
        var run = launched(settings: settings, installed: nil, earlierGame: earlierGame)
        _ = run.send(firstBuildToDone)
        return run
    }

    /// The first game's Ready to Play page with the card up on `picture`.
    private func cardUp(on picture: PictureSettings = PictureSettings()) -> FlowRun {
        var run = firstBuildDone()
        run.send(.buildEnded(nil))
        run.send(.pictureCardRead(picture, aspectLine: false))
        return run
    }

    @Test func theFirstGamesPageReadsSettingsThenShowsTheCardAndRemembersIt() {
        var run = firstBuildDone()
        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds, .readPictureCard])
        guard case .build(.finished) = run.screen else {
            Issue.record("the build didn't finish on its page: \(run.screen)")
            return
        }
        #expect(run.state.waiting == .pictureCard)
        #expect(run.state.pictureCard == nil)
        // Play waits for the read, a few lines of a file.
        #expect(!run.state.canPlay)
        #expect(run.send(.pictureCardRead(PictureSettings(), aspectLine: false)) == [.saveSettings(shownSettings)])
        #expect(run.state.pictureCard == Flow.PictureCard(picture: PictureSettings()))
        #expect(run.state.pictureCardIsIdle)
        #expect(run.state.canPlay)
    }

    @Test func aLauncherThatShowedTheCardNeverShowsItAgain() {
        var run = firstBuildDone(settings: shownSettings)
        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds])
        #expect(run.state.waiting == nil)
        #expect(run.send(.pictureCardRead(PictureSettings(), aspectLine: false)) == [])
        #expect(run.state.pictureCard == nil)
    }

    /// A rebuild finishes on the same page, and the card is only the first game's.
    @Test func aLaterBuildShowsNoCard() {
        var run = launched()
        #expect(!run.state.settings.pictureCardShown)
        for (event, _) in rebuildToRunning { run.send(event) }
        run.send(.build(.done(game: "/x/game/current/Dragoon.app")))
        #expect(run.send(.buildEnded(nil)) == [.deleteOldBuilds])
        #expect(run.send(.pictureCardRead(PictureSettings(), aspectLine: false)) == [])
        #expect(run.state.pictureCard == nil)
    }

    @Test(arguments: [PictureSettings(aspect: "4:3"), PictureSettings(aspect: "16:9", scale: 3)])
    func anAspectLineAlreadyThereShowsNoCard(_ picture: PictureSettings) {
        var run = firstBuildDone()
        run.send(.buildEnded(nil))
        #expect(run.send(.pictureCardRead(picture, aspectLine: true)) == [])
        #expect(run.state.pictureCard == nil)
        #expect(run.state.waiting == nil)
        #expect(run.state.canPlay)
        // It wasn't shown, so it isn't remembered as shown.
        #expect(!run.state.settings.pictureCardShown)
    }

    @Test(arguments: Flow.PictureCard.aspects)
    func aPickSavesTheFileAsReadWithItsAspectThenTheCardGoes(_ aspect: String) {
        let read = PictureSettings(aspect: "4:3", fullscreen: true, scale: 3, fastDisc: false)
        var run = cardUp(on: read)
        var saved = read
        saved.aspect = aspect
        #expect(run.send(.pictureCardPicked(aspect)) == [.savePicture(saved)])
        #expect(run.state.waiting == .pictureCard)
        #expect(!run.state.canPlay)
        #expect(run.send(.pictureCardPicked("16:9")) == [])
        #expect(run.send(.pictureSaved(saved, nil)) == [])
        #expect(run.state.pictureCard == nil)
        #expect(run.state.waiting == nil)
        #expect(run.state.canPlay)
    }

    @Test(arguments: ["16:10", "21:9", "window", "5:4", ""])
    func theCardSavesOnlyItsTwoAspects(_ aspect: String) {
        var run = cardUp()
        #expect(run.send(.pictureCardPicked(aspect)) == [])
        #expect(run.state.pictureCard == Flow.PictureCard(picture: PictureSettings()))
    }

    @Test func keepWritesNothingAndTheCardGoes() {
        var run = cardUp()
        #expect(run.send(.pictureCardSkipped) == [])
        #expect(run.state.pictureCard == nil)
        #expect(run.state.settings.pictureCardShown)
        #expect(run.send(.pictureCardPicked("16:9")) == [])
    }

    @Test func aFailedSaveKeepsTheCardWithWhyAndTheNextPickTriesAgain() {
        var run = cardUp()
        let wide = PictureSettings(aspect: "16:9")
        run.send(.pictureCardPicked("16:9"))
        #expect(run.send(.pictureSaved(wide, .notWritten("No space left on device"))) == [])
        #expect(run.state.pictureCard == Flow.PictureCard(picture: wide, failure: .notWritten("No space left on device")))
        #expect(run.state.waiting == nil)
        #expect(run.send(.pictureCardPicked("16:9")) == [.savePicture(wide)])
        #expect(run.state.pictureCard?.failure == nil)
        run.send(.pictureSaved(wide, nil))
        #expect(run.state.pictureCard == nil)
    }

    /// The game reads settings.txt as it starts, so the card is never up while one runs and
    /// a pick that comes while one does saves nothing.
    @Test func noCardWhileAnEarlierLaunchersGameRuns() {
        var run = firstBuildDone(earlierGame: 4242)
        #expect(run.state.gameRunning)
        #expect(run.send(.buildEnded(nil)) == [])
        #expect(run.state.waiting == nil)
        #expect(run.send(.pictureCardRead(PictureSettings(), aspectLine: false)) == [])
        #expect(run.state.pictureCard == nil)
    }

    @Test func aReadThatComesOnceAGameRunsShowsNoCard() {
        var run = firstBuildDone()
        run.send(.buildEnded(nil))
        var state = run.state
        state.gameRunning = true
        let (next, effects) = Flow.reduce(state, .pictureCardRead(PictureSettings(), aspectLine: false))
        #expect(effects == [])
        #expect(next.pictureCard == nil)
        #expect(!next.settings.pictureCardShown)
    }

    @Test(arguments: [nil, Flow.HandOff.charging, .launched, .hidden])
    func noPickIsSavedWhileAGameRuns(_ handOff: Flow.HandOff?) {
        var state = cardUp().state
        state.gameRunning = true
        state.handOff = handOff
        #expect(!state.pictureCardIsIdle)
        for aspect in Flow.PictureCard.aspects {
            let (next, effects) = Flow.reduce(state, .pictureCardPicked(aspect))
            #expect(effects == [])
            #expect(next.pictureCard == Flow.PictureCard(picture: PictureSettings()))
        }
    }

    /// Play passes the card by, so no pick can come while the game starts or runs.
    @Test func playPassesTheCardBy() {
        var run = cardUp()
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
        #expect(run.state.pictureCard == nil)
        #expect(run.send(.pictureCardPicked("16:9")) == [])
        run.send(.bookmarkResolved(.found(flowDisc)))
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == starting(1))
        #expect(run.send(.pictureCardPicked("16:9")) == [])
        #expect(run.send(.pictureCardSkipped) == [])
    }

    @Test func backToLibraryPassesTheCardBy() {
        var run = cardUp()
        run.send(.backToLibraryPressed)
        #expect(run.screen == .library)
        #expect(run.state.pictureCard == nil)
        #expect(run.send(.pictureCardPicked("16:9")) == [])
    }

    @Test func backToLibraryWaitsForTheRead() {
        var run = firstBuildDone()
        run.send(.buildEnded(nil))
        #expect(!run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [])
        guard case .build(.finished) = run.screen else {
            Issue.record("Back left the page during the read: \(run.screen)")
            return
        }
        run.send(.pictureCardRead(PictureSettings(), aspectLine: false))
        #expect(run.state.pictureCard == Flow.PictureCard(picture: PictureSettings()))
        #expect(run.state.canGoBackToLibrary)
    }

    /// Back during the card's save would let Library's Play start the game before the save is
    /// done, and drop a failed save unsaid, so Back waits for its result.
    @Test(arguments: [nil, PictureSettings.SaveFailure.notWritten("No space left on device")])
    func backToLibraryWaitsForTheSave(_ failure: PictureSettings.SaveFailure?) {
        var run = cardUp()
        let wide = PictureSettings(aspect: "16:9")
        run.send(.pictureCardPicked("16:9"))
        #expect(!run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [])
        guard case .build(.finished) = run.screen else {
            Issue.record("Back left the page during the save: \(run.screen)")
            return
        }
        #expect(run.send(.playPressed) == [])
        #expect(run.state.handOff == nil)
        run.send(.pictureSaved(wide, failure))
        #expect(run.state.pictureCard == (failure == nil ? nil : Flow.PictureCard(picture: wide, failure: failure)))
        #expect(run.state.canGoBackToLibrary)
        #expect(run.send(.backToLibraryPressed) == [.deleteOldBuilds])
        #expect(run.screen == .library)
    }

    /// Settings, pressed after Back during the card's save, waits too, so the card's result
    /// can't be taken as the sheet's, and the sheet opens on what the card saved.
    @Test func settingsAfterBackDuringTheSaveLeavesTheSheetToItsOwnRead() {
        var run = cardUp()
        let wide = PictureSettings(aspect: "16:9")
        run.send(.pictureCardPicked("16:9"))
        run.send(.backToLibraryPressed)
        #expect(run.send(.settingsPressed) == [])
        #expect(run.state.picture == nil)
        #expect(run.send(.pictureSaved(wide, nil)) == [])
        #expect(run.state.picture == nil)
        #expect(run.state.savedPicture == nil)
        run.send(.backToLibraryPressed)
        #expect(run.send(.settingsPressed) == [.readPicture])
        run.send(.pictureRead(wide))
        #expect(run.state.picture == wide)
        #expect(run.state.savedPicture == wide)
    }

    /// A save the Settings sheet started isn't the card's, and the card's isn't the sheet's.
    @Test func theCardsSaveResultLeavesTheSheetAlone() {
        var run = cardUp()
        run.send(.pictureCardPicked("16:9"))
        run.send(.pictureSaved(PictureSettings(aspect: "16:9"), nil))
        #expect(run.state.picture == nil)
        #expect(run.state.savedPicture == nil)
        #expect(run.state.pictureFailure == nil)
    }
}

/// The card's pick writes settings.txt byte for byte as the same pick in the Settings sheet,
/// through the same effect and the same `PictureSettings.save`.
@Suite struct PictureCardWriteTests {
    private static let path = fakeData + "/settings.txt"

    /// Files with no aspect line: none, a BOM alone, CR LF with a comment and a last line
    /// without a newline, and LF with bytes that aren't UTF-8.
    static let files: [Data?] = [
        nil,
        Data([0xEF, 0xBB, 0xBF]),
        Data("# mine\r\nscale 3\r\nfullscreen 1\r\nram_patches patches.txt".utf8),
        Data("disc console\n# caf\u{E9}\n".utf8) + Data([0xFF, 0xFE, 0x0A]),
    ]

    private static func fileSystem(_ file: Data?) -> FakeFileSystem {
        let fs = FakeFileSystem()
        if let file { fs.addFile(path, file) }
        return fs
    }

    /// settings.txt after the card's pick of `aspect` over `file`, through the flow.
    private static func cardWrite(_ aspect: String, over file: Data?) throws -> Data {
        let fs = fileSystem(file)
        var run = launched(settings: LauncherSettings(welcomeSeen: true, disc: flowBookmark), installed: nil)
        _ = run.send(firstBuildToDone)
        #expect(run.send(.buildEnded(nil)).contains(.readPictureCard))
        let read = PictureSettings.loadWithAspectLine(from: fakeData, fs: fs)
        run.send(.pictureCardRead(read.settings, aspectLine: read.aspectLine))
        let effects = run.send(.pictureCardPicked(aspect))
        guard case .savePicture(let picture)? = effects.first, effects.count == 1 else {
            Issue.record("the card's pick gave \(effects)")
            return Data()
        }
        try picture.save(to: fakeData, fs: fs)
        return try fs.readData(at: path)
    }

    /// settings.txt after the Settings sheet's pick of `aspect` over `file`, through the flow.
    /// The sheet saves nothing for the aspect it opened on, so for that one the player picks
    /// 21:9 first.
    private static func sheetWrite(_ aspect: String, over file: Data?) throws -> Data {
        let fs = fileSystem(file)
        var run = launched()
        run.send(.settingsPressed)
        let read = PictureSettings.load(from: fakeData, fs: fs)
        run.send(.pictureRead(read))
        let picks = read.aspect == aspect ? ["21:9", aspect] : [aspect]
        for pick in picks {
            var chosen = run.state.picture ?? read
            chosen.aspect = pick
            let effects = run.send(.pictureChosen(chosen))
            guard case .savePicture(let picture)? = effects.first, effects.count == 1 else {
                Issue.record("the sheet's pick gave \(effects)")
                return Data()
            }
            try picture.save(to: fakeData, fs: fs)
            run.send(.pictureSaved(picture, nil))
        }
        return try fs.readData(at: path)
    }

    @Test(arguments: Flow.PictureCard.aspects, files)
    func aPickWritesWhatTheSheetsDoes(_ aspect: String, _ file: Data?) throws {
        let card = try Self.cardWrite(aspect, over: file)
        #expect(card == (try Self.sheetWrite(aspect, over: file)))
        #expect(PictureSettings(parsing: card).aspect == aspect)
    }

    /// The engine's own `settings_save` of the card's values over a file with no keys.
    @Test(arguments: [("bom-only", "16:9"), ("empty", "4:3")])
    func aPickWritesWhatTheEngineDoes(_ name: String, _ aspect: String) throws {
        let fixture = try #require(SettingsFixture.all.first { $0.name == name })
        #expect(fixture.picture == PictureSettings(aspect: aspect))
        #expect(try Self.cardWrite(aspect, over: fixture.before) == fixture.after)
    }
}
