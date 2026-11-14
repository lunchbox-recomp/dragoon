import DragoonCore
import SwiftUI

/// Library's colors, from the banner's two hues. Brightness and saturation are fixed here, so
/// any banner gives a dark backdrop and a Play button whose text can be read.
struct HeroColors {
    static let buttonSaturation = 0.85
    static let buttonLight = 0.86
    static let buttonDark = 0.70
    /// WCAG's floor for body text.
    static let minimumContrast = 4.5

    let palette: BannerPalette

    /// The top of the backdrop.
    var sky: Color { Color(hue: palette.primary, saturation: 0.8, brightness: 0.32) }
    /// The bottom of the backdrop, under the Play bar.
    var ground: Color { Color(hue: palette.primary, saturation: 0.5, brightness: 0.06) }
    var glow: Color { Color(hue: palette.secondary, saturation: 0.7, brightness: 1) }
    var streakPrimary: Color { Color(hue: palette.primary, saturation: 0.45, brightness: 1) }
    var streakSecondary: Color { Color(hue: palette.secondary, saturation: 0.55, brightness: 1) }

    var buttonTop: Color {
        Color(hue: palette.primary, saturation: Self.buttonSaturation, brightness: Self.buttonLight)
    }
    var buttonBottom: Color {
        Color(hue: palette.primary, saturation: Self.buttonSaturation, brightness: Self.buttonDark)
    }
    /// White on the button when it reads against the lighter end, and near-black otherwise.
    var buttonInk: Color {
        Self.whiteReads(onHue: palette.primary) ? .white : Color(white: 0.08)
    }

    static func whiteReads(onHue hue: Double) -> Bool {
        let fill = luminance(hue: hue, saturation: buttonSaturation, brightness: buttonLight)
        return 1.05 / (fill + 0.05) >= minimumContrast
    }

    /// WCAG relative luminance of an sRGB color given as hue, saturation and brightness.
    static func luminance(hue: Double, saturation: Double, brightness: Double) -> Double {
        let (red, green, blue) = rgb(hue: hue, saturation: saturation, brightness: brightness)
        func linear(_ channel: Double) -> Double {
            channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    }

    static func rgb(hue: Double, saturation: Double, brightness: Double)
        -> (Double, Double, Double)
    {
        let sixths = (hue - hue.rounded(.down)) * 6
        let sector = Int(sixths) % 6
        let within = sixths - Double(Int(sixths))
        let low = brightness * (1 - saturation)
        let falling = brightness * (1 - within * saturation)
        let rising = brightness * (1 - (1 - within) * saturation)
        switch sector {
        case 0: return (brightness, rising, low)
        case 1: return (falling, brightness, low)
        case 2: return (low, brightness, rising)
        case 3: return (low, falling, brightness)
        case 4: return (rising, low, brightness)
        default: return (brightness, low, falling)
        }
    }
}
