import SwiftUI

struct LetterTileTitle: View {
    let text: String

    // The collage in Figma uses seven tiles behind nine separately styled letters.
    private let tiles: [(x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat, angle: Double)] = [
        (60.732, 61.5, 81.752, 86.112, -10),
        (112, 68, 80, 90, 0),
        (173, 45, 80, 90, 0),
        (216.414, 68.47, 70, 80, 10),
        (259, 52, 80, 80, 0),
        (341.999, 57.147, 81.159, 81.032, 10)
    ]

    private let fonts = [
        "IrishGrover-Regular", "Inika", "JacquesFrancoisShadow-Regular",
        "JejuHallasan", "Gugi-Regular", "JacquesFrancoisShadow-Regular",
        "JainiPurva-Regular", "Griffy-Regular", "GermaniaOne-Regular"
    ]
    private let letterX: [CGFloat] = [69.5, 100.5, 139.5, 177.5, 217.5, 242.5, 290.5, 307.5, 357.5]
    private let letterY: [CGFloat] = [54.5, 65.5, 42.5, 53.5, 68.5, 43.5, 55.5, 60.5, 51.5]

    var body: some View {
        GeometryReader { geometry in
            let scale = geometry.size.width / 402
            ZStack(alignment: .topLeading) {
                if text == "SightLine" {
                    collage
                } else {
                    alternativeTitle
                }
            }
            .frame(width: 402, height: 125, alignment: .topLeading)
            .scaleEffect(scale, anchor: .topLeading)
        }
        .aspectRatio(402.0 / 125, contentMode: .fit)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(text))
        .accessibilityAddTraits(.isHeader)
    }

    private var collage: some View {
        ZStack(alignment: .topLeading) {
            ForEach(tiles.indices, id: \.self) { index in
                Rectangle()
                    .fill(Theme.letterTile)
                    .frame(width: tiles[index].width, height: tiles[index].height)
                    .shadow(color: .black.opacity(0.25), radius: 2, x: 0, y: 4)
                    .rotationEffect(.degrees(tiles[index].angle))
                    .position(x: tiles[index].x, y: tiles[index].y)
            }
            // This one tile has an irregular outline in the source design.
            Image("SLTitleTile6")
                .resizable()
                .scaledToFit()
                .frame(width: 75.9128, height: 83.8324)
                .rotationEffect(.degrees(-10))
                .position(x: 303.719, y: 79.176)

            ForEach(Array("SIghtLiNE".enumerated()), id: \.offset) { index, character in
                Text(String(character))
                    .font(.custom(fonts[index], fixedSize: 60))
                    .foregroundStyle(Theme.text)
                    .fixedSize()
                    .position(x: letterX[index], y: letterY[index])
            }
        }
    }

    private var alternativeTitle: some View {
        HStack(spacing: -4) {
            ForEach(Array(text.enumerated()), id: \.offset) { index, character in
                Text(String(character))
                    .font(.custom(fonts[index % fonts.count], fixedSize: 44))
                    .foregroundStyle(Theme.text)
                    .padding(8)
                    .background(Theme.letterTile)
                    .rotationEffect(.degrees(index.isMultiple(of: 2) ? -6 : 6))
            }
        }
        .frame(width: 402, height: 125)
    }
}
