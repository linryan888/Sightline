import SwiftUI

@MainActor
struct SignUpView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model = AuthViewModel()
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case email
        case password
        case confirmPassword
    }

    var body: some View {
        @Bindable var form = model

        AuthScreenLayout(variant: .signUp) {
            VStack(spacing: 0) {
                LabeledField(label: "Email:", text: $form.email,
                             contentType: .emailAddress, keyboardType: .emailAddress)
                    .focused($focusedField, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .password }

                LabeledField(label: "Password:", text: $form.password,
                             isSecure: true, contentType: .newPassword)
                    .focused($focusedField, equals: .password)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .confirmPassword }
                    .padding(.top, 30)

                LabeledField(label: "Confirm Password:", text: $form.confirmPassword,
                             isSecure: true, contentType: .newPassword)
                    .focused($focusedField, equals: .confirmPassword)
                    .submitLabel(.go)
                    .onSubmit { submit() }
                    .padding(.top, 21)

                if let message = model.errorMessage {
                    Text(message)
                        .font(.callout)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 8)
                        .padding(.top, 8)
                        .accessibilityLabel(Text(message))
                }

                PillButton(title: "Sign Up", artwork: "SLPrimaryButtonSignup") { submit() }
                    .disabled(!model.canSignUp)
                    .padding(.top, 22)
            }
            .padding(.horizontal, 12)
            .padding(.top, 43)
            .padding(.bottom, 5)
        } footer: {
            Button {
                focusedField = nil
                dismiss()
            } label: {
                Text("Sign In")
                    .underline()
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .accessibilityLabel("Return to Log In")
        }
        .onChange(of: model.password) { _, _ in model.validatePasswords() }
        .onChange(of: model.confirmPassword) { _, _ in model.validatePasswords() }
    }

    private func submit() {
        guard model.canSignUp else { return }
        focusedField = nil
        model.signUp()
    }
}
