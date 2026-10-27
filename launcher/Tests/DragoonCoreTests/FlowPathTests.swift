import DragoonCore
import Foundation
import Testing

/// Where the launcher can run from. One that can't asks to be moved and does nothing else.
@Suite struct FlowPathTests {
    @Test func aTranslocatedLauncherAsksToBeMoved() {
        let translocated = "/private/var/folders/x1/abc/T/AppTranslocation/8E9C1A2B-77D0/d/Dragoon.app"
        let run = launched(appPath: translocated)
        #expect(run.screen == .mustMove(.translocated))
        #expect(run.effects == [])
    }

    @Test func aTranslocatedLauncherIsNamedForThatOnItsReadOnlyMountToo() {
        let translocated = "/private/var/folders/x1/abc/T/AppTranslocation/8E9C1A2B-77D0/d/Dragoon.app"
        #expect(launched(appPath: translocated, onReadOnlyVolume: true).screen == .mustMove(.translocated))
    }

    @Test func aLauncherOnAReadOnlyVolumeAsksToBeMoved() {
        let run = launched(appPath: "/Volumes/Dragoon 1.0/Dragoon.app", onReadOnlyVolume: true)
        #expect(run.screen == .mustMove(.readOnlyVolume))
        #expect(run.effects == [])
    }

    /// The kit's Makefile refuses these five, so the cases are listed here rather than taken
    /// from the code under test.
    @Test(arguments: ["$", "\"", "`", ":", ";"] as [Character])
    func aPathHoldingACharacterTheKitRefusesAsksToBeMoved(character: Character) {
        let path = flowHome + "/Apps \(character) Games/Dragoon.app"
        var run = launched(appPath: path)
        #expect(run.screen == .mustMove(.refusedCharacter(character)))
        #expect(run.effects == [])
        #expect(run.send(.playPressed) == [])
        #expect(run.send(.quitPressed) == [.quit])
    }

    @Test func theRefusedCharactersAreTheKitsFive() {
        #expect(MoveReason.refusedCharacters == ["$", "\"", "`", ":", ";"])
    }

    @Test func theFirstRefusedCharacterInThePathIsTheOneNamed() {
        let path = flowHome + "/a;b/c:d/Dragoon.app"
        #expect(launched(appPath: path).screen == .mustMove(.refusedCharacter(";")))
    }

    @Test(arguments: [
        flowApp,
        "/Applications/Dragoon.app",
        flowHome + "/Applications/Games (2027)/Kirby's Ride & Co/Dragoon.app",
        flowHome + "/Applications/Jeux vidéo/Dragoon.app",
        "/Users/Shared/AppTranslocation-notes/Dragoon.app",
    ])
    func aPathWithSpacesAndOtherPunctuationIsFine(path: String) {
        #expect(MoveReason(appPath: path, onReadOnlyVolume: false) == nil)
        #expect(launched(appPath: path).screen == .library)
    }
}
