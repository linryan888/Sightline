//
//  CaptureViews.swift
//  SightLine
//
//  List row + detail screen for saved glasses photos/videos.
//

import AVKit
import SwiftUI

/// Row for the main list: thumbnail, type, and time.
struct CaptureRow: View {
    let item: Item
    @State private var thumbnail: UIImage?

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8).fill(Color.black)
                if let thumbnail {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .scaledToFill()
                } else if item.captureKind == .video {
                    Image(systemName: "video.fill").foregroundStyle(.white)
                } else if item.captureKind == .photo {
                    Image(systemName: "photo").foregroundStyle(.white)
                }
            }
            .frame(width: 48, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body)
                Text(item.timestamp, format: Date.FormatStyle(date: .numeric, time: .shortened))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .task(id: item.mediaFileName) { await loadThumbnail() }
    }

    private var title: String {
        switch item.captureKind {
        case .photo: return "Photo"
        case .video: return "Video"
        case nil: return "Item"
        }
    }

    private func loadThumbnail() async {
        guard let url = item.mediaURL else { return }
        switch item.captureKind {
        case .photo:
            thumbnail = await UIImage(contentsOfFile: url.path)?
                .byPreparingThumbnail(ofSize: CGSize(width: 96, height: 96))
        case .video:
            let generator = AVAssetImageGenerator(asset: AVURLAsset(url: url))
            generator.appliesPreferredTrackTransform = true
            generator.maximumSize = CGSize(width: 96, height: 96)
            if let result = try? await generator.image(at: .zero) {
                thumbnail = UIImage(cgImage: result.image)
            }
        case nil:
            break
        }
    }
}

/// Full-screen view of a saved capture.
struct CaptureDetailView: View {
    let item: Item

    var body: some View {
        VStack(spacing: 16) {
            if let url = item.mediaURL {
                switch item.captureKind {
                case .photo:
                    if let image = UIImage(contentsOfFile: url.path) {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                    } else {
                        missingFile
                    }
                case .video:
                    CaptureVideoPlayer(url: url)
                case nil:
                    missingFile
                }
                ShareLink(item: url) {
                    Label("Share or Save", systemImage: "square.and.arrow.up")
                }
            } else {
                Text("Item at \(item.timestamp, format: Date.FormatStyle(date: .numeric, time: .standard))")
            }
        }
        .padding()
        .navigationTitle(item.captureKind == .video ? "Video" : "Photo")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var missingFile: some View {
        ContentUnavailableView("File not found", systemImage: "exclamationmark.triangle")
    }
}

/// Video player created once (not on every redraw).
struct CaptureVideoPlayer: View {
    @State private var player: AVPlayer

    init(url: URL) {
        _player = State(initialValue: AVPlayer(url: url))
    }

    var body: some View {
        VideoPlayer(player: player)
            .aspectRatio(9.0 / 16.0, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .onAppear { player.play() }
            .onDisappear { player.pause() }
    }
}
