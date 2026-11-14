import DragoonCore
import Foundation
import Testing

@testable import DragoonViews

private let laptop = PictureDisplay(frame: WholeSize(1512, 982), usable: WholeSize(1512, 944))

/// The engine's sizes, which `tools/settings_fixtures.py` wrote from gcn-recomp's `aspect.h` to
/// DragoonCoreTests' `SettingsFixtures/`: each line an aspect and whole numbers.
private func engineTable(_ name: String) -> [(aspect: String, numbers: [Int])] {
    let file = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("DragoonCoreTests/SettingsFixtures/\(name)")
    let text = (try? String(contentsOf: file, encoding: .utf8)) ?? ""
    return text.split(separator: "\n").map { line in
        let words = line.split(separator: " ")
        return (String(words[0]), words.dropFirst().compactMap { Int($0) })
    }
}

/// Where the preview puts the picture, in the source's points.
private func pictureInSource(_ layout: PicturePreview.Layout) -> CGRect {
    let scale = PicturePreview.height / CGFloat(layout.source.height)
    let p = layout.picture
    return CGRect(x: p.minX / scale, y: p.minY / scale, width: p.width / scale, height: p.height / scale)
}

private func near(_ a: CGRect, _ b: CGRect) -> Bool {
    abs(a.minX - b.minX) < 1e-9 && abs(a.minY - b.minY) < 1e-9 && abs(a.width - b.width) < 1e-9
        && abs(a.height - b.height) < 1e-9
}

/// The preview's sizes for every aspect and scale, windowed and fullscreen. The window and the
/// fullscreen picture are checked against the engine's own numbers in `window-sizes.txt` and
/// `fits.txt`, not worked out again here.
struct SettingsPreviewTests {
    static let pictures: [PictureSettings] = PictureSettings.aspects.flatMap { aspect in
        (Array(1...PictureSettings.maxScale) + [12]).flatMap { scale in
            [false, true].map { PictureSettings(aspect: aspect, fullscreen: $0, scale: scale) }
        }
    }

    /// A display whose usable area is `usable`, under a 38 point menu bar, so the preview's
    /// window can't come from the whole frame unnoticed.
    static func display(usable: WholeSize) -> PictureDisplay {
        PictureDisplay(frame: WholeSize(usable.width, usable.height + 38), usable: usable)
    }

    /// The window `main.cpp` opens, for each aspect in each usable area, or none.
    @Test func theWindowIsTheOneInWindowSizes() {
        let rows = engineTable("window-sizes.txt")
        #expect(rows.count == 50)
        for (aspect, n) in rows {
            let usable = n[0] == 0 ? nil : WholeSize(n[0], n[1])
            let window = WholeSize(n[2], n[3])
            let layout = PicturePreview.layout(
                PictureSettings(aspect: aspect), display: usable.map { Self.display(usable: $0) })
            #expect(layout.shows == .window)
            #expect(layout.source == window, "\(aspect) in \(String(describing: usable))")
            #expect(layout.frame.height == PicturePreview.height)
            #expect(abs(layout.frame.width - PicturePreview.height * CGFloat(n[2]) / CGFloat(n[3])) < 1e-9)
            #expect(near(pictureInSource(layout), CGRect(x: 0, y: 0, width: n[2], height: n[3])), "\(aspect)")
        }
    }

    /// The screen a fullscreen game covers, and where its picture goes, for each aspect on each
    /// display.
    @Test func theFullscreenPictureIsTheOneInFits() {
        let rows = engineTable("fits.txt")
        #expect(rows.count == 40)
        for (aspect, n) in rows {
            let screen = WholeSize(n[0], n[1])
            let layout = PicturePreview.layout(
                PictureSettings(aspect: aspect, fullscreen: true),
                display: PictureDisplay(frame: screen, usable: WholeSize(n[0], n[1] - 38)))
            #expect(layout.shows == .screen)
            #expect(layout.source == screen, "\(aspect) on \(screen)")
            #expect(layout.fit == WholeRect(x: n[2], y: n[3], width: n[4], height: n[5]), "\(aspect) on \(screen)")
            #expect(near(pictureInSource(layout), CGRect(x: n[2], y: n[3], width: n[4], height: n[5])), "\(aspect)")
        }
    }

