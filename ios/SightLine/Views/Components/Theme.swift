import SwiftUI

enum Theme {
    // Exact text and tile colors from the two Figma auth frames.
    static let text = Color(red: 69.0 / 255, green: 45.0 / 255, blue: 45.0 / 255)
    static let letterTile = Color(red: 238.0 / 255, green: 225.0 / 255, blue: 208.0 / 255)
    static let card = Color.white
    static let cardCornerRadius: CGFloat = 10

    static func handwriting(size: CGFloat = 30) -> Font {
        .custom("HiMelody-Regular", size: size, relativeTo: .body)
    }
}
