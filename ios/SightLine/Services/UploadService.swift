//
//  UploadService.swift
//  SightLine
//
//  Sends a recorded video to the backend's POST /chunks/upload, which puts
//  the file in the Supabase `footage` bucket and adds a row to `chunks`.
//
//  It's the same request as this curl (see backend/README.md):
//
//    curl -X POST "$API_BASE_URL/chunks/upload" \
//      -H "Authorization: Bearer $TOKEN" \
//      -F "file=@clip.mp4;type=video/mp4" \
//      -F "date=2026-11-17"
//
//  or in Python:
//
//    requests.post(f"{base}/chunks/upload",
//                  headers={"Authorization": f"Bearer {token}"},
//                  files={"file": ("clip.mp4", f, "video/mp4")},
//                  data={"date": "2026-11-17"})
//
//  The backend takes the user from the token (SIG-58), so there is no
//  user_id field anymore.
//

import Foundation
import UniformTypeIdentifiers

struct UploadService {
    let api: APIClient
    /// Returns a Supabase access token for the signed-in user.
    let accessToken: () async throws -> String

    /// Uploads one video. `date` is the day the footage belongs to (sent as
    /// YYYY-MM-DD in the phone's time zone). Returns the new `chunks` row if
    /// the response could be read.
    @discardableResult
    func uploadChunk(fileURL: URL, date: Date) async throws -> UploadedChunk? {
        let token = try await accessToken()
        let fileData = try Data(contentsOf: fileURL, options: .mappedIfSafe)

        // multipart/form-data: each field is a "part" separated by a boundary
        // string that can't appear in the content.
        let boundary = "SightLine-\(UUID().uuidString)"
        let form = MultipartForm(boundary: boundary)
            .field(name: "date", value: Self.dayString(date))
            .file(name: "file", fileName: fileURL.lastPathComponent,
                  mimeType: Self.mimeType(for: fileURL), data: fileData)

        var request = URLRequest(url: api.url(for: "chunks/upload"))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        // The deployed backend can take ~a minute to wake up after idling.
        request.timeoutInterval = 120

        let responseData = try await api.upload(request, body: form.finish())
        return try? JSONDecoder().decode(UploadResponse.self, from: responseData).chunk.first
    }

    /// "2026-11-17" for the given moment, in the phone's time zone.
    /// (Plain .iso8601 would use UTC and give tomorrow's date in the evening.)
    static func dayString(_ date: Date) -> String {
        date.formatted(Date.ISO8601FormatStyle(timeZone: .current).year().month().day())
    }

    /// video/mp4 for .mp4, video/quicktime for .mov (what the glasses recorder saves).
    static func mimeType(for fileURL: URL) -> String {
        UTType(filenameExtension: fileURL.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
    }
}

/// The part of the backend's response we use:
/// {"message": "...", "chunk": [{"id": "...", "storage_path": "...", "status": "split", ...}]}
struct UploadResponse: Decodable {
    let chunk: [UploadedChunk]
}

struct UploadedChunk: Decodable {
    let id: String
    let storagePath: String
    let status: String?

    enum CodingKeys: String, CodingKey {
        case id
        case storagePath = "storage_path"
        case status
    }
}

/// Builds a multipart/form-data body, one part at a time.
struct MultipartForm {
    let boundary: String
    private var body = Data()

    init(boundary: String) {
        self.boundary = boundary
    }

    /// A plain text field, like `-F "date=2026-11-17"`.
    func field(name: String, value: String) -> MultipartForm {
        var copy = self
        copy.append("--\(boundary)\r\n")
        copy.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        copy.append("\(value)\r\n")
        return copy
    }

    /// A file field, like `-F "file=@clip.mp4;type=video/mp4"`.
    func file(name: String, fileName: String, mimeType: String, data: Data) -> MultipartForm {
        var copy = self
        copy.append("--\(boundary)\r\n")
        copy.append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(fileName)\"\r\n")
        copy.append("Content-Type: \(mimeType)\r\n\r\n")
        copy.body.append(data)
        copy.append("\r\n")
        return copy
    }

    /// The finished body, with the closing boundary.
    func finish() -> Data {
        var copy = self
        copy.append("--\(boundary)--\r\n")
        return copy.body
    }

    private mutating func append(_ text: String) {
        body.append(Data(text.utf8))
    }
}
