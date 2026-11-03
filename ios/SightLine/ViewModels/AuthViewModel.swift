import Foundation
import Observation

@MainActor
@Observable
final class AuthViewModel {
    var email = ""
    var password = ""
    var confirmPassword = ""
    var errorMessage: String?

    var canLogIn: Bool {
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !password.isEmpty
    }

    var canSignUp: Bool {
        canLogIn && !confirmPassword.isEmpty && password == confirmPassword
    }

    func validatePasswords() {
        if !confirmPassword.isEmpty && password != confirmPassword {
            errorMessage = "Passwords don't match"
        } else {
            errorMessage = nil
        }
    }

    func logIn() {
        guard canLogIn else { return }
        print("SightLine UI only: Log In tapped")
    }

    func signUp() {
        validatePasswords()
        guard canSignUp else { return }
        print("SightLine UI only: Sign Up tapped")
    }
}
