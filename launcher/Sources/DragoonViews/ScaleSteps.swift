import DragoonCore
import SwiftUI

/// How the picture's detail grows with the scale: an edge drawn in square pixels, one size of
/// pixel for each scale, so 1x shows the coarsest steps and 8x the finest.
struct ScaleSteps: View {
    static let size = CGSize(width: 72, height: 36)
    /// The pixel's side at 1x, in points.
    static let coarsest: CGFloat = 12

    let scale: Int
    let colors: HeroColors

    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.45)))
            let side = Self.coarsest / CGFloat(min(max(scale, 1), PictureSettings.maxScale))
            let columns = Int((size.width / side).rounded(.up))
            // The edge rises from the bottom left to the top right, and each column fills to the
            // last whole pixel under it. One path, so the columns meet with no seam.
            var steps = Path()
            for column in 0..<columns {
                let x = CGFloat(column) * side
                let edge = size.height * (1 - (x + side / 2) / size.width)
                let top = (edge / side).rounded(.down) * side
                steps.addRect(CGRect(x: x, y: top, width: side, height: size.height - top))
            }
            context.fill(steps, with: .color(colors.streakPrimary))
        }
        .frame(width: Self.size.width, height: Self.size.height)
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .accessibilityHidden(true)
    }
}
