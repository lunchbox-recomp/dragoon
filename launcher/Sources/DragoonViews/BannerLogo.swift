import DragoonCore
import SwiftUI

/// The disc's banner at a whole-number `scale` with its pixels kept square, over a soft bloom
/// of itself.
struct BannerLogo: View {
    let banner: DiscBanner
    let scale: CGFloat

    var body: some View {
        if let image = banner.cgImage() {
            let picture = Image(decorative: image, scale: 1)
            ZStack {
                picture.resizable().interpolation(.high).blur(radius: 18).opacity(0.55)
                picture.resizable().interpolation(.none)
            }
            .frame(
                width: CGFloat(DiscBanner.width) * scale, height: CGFloat(DiscBanner.height) * scale)
            .accessibilityElement()
            .accessibilityLabel(banner.texts.first?.longName ?? Strings.libraryTitle)
        }
    }
}

/// "Dragoon" drawn in type, for Library with no banner to show.
struct Wordmark: View {
    let colors: HeroColors

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(Strings.appName)
                .font(.system(size: 92, weight: .black, design: .rounded).italic())
                .foregroundStyle(
                    LinearGradient(
                        colors: [.white, colors.glow], startPoint: .top, endPoint: .bottom))
                .shadow(color: colors.glow.opacity(0.6), radius: 18)
            Text(Strings.libraryTitle.uppercased())
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .tracking(5)
                .foregroundStyle(.white.opacity(0.75))
                .padding(.leading, 6)
        }
        .frame(height: CGFloat(DiscBanner.height) * 4, alignment: .bottomLeading)
    }
}
