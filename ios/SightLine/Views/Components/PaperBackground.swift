import SwiftUI

/// Only decorative artwork uses Figma coordinates. The forms use normal layout.
struct PaperBackground: View {
    enum Variant: Equatable {
        case logIn
        case signUp
    }

    var variant: Variant = .logIn

    var body: some View {
        Canvas { context, size in
            let scale = size.width / 402
            let height = size.height / scale
            let bottomShift = height - 874
            context.scaleBy(x: scale, y: scale)

            // Figma repeats its original paper texture in an oversized layer.
            let rows = max(2, Int(ceil((height + 1059) / 1078.5)))
            for row in 0..<rows {
                for column in 0..<2 {
                    draw("SLPaperTexture", x: -599 + CGFloat(column) * 834,
                         y: -1059 + CGFloat(row) * 1078.5,
                         width: 834, height: 1078.5, in: &context)
                }
            }

            rotated("SLTornPaper", center: CGPoint(x: 480.438, y: -193.487),
                    width: 670.369, height: 292.937, angle: -60,
                    opacity: 0.4, in: &context)

            if variant == .logIn {
                rotated("SLLargeStarLogin", center: CGPoint(x: 120.79, y: 94.148),
                        width: 329.016, height: 326.044, angle: 15, in: &context)
                rotated("SLTornPaper", center: CGPoint(x: 341.083, y: 789.046 + bottomShift),
                        width: 1222, height: 534, angle: -8,
                        opacity: 0.4, in: &context)
                rotated("SLPinkNoteLogin", center: CGPoint(x: 98.441, y: 852.444 + bottomShift),
                        width: 188, height: 156, angle: 10, in: &context)
                rotated("SLBlueNoteLogin", center: CGPoint(x: 344.177, y: 844.992 + bottomShift),
                        width: 204.819, height: 198.828, angle: -10, in: &context)
                rotated("SLYellowNoteLogin", center: CGPoint(x: 243.709, y: 928.546 + bottomShift),
                        width: 235.803, height: 181.644, angle: -4, in: &context)
                draw("SLPushPin", x: 314, y: -20, width: 109, height: 109, in: &context)
                mirroredPin(x: -9, y: 681 + bottomShift, in: &context)
            } else {
                rotated("SLLargeStarSignup", center: CGPoint(x: 120.79, y: 94.148),
                        width: 329.016, height: 326.044, angle: 15, in: &context)
                rotated("SLPinkNoteSignup", center: CGPoint(x: 324.441, y: 796.444 + bottomShift),
                        width: 188, height: 156, angle: 10, in: &context)
                rotated("SLBlueNoteSignup", center: CGPoint(x: 109.177, y: 818.992 + bottomShift),
                        width: 204.819, height: 198.828, angle: -10, in: &context)
                rotated("SLYellowNoteSignup", center: CGPoint(x: 235.959, y: 878.546 + bottomShift),
                        width: 235.803, height: 181.644, angle: -4, in: &context)
                rotated("SLPushPin", center: CGPoint(x: 379.128, y: 179.128),
                        width: 109, height: 109, angle: -17.12, in: &context)
                mirroredPin(x: -18, y: 652 + bottomShift, in: &context)
            }

        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func draw(_ name: String, x: CGFloat, y: CGFloat,
                      width: CGFloat, height: CGFloat, in context: inout GraphicsContext) {
        context.draw(Image(name), in: CGRect(x: x, y: y, width: width, height: height))
    }

    private func rotated(_ name: String, center: CGPoint, width: CGFloat,
                         height: CGFloat, angle: Double, opacity: Double = 1,
                         in context: inout GraphicsContext) {
        var layer = context
        layer.opacity = opacity
        layer.translateBy(x: center.x, y: center.y)
        layer.rotate(by: .degrees(angle))
        layer.draw(Image(name), in: CGRect(x: -width / 2, y: -height / 2,
                                          width: width, height: height))
    }

    private func mirroredPin(x: CGFloat, y: CGFloat, in context: inout GraphicsContext) {
        var layer = context
        layer.translateBy(x: x + 109, y: y)
        layer.scaleBy(x: -1, y: 1)
        draw("SLPushPin", x: 0, y: 0, width: 109, height: 109, in: &layer)
    }
}
