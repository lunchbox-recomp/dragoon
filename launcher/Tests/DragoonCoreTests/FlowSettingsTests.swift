import DragoonCore
import Foundation
import Testing

private let wide = PictureSettings(aspect: "16:9", fullscreen: false, scale: 3)

/// Library's Settings sheet. It reads settings.txt as it opens and saves each change, and only
/// while Library is idle, so never while the game runs.
@Suite struct FlowSettingsTests {
    /// Library with the sheet open on `picture`.
    private func sheetOpen(on picture: PictureSettings = PictureSettings()) -> FlowRun {
        var run = launched()
        run.send(.settingsPressed)
        run.send(.pictureRead(picture))
        return run
    }

    @Test func settingsReadsTheFileThenOpensTheSheetOnIt() {
        var run = launched()
        #expect(run.send(.settingsPressed) == [.readPicture])
        #expect(run.state.picture == nil)
        #expect(run.state.waiting == .picture)
        #expect(run.send(.pictureRead(wide)) == [])
        #expect(run.state.picture == wide)
        #expect(run.state.libraryIsIdle)
    }

    @Test func eachChangeIsSavedAsItsMade() {
        var run = sheetOpen()
        var next = PictureSettings()
        next.aspect = "21:9"
        #expect(run.send(.pictureChosen(next)) == [.savePicture(next)])
        next.fullscreen = true
        #expect(run.send(.pictureChosen(next)) == [.savePicture(next)])
        next.scale = 5
        #expect(run.send(.pictureChosen(next)) == [.savePicture(next)])
        #expect(run.state.picture == next)
    }

    @Test func choosingWhatsThereSavesNothing() {
        var run = sheetOpen(on: wide)
        #expect(run.send(.pictureChosen(wide)) == [])
    }

    @Test func aChoiceWithTheSheetClosedSavesNothing() {
        var run = launched()
        #expect(run.send(.pictureChosen(wide)) == [])
        #expect(run.state.picture == nil)
    }

    /// The game reads settings.txt as it starts and its Display page saves it, so a running
    /// game's file is never written over.
    @Test func nothingIsWrittenWhileTheGameRuns() {
        var run = launched()
        _ = run.send(playToStarting)
        #expect(run.state.gameRunning)
        #expect(run.send(.settingsPressed) == [])
        #expect(run.send(.pictureRead(wide)) == [])
        #expect(run.state.picture == nil)
        #expect(run.send(.pictureChosen(wide)) == [])
    }

    @Test func nothingIsWrittenWhileAnEarlierLaunchersGameRuns() {
        var run = launched(earlierGame: 4242)
        #expect(run.send(.settingsPressed) == [])
        var open = run.state
        open.picture = PictureSettings()
        let (next, effects) = Flow.reduce(open, .pictureChosen(wide))
        #expect(effects == [])
        #expect(next.picture == PictureSettings())
    }

    /// A game that's running when a choice comes, however it got there, gets no write.
    @Test(arguments: [Flow.HandOff.charging, .launched, .hidden])
    func aChoiceWhileAGameRunsIsDropped(_ handOff: Flow.HandOff) {
        var state = sheetOpen().state
        state.gameRunning = true
        state.handOff = handOff
        let (next, effects) = Flow.reduce(state, .pictureChosen(wide))
        #expect(effects == [])
        #expect(next.picture == PictureSettings())
    }

    @Test func playWaitsWhileTheSheetIsOpen() {
        var run = sheetOpen()
        #expect(!run.state.canPlay)
        #expect(run.send(.playPressed) == [])
        #expect(run.state.handOff == nil)
        run.send(.settingsDonePressed)
        #expect(run.state.picture == nil)
        #expect(run.send(.playPressed) == [.resolveBookmark(flowBookmark)])
    }

    @Test func settingsWaitsForAResultOnItsWay() {
        var run = launched()
        run.send(.playPressed)
        #expect(run.send(.settingsPressed) == [])
        run = launched()
        run.send(.changeDiscPressed)
        #expect(run.send(.settingsPressed) == [])
    }

    @Test func settingsIsOnlyLibrarys() {
        var run = launched(installed: nil)
        #expect(run.screen != .library)
        #expect(run.send(.settingsPressed) == [])
    }

    @Test func aSecondSettingsWhileTheSheetIsOpenReadsNothing() {
        var run = sheetOpen()
        #expect(run.send(.settingsPressed) == [])
    }

    @Test func aFailedSaveShowsUntilTheNextChangeOrTheSheetCloses() {
        var run = sheetOpen()
        run.send(.pictureChosen(wide))
        run.send(.pictureSaved(.notWritten("No space left on device")))
        #expect(run.state.pictureFailure == .notWritten("No space left on device"))
        var next = wide
        next.scale = 4
        run.send(.pictureChosen(next))
        #expect(run.state.pictureFailure == nil)
        run.send(.pictureSaved(.unreadable("Permission denied")))
        run.send(.settingsDonePressed)
        #expect(run.state.pictureFailure == nil)
        run.send(.pictureSaved(.refused))
        #expect(run.state.pictureFailure == nil)
    }

    @Test func aReadThatComesAfterTheWaitIsOverIsIgnored() {
        var run = launched()
        #expect(run.send(.pictureRead(wide)) == [])
        #expect(run.state.picture == nil)
    }
}
