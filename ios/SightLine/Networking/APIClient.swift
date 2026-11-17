//
//  APIClient.swift
//  SightLine
//
//  Small wrapper around URLSession for talking to our backend (FastAPI in
//  /backend). Knows the base URL and turns non-2xx responses into errors.
//

import Foundation

struct APIClient {
    let baseURL: URL
    var session: URLSession = .shared

    /// Uses API_BASE_URL from Secrets.xcconfig.
    static func live() throws -> APIClient {
        APIClient(baseURL: try AppConfig.apiBaseURL)
    }

    /// e.g. url(for: "chunks/upload") -> https://<backend>/chunks/upload
    func url(for path: String) -> URL {
        baseURL.appending(path: path)
    }

    /// Sends `body` with `request` and returns the response body.
    /// Throws APIError.badStatus for any status outside 200–299.
    func upload(_ request: URLRequest, body: Data) async throws -> Data {
        let (data, response) = try await session.upload(for: request, from: body)
        try APIError.check(response, data: data)
        return data
    }
}

enum APIError: LocalizedError {
    case badStatus(code: Int, message: String)
    case notHTTP

    var errorDescription: String? {
        switch self {
        case .badStatus(let code, let message):
            return "Server returned \(code): \(message)"
        case .notHTTP:
            return "The server's response wasn't HTTP."
        }
    }

    /// Throws unless `response` is an HTTP 2xx.
    static func check(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.notHTTP }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.badStatus(code: http.statusCode, message: message(from: data))
        }
    }

    /// Pulls a readable message out of an error body.
    /// FastAPI sends {"detail": "..."} (or a list of problems for a 422).
    /// Supabase Auth sends "msg" or "error_description".
    private static func message(from data: Data) -> String {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = json["detail"] as? String { return detail }
            if let problems = json["detail"] as? [[String: Any]] {
                return problems.compactMap { $0["msg"] as? String }.joined(separator: "; ")
            }
            for key in ["msg", "error_description", "message", "error"] {
                if let text = json[key] as? String { return text }
            }
        }
        let text = String(decoding: data.prefix(300), as: UTF8.self)
        return text.isEmpty ? "No details from the server." : text
    }
}
