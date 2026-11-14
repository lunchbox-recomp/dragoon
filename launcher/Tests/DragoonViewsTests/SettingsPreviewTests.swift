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
            // The HUD's box is 4:3, as tall as the picture and in its middle.
            #expect(abs(layout.hud.width - min(expected.width, expected.height * 4 / 3)) < 1e-9)
            #expect(layout.hud.height == expected.height)
            #expect(abs(layout.hud.midX - expected.midX) < 1e-9)
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

    @Test func theNotesNameTheEnginesSizes() {
        for picture in Self.pictures {
            let inside = PictureGeometry.internalSize(scale: picture.scale)
            #expect(Strings.scaleNote(picture.scale).contains("\(inside.width) x \(inside.height) inside"))
            let window = PictureGeometry.window(aspect: picture.aspect, usable: testDisplay.usable)
            let note = Strings.windowNote(picture, display: testDisplay)
            if picture.fullscreen {
                let fit = PictureGeometry.fullscreen(aspect: picture.aspect, display: testDisplay.frame)
                #expect(note.contains("\(fit.width) x \(fit.height)"), "\(picture)")
            } else {
                #expect(note.contains("\(window.width) x \(window.height) points"), "\(picture)")
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
