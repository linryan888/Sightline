//
//  UploadButton.swift
//  SightLine
//
//  DEBUG ONLY. A button that uploads one video to the backend and shows
//  "Uploaded" or the error underneath, so failures are never silent.
//  Used for the bundled test clip (ContentView) and for saved glasses
//  recordings (CaptureDetailView).
//

#if DEBUG
import SwiftUI

struct UploadButton: View {
    let title: String
    /// nil shows an error when tapped (e.g. the test clip isn't in the bundle).
    let fileURL: URL?
    /// The day the footage belongs to.
    let date: Date

    private enum Status {
        case idle
        case uploading
        case uploaded(String)
        case failed(String)
    }

    @State private var status: Status = .idle

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                Task { await upload() }
            } label: {
                if case .uploading = status {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Uploading…")
                    }
                } else {
                    Label(title, systemImage: "icloud.and.arrow.up")
                }
            }
            .disabled(isUploading)

            switch status {
            case .idle, .uploading:
                EmptyView()
            case .uploaded(let message):
                Label(message, systemImage: "checkmark.circle.fill")
                    .font(.footnote)
                    .foregroundStyle(.green)
            case .failed(let message):
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }
        }
    }

    private var isUploading: Bool {
        if case .uploading = status { return true }
        return false
    }

    private func upload() async {
        guard let fileURL else {
            status = .failed("No video file to upload. For the test clip, add test-clip.mp4 to SightLine/Resources.")
            return
        }
        status = .uploading
        do {
            let chunk = try await UploadService.debug().uploadChunk(fileURL: fileURL, date: date)
            if let chunk {
                status = .uploaded("Uploaded. Chunk \(chunk.id), status: \(chunk.status ?? "unknown")")
            } else {
                status = .uploaded("Uploaded")
            }
        } catch {
            status = .failed(error.localizedDescription)
        }
    }
}
#endif
