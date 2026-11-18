//
//  GlassesView.swift
//  SightLine
//
//  Minimal screen for the Meta glasses: connect, live video, photo, record.
//  All logic lives in GlassesManager; restyle this view however you like.
//

import AVKit
import MWDATCore
import SwiftData
import SwiftUI

struct GlassesView: View {
    @Environment(GlassesManager.self) private var glasses
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                if glasses.isRegistered {
                    preview
                    status
                    controls
                } else {
                    connectPrompt
                }
            }
            .padding()
            .navigationTitle("Glasses")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                if glasses.isRegistered {
                    ToolbarItem(placement: .primaryAction) {
                        Button("Disconnect", role: .destructive) { glasses.disconnect() }
                    }
                }
            }
            // Save every capture into the app's list (the + screen).
            .onChange(of: glasses.lastPhoto) { _, photo in
                if let photo { CaptureStorage.savePhoto(photo, in: modelContext) }
            }
            .onChange(of: glasses.lastVideoURL) { _, url in
                if let url { CaptureStorage.saveVideo(from: url, in: modelContext) }
            }
            // Attached here, not on the live preview: the preview redraws every
            // frame, which would rebuild the player and make it flash.
            .sheet(isPresented: Binding(
                get: { glasses.lastVideoURL != nil },
                set: { if !$0 { glasses.discardVideo() } }
            )) {
                if let url = glasses.lastVideoURL {
                    RecordedVideoView(url: url)
                }
            }
            .alert(
                "Something went wrong",
                isPresented: Binding(
                    get: { glasses.errorMessage != nil },
                    set: { if !$0 { glasses.errorMessage = nil } }
                )
            ) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(glasses.errorMessage ?? "")
            }
        }
    }

    // MARK: - Pieces

    private var connectPrompt: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "eyeglasses")
                .font(.system(size: 56))
            Text("Connect your Meta glasses")
                .font(.title3.bold())
            Text("You'll be sent to the Meta AI app to approve SightLine, then brought back here.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Connect") { glasses.connect() }
                .buttonStyle(.borderedProminent)
                .disabled(glasses.registrationState == .registering)
            Spacer()
        }
    }

    private var preview: some View {
        ZStack(alignment: .topLeading) {
            ZStack {
                RoundedRectangle(cornerRadius: 16)
                    .fill(.black)
                if let frame = glasses.currentFrame {
                    Image(uiImage: frame)
                        .resizable()
                        .scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                } else if glasses.isBusy {
                    ProgressView().tint(.white)
                } else {
                    Text(glasses.hasActiveDevice ? "Tap Start to stream" : "Put on your glasses")
                        .foregroundStyle(.white.opacity(0.7))
                }
            }

            if let start = glasses.recordingStartDate {
                recordingBadge(since: start)
                    .padding(12)
            }
        }
        .aspectRatio(9.0 / 16.0, contentMode: .fit)
        .frame(maxHeight: .infinity)
    }

    /// Red dot + mm:ss while recording.
    private func recordingBadge(since start: Date) -> some View {
        TimelineView(.periodic(from: start, by: 1)) { context in
            let seconds = max(0, Int(context.date.timeIntervalSince(start)))
            HStack(spacing: 6) {
                Circle().fill(Color.red).frame(width: 8, height: 8)
                Text(String(format: "%02d:%02d", seconds / 60, seconds % 60))
                    .font(.footnote.monospacedDigit().bold())
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(.black.opacity(0.6), in: Capsule())
        }
    }

    private var status: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(glasses.hasActiveDevice ? Color.green : Color.gray)
                .frame(width: 8, height: 8)
            Text(glasses.hasActiveDevice ? "Glasses connected" : "No glasses detected")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
    }

    private var controls: some View {
        HStack(spacing: 12) {
            Button {
                if glasses.isStreaming {
                    glasses.stopStreaming()
                } else {
                    Task { await glasses.startStreaming() }
                }
            } label: {
                Label(glasses.isStreaming ? "Stop" : "Start",
                      systemImage: glasses.isStreaming ? "stop.fill" : "play.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(glasses.isBusy)

            Button {
                glasses.toggleRecording()
            } label: {
                Label(glasses.isRecording ? "End" : "Record",
                      systemImage: glasses.isRecording ? "stop.circle.fill" : "record.circle")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .tint(.red)
            .disabled(!glasses.isStreaming && !glasses.isRecording)

            Button {
                glasses.capturePhoto()
            } label: {
                Label("Photo", systemImage: "camera.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(!glasses.isStreaming)
        }
        .labelStyle(.titleAndIcon)
        .sheet(isPresented: Binding(
            get: { glasses.lastPhoto != nil },
            set: { if !$0 { glasses.lastPhoto = nil } }
        )) {
            if let image = glasses.lastPhoto {
                photoSheet(image)
            }
        }
    }

    private func photoSheet(_ image: UIImage) -> some View {
        VStack(spacing: 16) {
            Image(uiImage: image)
                .resizable()
                .scaledToFit()
            Label("Saved to SightLine", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
            ShareLink(item: Image(uiImage: image),
                      preview: SharePreview("Glasses photo", image: Image(uiImage: image)))
        }
        .padding()
    }

}

/// Plays a finished recording; Share includes "Save Video" to Photos.
/// The player lives in @State so it's created once, not on every redraw.
private struct RecordedVideoView: View {
    let url: URL
    @State private var player: AVPlayer

    init(url: URL) {
        self.url = url
        _player = State(initialValue: AVPlayer(url: url))
    }

    var body: some View {
        VStack(spacing: 16) {
            VideoPlayer(player: player)
                .aspectRatio(9.0 / 16.0, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 16))
            Label("Saved to SightLine", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
            ShareLink(item: url) {
                Label("Share or Save", systemImage: "square.and.arrow.up")
            }
        }
        .padding()
        .onAppear { player.play() }
        .onDisappear { player.pause() }
    }
}
