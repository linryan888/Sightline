import SwiftUI

struct PillButton: View {
    let title: String
    var artwork = "SLPrimaryButtonLogin"
    let action: () -> Void

    @Environment(\.isEnabled) private var isEnabled
    @ScaledMetric(relativeTo: .body) private var minimumHeight: CGFloat = 53

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(Theme.handwriting())
                .foregroundStyle(Theme.text)
                .padding(.horizontal, 18)
                .padding(.bottom, 10)
                .frame(minWidth: 148, minHeight: minimumHeight)
                .background {
                    Image(artwork)
                        .resizable(capInsets: EdgeInsets(top: 20, leading: 27, bottom: 30, trailing: 27))
                        .accessibilityHidden(true)
                }
                .contentShape(Capsule())
                .opacity(isEnabled ? 1 : 0.55)
        }
        .buttonStyle(.plain)
    }
}