    /// Fullscreen on a display the sheet doesn't know is drawn as the window the game opens.
    @Test func aFullscreenGameOnAnUnknownDisplayIsDrawnAsItsWindow() {
        for (aspect, n) in engineTable("window-sizes.txt") where n[0] == 0 {
            let layout = PicturePreview.layout(PictureSettings(aspect: aspect, fullscreen: true), display: nil)
            #expect(layout.shows == .unknownScreen)
            #expect(layout.source == WholeSize(n[2], n[3]), "\(aspect)")
        }
    }

    @Test(arguments: [testDisplay, laptop, nil])
    func theMenusFrameIsFourByThreeInThePicturesMiddle(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let p = layout.picture
            #expect(abs(layout.menus.width - min(p.width, p.height * 4 / 3)) < 1e-9)
            #expect(layout.menus.height == p.height)
            #expect(abs(layout.menus.midX - p.midX) < 1e-9)
        }
    }

    /// Each HUD box is where it is in the 4:3 picture of the same height, moved with the place it
    /// keeps: the left one stays with the left edge, the middle one with the middle and the right
    /// ones with the right.
    @Test(arguments: [testDisplay, laptop, nil])
    func eachHUDBoxKeepsItsFourByThreeSizeAndDistanceToItsEdge(_ display: PictureDisplay?) {
        for picture in Self.pictures {
            let layout = PicturePreview.layout(picture, display: display)
            let p = layout.picture
            // The same picture at 4:3: as high, with its left edge where this one's is.
            let fourByThree = CGRect(x: p.minX, y: p.minY, width: p.height * 4 / 3, height: p.height)
            let reference = PicturePreview.layout(PictureSettings(aspect: "4:3"), display: nil)
            let k = p.height / reference.picture.height
            #expect(layout.hud.map(\.edge) == [.left, .middle, .right, .right, .right])
            for (box, at43) in zip(layout.hud, reference.hud) {
                #expect(abs(box.rect.width - at43.rect.width * k) < 1e-9, "\(picture)")
                #expect(abs(box.rect.height - at43.rect.height * k) < 1e-9, "\(picture)")
                #expect(abs(box.rect.minY - (p.minY + at43.rect.minY * k)) < 1e-9, "\(picture)")
                switch box.edge {
                case .left:
                    #expect(abs(box.rect.minX - (fourByThree.minX + at43.rect.minX * k)) < 1e-9, "\(picture)")
                case .middle:
                    let fromMiddle = at43.rect.minX - reference.picture.midX
                    #expect(abs((box.rect.minX - p.midX) - fromMiddle * k) < 1e-9, "\(picture)")
                case .right:
                    let fromRight = reference.picture.maxX - at43.rect.maxX
                    #expect(abs((p.maxX - box.rect.maxX) - fromRight * k) < 1e-9, "\(picture)")
                }
            }
        }
    }

    /// At 16:9 on the test display, the window is 213.375 points across in the preview against
    /// 160 at 4:3, so a right box sits 53.375 further right, the middle one half that and a left
    /// box doesn't move.
    @Test func sixteenByNinesMiddleAndRightBoxesMoveWithTheirPlace() {
        let wide = PicturePreview.layout(PictureSettings(aspect: "16:9"), display: testDisplay)
        let narrow = PicturePreview.layout(PictureSettings(aspect: "4:3"), display: testDisplay)
        #expect(narrow.frame.width == 160)
        let movedBy: [PicturePreview.HUDBox.Edge: CGFloat] = [.left: 0, .middle: 26.6875, .right: 53.375]
        for (box, at43) in zip(wide.hud, narrow.hud) {
            let moved = box.rect.minX - at43.rect.minX
            #expect(abs(moved - movedBy[box.edge]!) < 1e-9)
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
