//
//  AppConfig.swift
//  SightLine
//
//  Reads settings from Secrets.xcconfig. They reach the app through
//  SightLine-Info.plist (e.g. API_BASE_URL = $(API_BASE_URL)), so at runtime
//  they're plain Info.plist values.
//

import Foundation

enum AppConfig {
    enum ConfigError: LocalizedError {
        case missing(String)
        case invalidURL(key: String, value: String)

        var errorDescription: String? {
            switch self {
            case .missing(let key):
                return "\(key) isn't set. Add it to SightLine/App/Secrets.xcconfig and rebuild."
            case .invalidURL(let key, let value):
                return "\(key) isn't a valid URL: \"\(value)\". In xcconfig files, write https:/$()/… instead of https://…"
            }
        }
    }

    /// Backend base URL, e.g. https://sightline-eyw3.onrender.com
    static var apiBaseURL: URL {
        get throws { try url("API_BASE_URL") }
    }

    static var supabaseURL: URL {
        get throws { try url("SUPABASE_URL") }
    }

    static var supabaseAnonKey: String {
        get throws { try string("SUPABASE_ANON_KEY") }
    }

    /// A non-empty Info.plist string, or a clear error naming the missing key.
    static func string(_ key: String) throws -> String {
        let value = (Bundle.main.object(forInfoDictionaryKey: key) as? String)?
            .trimmingCharacters(in: .whitespaces) ?? ""
        guard !value.isEmpty else { throw ConfigError.missing(key) }
        return value
    }

    static func url(_ key: String) throws -> URL {
        let value = try string(key)
        guard let url = URL(string: value), url.scheme != nil, url.host != nil else {
            throw ConfigError.invalidURL(key: key, value: value)
        }
        return url
    }
}
