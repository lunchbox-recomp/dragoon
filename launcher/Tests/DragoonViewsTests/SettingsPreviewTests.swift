import DragoonCore
import Foundation
import Testing

@testable import DragoonViews

private let laptop = PictureDisplay(frame: WholeSize(1512, 982), usable: WholeSize(1512, 944))

/// The preview's sizes for every aspect and scale, windowed and fullscreen, on two displays and
/// on none. `PictureGeometryTests` checks `PictureGeometry` against the engine's own numbers,
/// and this checks the preview draws `PictureGeometry`'s.
struct SettingsPreviewTests {
    static let pictures: [PictureSettings] = PictureSettings.aspects.flatMap { aspect in
        (Array(1...PictureSettings.maxScale) + [12]).flatMap { scale in
            [false, true].map { PictureSettings(aspect: aspect, fullscreen: $0, scale: scale) }
        }
    }

    @Test(arguments: [testDisplay, laptop, nil])
    func theFrameHasTheShapeOfTheGamesWindowOrScreen(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let source: WholeSize
            if picture.fullscreen, let display {
                source = display.frame
            } else {
                source = PictureGeometry.window(aspect: picture.aspect, usable: display?.usable)
            }
            #expect(layout.source == source, "\(picture)")
            #expect(layout.frame.height == PicturePreview.height)
            let width = PicturePreview.height * CGFloat(source.width) / CGFloat(source.height)
            #expect(abs(layout.frame.width - width) < 1e-9, "\(picture)")
        }
    }

    @Test(arguments: [testDisplay, laptop, nil])
    func thePictureIsWhereTheGameDrawsIt(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let scale = PicturePreview.height / CGFloat(layout.source.height)
            var fit = WholeRect(x: 0, y: 0, width: layout.source.width, height: layout.source.height)
            if picture.fullscreen, let display {
                fit = PictureGeometry.fullscreen(aspect: picture.aspect, display: display.frame)
            }
            let expected = CGRect(
                x: CGFloat(fit.x) * scale, y: CGFloat(fit.y) * scale, width: CGFloat(fit.width) * scale,
                height: CGFloat(fit.height) * scale)
            #expect(layout.picture == expected, "\(picture)")
            // The menus' frame is 4:3, as tall as the picture and in its middle.
            #expect(abs(layout.menus.width - min(expected.width, expected.height * 4 / 3)) < 1e-9)
            #expect(layout.menus.height == expected.height)
            #expect(abs(layout.menus.midX - expected.midX) < 1e-9)
        }
    }

    /// Each HUD box is where it is in the 4:3 picture of the same height, moved with the edge it
    /// keeps: the left ones stay with the left edge and the right ones with the right.
    @Test(arguments: [testDisplay, laptop, nil])
    func eachHUDBoxKeepsItsFourByThreeSizeAndDistanceToItsEdge(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let p = layout.picture
            // The same picture at 4:3: as high, with its left edge where this one's is.
            let fourByThree = CGRect(x: p.minX, y: p.minY, width: p.height * 4 / 3, height: p.height)
            let reference = PicturePreview.layout(PictureSettings(aspect: "4:3"), display: nil)
            let k = p.height / reference.picture.height
            #expect(layout.hud.map(\.edge) == [.left, .right, .left, .right])
            for (box, at43) in zip(layout.hud, reference.hud) {
                #expect(abs(box.rect.width - at43.rect.width * k) < 1e-9, "\(picture)")
                #expect(abs(box.rect.height - at43.rect.height * k) < 1e-9, "\(picture)")
                #expect(abs(box.rect.minY - (p.minY + at43.rect.minY * k)) < 1e-9, "\(picture)")
                switch box.edge {
                case .left:
                    #expect(abs(box.rect.minX - (fourByThree.minX + at43.rect.minX * k)) < 1e-9, "\(picture)")
                case .right:
                    let fromRight = reference.picture.maxX - at43.rect.maxX
                    #expect(abs((p.maxX - box.rect.maxX) - fromRight * k) < 1e-9, "\(picture)")
                }
            }
        }
    }

    /// At 16:9 on the test display, the window is 213.375 points across in the preview against
    /// 160 at 4:3, so a right box sits 53.375 further right and a left box doesn't move.
    @Test func sixteenByNinesRightBoxesMoveWithTheRightEdge() {
        let wide = PicturePreview.layout(PictureSettings(aspect: "16:9"), display: testDisplay)
        let narrow = PicturePreview.layout(PictureSettings(aspect: "4:3"), display: testDisplay)
        #expect(narrow.frame.width == 160)
        for (box, at43) in zip(wide.hud, narrow.hud) {
            let moved = box.rect.minX - at43.rect.minX
            #expect(abs(moved - (box.edge == .left ? 0 : 53.375)) < 1e-9)
            #expect(box.rect.size == at43.rect.size)
        }
    }

    @Test func theScaleChangesNoSizeButTheInternalPictures() {
        for aspect in PictureSettings.aspects {
            let layouts = (1...PictureSettings.maxScale).map {
                PicturePreview.layout(PictureSettings(aspect: aspect, scale: $0), display: testDisplay)
            }
            #expect(Set(layouts.map(\.source)).count == 1)
        }
    }

    @Test func theScaleNoteNamesTheInternalPicture() {
        for picture in Self.pictures {
            let inside = PictureGeometry.internalSize(scale: picture.scale)
            #expect(Strings.scaleNote(picture.scale).contains("drawn at \(inside.width) x \(inside.height),"))
        }
    }

    /// The note under Fullscreen says what the preview draws: the window at its size, the screen
    /// with the picture in it, or a screen the sheet doesn't know the size of.
    @Test(arguments: [testDisplay, laptop, nil])
    func theWindowNoteSaysWhatThePreviewDraws(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let note = Strings.windowNote(layout)
            let source = layout.source, fit = layout.fit
            switch layout.shows {
            case .window:
                #expect(!picture.fullscreen)
                #expect(note == "The game's window opens at \(source.width) x \(source.height) points.")
            case .screen:
                #expect(picture.fullscreen && display != nil)
                #expect(note.contains("\(fit.width) x \(fit.height)"), "\(picture)")
            case .unknownScreen:
                #expect(picture.fullscreen && display == nil)
                #expect(note == "The game fills the screen.")
            }
        }
    }

    /// The window at 16:9 on the test display, worked by hand from `aspect.h`: 960 high fits
    /// under the 1050 point usable area less the 40 point title bar, so it's 1707 wide.
    @Test func sixteenByNineOnTheTestDisplayIs1707By960() {
        let layout = PicturePreview.layout(PictureSettings(aspect: "16:9"), display: testDisplay)
        #expect(layout.source == WholeSize(1707, 960))
        #expect(abs(layout.frame.width - 213.375) < 1e-9)
    }
}
