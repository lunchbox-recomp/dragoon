import DragoonCore
import Foundation
import Testing

/// The sizes the engine gives, which the harness that wrote `SettingsFixtures/` printed from
/// gcn-recomp's `runtime/gx/aspect.h`, `settings.h` and `gx::kMaxInternalScale`.
enum EngineSizes {
    static let directory = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().appendingPathComponent("SettingsFixtures")

    /// Each line's words, the first a string and the rest whole numbers.
    static func table(_ name: String) -> [(String, [Int])] {
        let text = (try? String(contentsOf: directory.appendingPathComponent(name), encoding: .utf8)) ?? ""
        return text.split(separator: "\n").map { line in
            let words = line.split(separator: " ").map(String.init)
            return (words[0], words.dropFirst().compactMap { Int($0) })
        }
    }

    /// The window `main.cpp` opens: aspect, the display's usable area (0 by 0 for none), and the
    /// window's size.
    static let windows: [(aspect: String, usable: WholeSize?, window: WholeSize)] = table("window-sizes.txt").map {
        let usable = $0.1[0] == 0 ? nil : WholeSize($0.1[0], $0.1[1])
        return ($0.0, usable, WholeSize($0.1[2], $0.1[3]))
    }

    /// The picture on a fullscreen display: aspect, the display, and where the picture goes.
    static let fits: [(aspect: String, display: WholeSize, picture: WholeRect)] = table("fits.txt").map {
        ($0.0, WholeSize($0.1[0], $0.1[1]),
         WholeRect(x: $0.1[2], y: $0.1[3], width: $0.1[4], height: $0.1[5]))
    }

    /// The picture the renderer draws at each scale, 1 to 10.
    static let scales: [(scale: Int, size: WholeSize)] = table("scales.txt").compactMap { row in
        guard let scale = Int(row.0) else { return nil }
        return (scale, WholeSize(row.1[0], row.1[1]))
    }

    static func window(_ aspect: String, usable: WholeSize?) -> WholeSize? {
        windows.first { $0.aspect == aspect && $0.usable == usable }?.window
    }

    static func fit(_ aspect: String, display: WholeSize) -> WholeRect? {
        fits.first { $0.aspect == aspect && $0.display == display }?.picture
    }
}

@Suite struct PictureGeometryTests {
    @Test func theTablesHoldEveryAspectAndScale() {
        #expect(EngineSizes.windows.count == 50)
        #expect(EngineSizes.fits.count == 40)
        #expect(EngineSizes.scales.map(\.scale) == Array(1...10))
        #expect(Set(EngineSizes.windows.map(\.aspect)) == Set(PictureSettings.aspects))
        #expect(Set(EngineSizes.fits.map(\.aspect)) == Set(PictureSettings.aspects))
    }

    @Test func theWindowIsTheOneTheEngineOpens() {
        for (aspect, usable, window) in EngineSizes.windows {
            #expect(
                PictureGeometry.window(aspect: aspect, usable: usable) == window,
                "\(aspect) in \(String(describing: usable))")
        }
    }

    @Test func theFullscreenPictureIsWhereTheEngineFitsIt() {
        for (aspect, display, picture) in EngineSizes.fits {
            #expect(
                PictureGeometry.fullscreen(aspect: aspect, display: display) == picture,
                "\(aspect) on \(display)")
        }
    }

    @Test func theInternalPictureIsTheEnginesAtEveryScale() {
        for (scale, size) in EngineSizes.scales {
            #expect(PictureGeometry.internalSize(scale: scale) == size, "at \(scale)")
        }
    }

    /// The numbers `aspect.h`'s own comments give.
    @Test func aspectHsExamplesHold() {
        let height = PictureGeometry.openingHeight
        #expect(PictureGeometry.width(height: height, shape: WholeSize(4, 3)) == 1280)
        #expect(PictureGeometry.width(height: height, shape: WholeSize(16, 9)) == 1707)
        #expect(PictureGeometry.width(height: 412, shape: WholeSize(9, 21)) == 177)
        #expect(
            PictureGeometry.fit(WholeSize(1920, 1080), ratio: 4.0 / 3)
                == WholeRect(x: 240, y: 0, width: 1440, height: 1080))
    }
}
