import DragoonCore
import SwiftUI

/// The Settings sheet's picture of what the game's aspect does, drawn in shapes: a horizon, the
/// lines of a track running to it and the race HUD's boxes. A wider aspect shows more of the
/// track to each side, and the HUD stays in its 4:3 box in the middle. The frame has the shape
/// of the window the game opens, or of the screen when it's fullscreen.
public struct PicturePreview: View {
    /// The frame's height in points. Its width follows the window's or the screen's shape.
    public static let height: CGFloat = 120

    /// Where the preview draws, in its own points.
    public struct Layout: Equatable, Sendable {
        /// The engine's size the frame stands for, in points: the game's window, or the screen.
        public var source: WholeSize
        public var frame: CGSize
        /// The game's picture in the frame, which bars surround on a screen of another shape.
        public var picture: CGRect
        /// The race HUD's 4:3 box in the picture.
        public var hud: CGRect
    }

    public static func layout(_ settings: PictureSettings, display: PictureDisplay?) -> Layout {
        let source: WholeSize
        let fit: WholeRect
        if settings.fullscreen, let display {
            source = display.frame
            fit = PictureGeometry.fullscreen(aspect: settings.aspect, display: display.frame)
        } else {
            source = PictureGeometry.window(aspect: settings.aspect, usable: display?.usable)
            fit = WholeRect(x: 0, y: 0, width: source.width, height: source.height)
        }
        let scale = height / CGFloat(source.height)
        let picture = CGRect(
            x: CGFloat(fit.x) * scale, y: CGFloat(fit.y) * scale, width: CGFloat(fit.width) * scale,
            height: CGFloat(fit.height) * scale)
        let hudWidth = min(picture.width, picture.height * 4 / 3)
        let hud = CGRect(
            x: picture.midX - hudWidth / 2, y: picture.minY, width: hudWidth, height: picture.height)
        return Layout(
            source: source, frame: CGSize(width: CGFloat(source.width) * scale, height: height),
            picture: picture, hud: hud)
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
            drawHUD(in: context, box: layout.hud, increased: increased)
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

    /// The HUD's boxes at the corners of its 4:3 box, and the box's edge, dashed.
    private func drawHUD(in context: GraphicsContext, box: CGRect, increased: Bool) {
        let unit = box.height / 12
        let ink = Color.white.opacity(increased ? 1 : 0.85)
        let panel = Color.black.opacity(0.55)
        let boxes = [
            CGRect(x: box.minX + unit * 0.6, y: box.minY + unit * 0.6, width: unit * 3.4, height: unit * 1.3),
            CGRect(x: box.maxX - unit * 4.0, y: box.minY + unit * 0.6, width: unit * 3.4, height: unit * 1.3),
            CGRect(x: box.minX + unit * 0.6, y: box.maxY - unit * 1.9, width: unit * 4.4, height: unit * 1.3),
        ]
        for rect in boxes {
            let shape = Path(roundedRect: rect, cornerRadius: unit * 0.3)
            context.fill(shape, with: .color(panel))
            context.stroke(shape, with: .color(ink), lineWidth: 1)
        }
        // A speed dial at the bottom right.
        let dial = CGRect(x: box.maxX - unit * 3.4, y: box.maxY - unit * 3.4, width: unit * 2.8, height: unit * 2.8)
        context.fill(Path(ellipseIn: dial), with: .color(panel))
        context.stroke(Path(ellipseIn: dial), with: .color(ink), lineWidth: 1)
        var needle = Path()
        needle.move(to: CGPoint(x: dial.midX, y: dial.midY))
        needle.addLine(to: CGPoint(x: dial.midX + unit * 0.9, y: dial.midY - unit * 0.7))
        context.stroke(needle, with: .color(colors.glow), lineWidth: 2)
        context.stroke(
            Path(box.insetBy(dx: 0.5, dy: 0.5)), with: .color(colors.glow.opacity(increased ? 1 : 0.8)),
            style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
    }
}
