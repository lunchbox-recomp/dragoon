import DragoonCore
import Foundation
import Testing

/// The disc's banner: read once a disc passes its check and there's none in the cache yet.
@Suite struct FlowBannerTests {
    @Test func aCachedBannerIsThereFromTheStart() {
        #expect(launched().state.banner == flowBanner)
        #expect(launched(banner: nil).state.banner == nil)
    }

    @Test func theFirstDiscThatPassesHasItsBannerRead() {
        var run = launched(settings: LauncherSettings(welcomeSeen: true), installed: nil, banner: nil)
        _ = run.send([
            .toolsDetected(.ready(flowToolchain)), .chooseDiscPressed,
            .discChosen(path: flowDisc, bookmark: flowBookmark),
        ])
        #expect(run.send(.discChecked(path: flowDisc, check: .ok)) == [
            .saveSettings(LauncherSettings(welcomeSeen: true, disc: flowBookmark)),
            .readBanner(flowDisc),
        ])
    }

    @Test func playWithNoBannerStartsTheGameAndReadsIt() {
        var run = launched(banner: nil)
        let effects = run.send(playToStarting)
        #expect(effects.last == starting(1) + [.readBanner(flowDisc)])
    }

    @Test func aRebuildWithNoBannerReadsItBeforeTheTools() {
        var run = launched(banner: nil)
        _ = run.send([.rebuildPressed, .spaceChecked(enoughSpace), .bookmarkResolved(.found(flowDisc))])
        #expect(run.send(.discChecked(path: flowDisc, check: .ok))
            == [.detectTools, .readBanner(flowDisc)])
    }

    @Test func withABannerCachedNothingIsRead() {
        var run = launched()
        #expect(run.send(playToStarting).last == starting(1))
    }

    @Test(arguments: [
        DiscCheck.wrongGame(foundID: "TSTE01"), .wrongRevision(foundSHA1: String(repeating: "4", count: 40)),
        .needsConversion(format: .rvz), .unreadable(reason: "cut short"),
    ])
    func aDiscThatFailsItsCheckHasNoBannerRead(_ check: DiscCheck) {
        var run = launched(banner: nil)
        _ = run.send([.playPressed, .bookmarkResolved(.found(flowDisc))])
        let effects = run.send(.discChecked(path: flowDisc, check: check))
        #expect(effects == [])
    }

    @Test func theBannerReadIsKeptAndNotReadAgain() {
        var run = launched(banner: nil)
        _ = run.send(playToStarting)
        let before = run.state
        #expect(run.send(.bannerRead(flowBanner)) == [])
        var expected = before
        expected.banner = flowBanner
        #expect(run.state == expected)

        run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        #expect(run.send(playToStarting).last == starting(2))
    }

    @Test func aBannerThatCouldntBeReadLeavesItToTheNextCheck() {
        var run = launched(banner: nil)
        _ = run.send(playToStarting)
        let before = run.state
        #expect(run.send(.bannerRead(nil)) == [])
        #expect(run.state == before)

        run.send(.gameExited(launch: 1, exit: .status(0), panic: nil))
        #expect(run.send(playToStarting).last
            == starting(2) + [.readBanner(flowDisc)])
    }

    @Test func noBannerReadReplacesTheCachedOneWithNothing() {
        var run = launched()
        #expect(run.send(.bannerRead(nil)) == [])
        #expect(run.state.banner == flowBanner)
    }

    @Test func aBannerReadBeforeTheLaunchOrOnAScreenThatOnlyQuitsIsIgnored() {
        var starting = FlowRun()
        #expect(starting.send(.bannerRead(flowBanner)) == [])
        #expect(starting.state.banner == nil)

        var moving = launched(appPath: "/private/var/folders/x/AppTranslocation/y/Dragoon.app",
                              banner: nil)
        #expect(moving.send(.bannerRead(flowBanner)) == [])
        #expect(moving.state.banner == nil)
    }
}
