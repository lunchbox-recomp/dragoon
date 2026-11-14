import DragoonCore
import SwiftUI

/// Library's colors, from the banner's two hues. Brightness and saturation are fixed here, so
/// any banner gives a dark backdrop and a Play button whose text can be read.
struct HeroColors {
    static let buttonSaturation = 0.85
    static let buttonLight = 0.86
    static let buttonDark = 0.70
    static let buttonHeight = 64.0
    /// The rows of the button Play's label covers, from the top of its "l" to the bottom of its
    /// "y", in points from the button's top, as the library snapshot draws them.
    static let labelRows: ClosedRange<Double> = 21...45
    /// The near-black ink's gray, sRGB, for the light buttons.
    static let darkInk = 0.08
    /// The bar Play's text meets on every hue: 3:1, WCAG's floor for large text, which Play's
    /// 24 pt bold label is. 4.5:1, the floor for body text, can't be met on every hue: on the
    /// worst, both inks come to 4.0:1.
    static let minimumContrast = 3.0

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
    /// White or near-black, whichever has more contrast with the button.
    var buttonInk: Color {
        Self.whiteReads(onHue: palette.primary) ? .white : Color(white: Self.darkInk)
    }

    static func whiteReads(onHue hue: Double) -> Bool {
        let ink = inkContrasts(onHue: hue)
        return ink.white >= ink.dark
    }

    /// Each ink's contrast with the button where it's worst behind the label: white's at the
    /// label's top row, where the button is lightest, and near-black's at its bottom row, where
    /// the button is darkest.
    static func inkContrasts(onHue hue: Double) -> (white: Double, dark: Double) {
        func luminance(atRow row: Double) -> Double {
            let brightness = buttonLight - (buttonLight - buttonDark) * row / buttonHeight
            return Self.luminance(hue: hue, saturation: buttonSaturation, brightness: brightness)
        }
        return (
            contrast(1, luminance(atRow: labelRows.lowerBound)),
            contrast(linear(darkInk), luminance(atRow: labelRows.upperBound))
        )
    }

    /// WCAG's contrast ratio of two relative luminances.
    static func contrast(_ one: Double, _ other: Double) -> Double {
        (max(one, other) + 0.05) / (min(one, other) + 0.05)
    }

    /// WCAG relative luminance of an sRGB color given as hue, saturation and brightness.
    static func luminance(hue: Double, saturation: Double, brightness: Double) -> Double {
        let (red, green, blue) = rgb(hue: hue, saturation: saturation, brightness: brightness)
        return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    }

    /// An sRGB channel's linear light.
    static func linear(_ channel: Double) -> Double {
        channel <= 0.04045 ? channel / 12.92 : pow((channel + 0.055) / 1.055, 2.4)
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
