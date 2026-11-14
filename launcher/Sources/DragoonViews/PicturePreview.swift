import DragoonCore
import SwiftUI

/// The Settings sheet's picture of what the game's aspect does, drawn in shapes: a horizon, the
/// lines of a track running to it and the race HUD's boxes. A wider aspect shows more of the
/// track to each side. Each HUD box keeps its 4:3 size and its 4:3 distance to the picture's
/// left or right edge, as the game anchors its HUD, and a dashed 4:3 frame in the middle is
/// where the menus stay. The frame has the shape of the window the game opens, or of the screen
/// when it's fullscreen.
public struct PicturePreview: View {
    /// The frame's height in points. Its width follows the window's or the screen's shape.
    public static let height: CGFloat = 120

    /// One of the race HUD's boxes, by the edge of the picture it keeps.
    public struct HUDBox: Equatable, Sendable {
        public enum Edge: Equatable, Sendable { case left, right }
        public var edge: Edge
        public var rect: CGRect
        /// The speed dial, drawn round.
        public var dial: Bool
    }

    /// The HUD's boxes in a 4:3 picture 12 units high and 16 across. `x` runs from the box's edge
    /// to its left side.
    nonisolated static let hudUnits: [(edge: HUDBox.Edge, x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat, dial: Bool)] = [
        (.left, 0.6, 0.6, 3.4, 1.3, false),
        (.right, -4.0, 0.6, 3.4, 1.3, false),
        (.left, 0.6, 10.1, 4.4, 1.3, false),
        (.right, -3.4, 8.6, 2.8, 2.8, true),
    ]

    /// Where the preview draws, in its own points.
    public struct Layout: Equatable, Sendable {
        /// What the frame stands for.
        public enum Shows: Equatable, Sendable {
            case window
            /// The screen a fullscreen game covers.
            case screen
            /// A fullscreen game's screen, whose size isn't known, so the frame is the window
            /// the game would open.
            case unknownScreen
        }
        public var shows: Shows
        /// The engine's size the frame stands for, in points: the game's window, or the screen.
        public var source: WholeSize
        /// Where the game's picture goes in `source`, in its points.
        public var fit: WholeRect
        public var frame: CGSize
        /// The game's picture in the frame, which bars surround on a screen of another shape.
        public var picture: CGRect
        /// The 4:3 frame in the middle of the picture that the menus, text and movie keep.
        public var menus: CGRect
        public var hud: [HUDBox]
    }

    nonisolated public static func layout(_ settings: PictureSettings, display: PictureDisplay?) -> Layout {
        let shows: Layout.Shows
        let source: WholeSize
        let fit: WholeRect
        if settings.fullscreen, let display {
            shows = .screen
            source = display.frame
            fit = PictureGeometry.fullscreen(aspect: settings.aspect, display: display.frame)
        } else {
            shows = settings.fullscreen ? .unknownScreen : .window
            source = PictureGeometry.window(aspect: settings.aspect, usable: display?.usable)
            fit = WholeRect(x: 0, y: 0, width: source.width, height: source.height)
        }
        let scale = height / CGFloat(source.height)
        let picture = CGRect(
            x: CGFloat(fit.x) * scale, y: CGFloat(fit.y) * scale, width: CGFloat(fit.width) * scale,
            height: CGFloat(fit.height) * scale)
        let menusWidth = min(picture.width, picture.height * 4 / 3)
        let menus = CGRect(
            x: picture.midX - menusWidth / 2, y: picture.minY, width: menusWidth, height: picture.height)
        let unit = picture.height / 12
        var hud: [HUDBox] = []
        for box in hudUnits {
            let edge = box.edge == .left ? picture.minX : picture.maxX
            let rect = CGRect(
                x: edge + box.x * unit, y: picture.minY + box.y * unit, width: box.width * unit,
                height: box.height * unit)
            hud.append(HUDBox(edge: box.edge, rect: rect, dial: box.dial))
        }
        return Layout(
            shows: shows, source: source, fit: fit,
            frame: CGSize(width: CGFloat(source.width) * scale, height: height), picture: picture, menus: menus,
            hud: hud)
    }

