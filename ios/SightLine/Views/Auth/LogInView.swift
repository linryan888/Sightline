import SwiftUI

@MainActor
struct LogInView: View {
    @State private var model = AuthViewModel()
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case email
        case password
    }

    var body: some View {
        @Bindable var form = model

        AuthScreenLayout(variant: .logIn) {
            VStack(spacing: 24) {
                VStack(spacing: 30) {
                    LabeledField(label: "Email:", text: $form.email,
                                 contentType: .emailAddress, keyboardType: .emailAddress)
                        .focused($focusedField, equals: .email)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .password }

                    LabeledField(label: "Password:", text: $form.password,
                                 isSecure: true, contentType: .password)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { submit() }
                }

                PillButton(title: "Log In") { submit() }
                    .disabled(!model.canLogIn)
            }
            .padding(.horizontal, 12)
            .padding(.top, 43)
            .padding(.bottom, 14)
        } footer: {
            NavigationLink {
                SignUpView()
            } label: {
                Text("new account")
                    .underline()
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .accessibilityLabel("Create a new account")
        }
    }

    private func submit() {
        guard model.canLogIn else { return }
        focusedField = nil
        model.logIn()
    }
}
