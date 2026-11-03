import SwiftUI
import UIKit

struct LabeledField: View {
    let label: String
    @Binding var text: String
    var isSecure = false
    var contentType: UITextContentType? = nil
    var keyboardType: UIKeyboardType = .default

    @ScaledMetric(relativeTo: .body) private var minimumHeight: CGFloat = 53

    var body: some View {
        Group {
            if isSecure {
                SecureField(label, text: $text, prompt: prompt)
            } else {
                TextField(label, text: $text, prompt: prompt)
            }
        }
        .font(Theme.handwriting())
        .foregroundStyle(Theme.text)
        .textContentType(contentType)
        .keyboardType(keyboardType)
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .padding(.horizontal, 20)
        .frame(maxWidth: .infinity, minHeight: minimumHeight)
        .background {
            Image("SLFieldWell")
                .resizable(capInsets: EdgeInsets(top: 26, leading: 26, bottom: 26, trailing: 26))
                .accessibilityHidden(true)
        }
        .accessibilityLabel(Text(label))
    }

    private var prompt: Text {
        Text(label).foregroundColor(Theme.text)
    }
}