    let layout: Layout
    let colors: HeroColors
    @Environment(\.colorSchemeContrast) private var contrast

    init(_ settings: PictureSettings, display: PictureDisplay?, colors: HeroColors) {
        layout = Self.layout(settings, display: display)
        self.colors = colors
    }

    public var body: some View {
        let increased = contrast == .increased
        Canvas { context, _ in
            context.fill(Path(CGRect(origin: .zero, size: layout.frame)), with: .color(.black))
            context.clip(to: Path(layout.picture))
            drawWorld(in: context, picture: layout.picture)
            drawHUD(in: context, increased: increased)
        }
        .frame(width: layout.frame.width, height: layout.frame.height)
        .overlay(
            RoundedRectangle(cornerRadius: 3)
                .strokeBorder(.white.opacity(increased ? 0.9 : 0.45), lineWidth: increased ? 2 : 1))
        .accessibilityElement()
        .accessibilityLabel(Strings.previewLabel(layout.source))
    }

    /// The sky, the ground and the track's lines, all sized by the picture's height, so a wider
    /// picture shows more of them rather than bigger ones.
    private func drawWorld(in context: GraphicsContext, picture: CGRect) {
        let horizon = picture.minY + picture.height * 0.42
        let sky = CGRect(x: picture.minX, y: picture.minY, width: picture.width, height: horizon - picture.minY)
        context.fill(
            Path(sky),
            with: .linearGradient(
                Gradient(colors: [colors.sky, colors.streakPrimary.opacity(0.55)]),
                startPoint: CGPoint(x: 0, y: sky.minY), endPoint: CGPoint(x: 0, y: sky.maxY)))
        let ground = CGRect(x: picture.minX, y: horizon, width: picture.width, height: picture.maxY - horizon)
        context.fill(Path(ground), with: .color(colors.ground))
        let vanishing = CGPoint(x: picture.midX, y: horizon)
        let spread = picture.height * 0.5
        for lane in -9...9 {
            var line = Path()
            line.move(to: vanishing)
            line.addLine(to: CGPoint(x: picture.midX + CGFloat(lane) * spread, y: picture.maxY))
            let edge = abs(lane) == 1
            context.stroke(
                line, with: .color(edge ? .white.opacity(0.9) : colors.streakSecondary.opacity(0.45)),
                lineWidth: edge ? 2 : 1)
        }
        // The track's middle, dashed as it runs to the horizon.
        var middle = Path()
        middle.move(to: vanishing)
        middle.addLine(to: CGPoint(x: picture.midX, y: picture.maxY))
        context.stroke(
            middle, with: .color(.white.opacity(0.7)),
            style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
        var line = Path()
        line.move(to: CGPoint(x: picture.minX, y: horizon))
        line.addLine(to: CGPoint(x: picture.maxX, y: horizon))
        context.stroke(line, with: .color(colors.glow.opacity(0.8)), lineWidth: 1)
    }

    /// The HUD's boxes at the picture's edges, and the menus' 4:3 frame, dashed.
    private func drawHUD(in context: GraphicsContext, increased: Bool) {
        let unit = layout.picture.height / 12
        let ink = Color.white.opacity(increased ? 1 : 0.85)
        let panel = Color.black.opacity(0.55)
        for box in layout.hud {
            let shape = box.dial ? Path(ellipseIn: box.rect) : Path(roundedRect: box.rect, cornerRadius: unit * 0.3)
            context.fill(shape, with: .color(panel))
            context.stroke(shape, with: .color(ink), lineWidth: 1)
            guard box.dial else { continue }
            var needle = Path()
            needle.move(to: CGPoint(x: box.rect.midX, y: box.rect.midY))
            needle.addLine(to: CGPoint(x: box.rect.midX + unit * 0.9, y: box.rect.midY - unit * 0.7))
            context.stroke(needle, with: .color(colors.glow), lineWidth: 2)
        }
        context.stroke(
            Path(layout.menus.insetBy(dx: 0.5, dy: 0.5)), with: .color(colors.glow.opacity(increased ? 1 : 0.8)),
            style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
    }
}
