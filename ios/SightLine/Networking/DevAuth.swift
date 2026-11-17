//
//  DevAuth.swift
//  SightLine
//
//  DEBUG ONLY. The chunk endpoints need a Supabase access token (SIG-58),
//  but the app has no login screen yet (SIG-32). Until it does, the debug
//  upload buttons sign in as the test user from Secrets.xcconfig.
//
//  This is Supabase's email/password sign-in, the same as:
//
//    curl -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
//      -H "apikey: $SUPABASE_ANON_KEY" -H "Content-Type: application/json" \
//      -d '{"email": "...", "password": "..."}'
//
//  Delete this file once real sign-in lands, and pass the session's
//  access token to UploadService instead.
//

#if DEBUG
import Foundation

enum DevAuth {
    /// Signs in as TEST_USER_EMAIL / TEST_USER_PASSWORD and returns the access token.
    static func accessToken() async throws -> String {
        var components = URLComponents(
            url: try AppConfig.supabaseURL.appending(path: "auth/v1/token"),
            resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "grant_type", value: "password")]

        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.setValue(try AppConfig.supabaseAnonKey, forHTTPHeaderField: "apikey")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "email": try AppConfig.string("TEST_USER_EMAIL"),
            "password": try AppConfig.string("TEST_USER_PASSWORD"),
        ])

        let (data, response) = try await URLSession.shared.data(for: request)
        do {
            try APIError.check(response, data: data)
        } catch {
            throw DevAuthError.signInFailed(error.localizedDescription)
        }
        return try JSONDecoder().decode(TokenResponse.self, from: data).accessToken
    }

    private struct TokenResponse: Decodable {
        let accessToken: String

        enum CodingKeys: String, CodingKey {
            case accessToken = "access_token"
        }
    }
}

enum DevAuthError: LocalizedError {
    case signInFailed(String)

    var errorDescription: String? {
        switch self {
        case .signInFailed(let reason):
            return "Test user sign-in failed. \(reason)"
        }
    }
}

extension UploadService {
    /// Upload service for the debug buttons: our backend + the test user's token.
    static func debug() throws -> UploadService {
        UploadService(api: try APIClient.live(), accessToken: DevAuth.accessToken)
    }
}
#endif
