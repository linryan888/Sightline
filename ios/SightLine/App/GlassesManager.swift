//
//  GlassesManager.swift
//  SightLine
//
//  All Meta glasses logic lives here: registration (connecting the app to
//  the glasses through the Meta AI app), camera permission, and live video.
//  Based on Meta's CameraAccess sample, trimmed down so any SightLine view
//  can use it without inheriting the sample's UI.
//
//  Usage from any view:
//    @Environment(GlassesManager.self) private var glasses
//    glasses.connect()                 // one-time pairing
//    await glasses.startStreaming()    // live video -> glasses.currentFrame
//    glasses.capturePhoto()            // photo -> glasses.lastPhoto
//    glasses.toggleRecording()         // video -> glasses.lastVideoURL
//    glasses.stopStreaming()
//

import MWDATCamera
import MWDATCore
import Observation
import SwiftUI
import UIKit
import os

/// Shows up in Xcode's console, filter by "Glasses".
private let log = Logger(subsystem: "SightLine", category: "Glasses")

@Observable
@MainActor
final class GlassesManager {

  // MARK: - State your UI can read

  /// Whether this app is registered with the glasses (via the Meta AI app).
  var registrationState: RegistrationState
  var isRegistered: Bool { registrationState == .registered }

  /// True when a pair of glasses is connected and available.
  var hasActiveDevice = false

  /// SDK session/stream states. Use these to drive spinners and labels.
  var sessionState: DeviceSessionState = .idle
  var streamState: StreamState = .stopped
  var isStreaming: Bool { streamState == .streaming }
  var isBusy: Bool {
    sessionState == .starting || sessionState == .stopping
      || streamState == .starting || streamState == .waitingForDevice || streamState == .stopping
  }

  /// Latest live frame from the glasses camera. Show it with Image(uiImage:).
  var currentFrame: UIImage?

  /// Most recent photo taken with capturePhoto().
  var lastPhoto: UIImage?

  /// Video recording state. `recordingStartDate` drives an on-screen timer.
  var isRecording = false
  var recordingStartDate: Date?
  /// Most recent finished recording (a .mov in the temp folder).
  var lastVideoURL: URL?

  /// Set when something fails. Show it in an alert, then set back to nil.
  var errorMessage: String?

  // MARK: - Private

  @ObservationIgnored private let wearables: WearablesInterface
  @ObservationIgnored private let deviceSelector: AutoDeviceSelector
  @ObservationIgnored private var session: DeviceSession?
  @ObservationIgnored private var camera: MWDATCamera.Camera?
  @ObservationIgnored private let sessionTokens = ListenerTokenBag()
  @ObservationIgnored private let streamTokens = ListenerTokenBag()
  @ObservationIgnored private var backgroundTasks: [Task<Void, Never>] = []
  @ObservationIgnored private let recorder = GlassesRecorder()
  /// Set when startStreaming() is called before the session has finished starting.
  @ObservationIgnored private var wantsStream = false
  /// True while the Meta AI app is open for the camera permission prompt.
  @ObservationIgnored private var isRequestingPermission = false

  // MARK: - Init

  /// Call `Wearables.configure()` before creating this (see SightLineApp).
  init(wearables: WearablesInterface = Wearables.shared) {
    self.wearables = wearables
    self.deviceSelector = AutoDeviceSelector(wearables: wearables)
    self.registrationState = wearables.registrationState

    backgroundTasks.append(Task { [weak self] in
      for await state in wearables.registrationStateStream() {
        self?.registrationState = state
      }
    })

    backgroundTasks.append(Task { [weak self] in
      guard let selector = self?.deviceSelector else { return }
      for await deviceId in selector.activeDeviceStream() {
        self?.hasActiveDevice = deviceId != nil
      }
    })

    // iOS pauses raw streams in the background, so end the session cleanly.
    // Only when a stream is actually running: registration and the camera
    // permission prompt also background the app (they open Meta AI), and
    // stopping then would kill the session we're about to stream on.
    backgroundTasks.append(Task { [weak self] in
      for await _ in NotificationCenter.default.notifications(
        named: UIApplication.didEnterBackgroundNotification)
      {
        guard let self, self.camera != nil, !self.isRequestingPermission else { continue }
        log.info("App backgrounded while streaming, stopping")
        self.stopStreaming()
      }
    })
  }

  // MARK: - Registration

  /// Opens the Meta AI app so the user can approve SightLine. Only needed once.
  func connect() {
    guard registrationState != .registering else { return }
    Task {
      do {
        try await wearables.startRegistration()
      } catch {
        errorMessage = error.localizedDescription
      }
    }
  }

  func disconnect() {
    Task {
      do {
        try await wearables.startUnregistration()
      } catch {
        errorMessage = error.localizedDescription
      }
    }
  }

  /// Pass URLs from .onOpenURL here. The Meta AI app calls back into SightLine
  /// after registration and permission prompts.
  func handleURL(_ url: URL) async {
    guard
      let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
      components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true
    else { return }
    do {
      _ = try await Wearables.shared.handleUrl(url)
    } catch {
      errorMessage = error.localizedDescription
    }
  }

  // MARK: - Streaming

  /// Starts live video. Creates the device session if needed, asks for camera
  /// permission (opens the Meta AI app the first time), then starts the stream.
  func startStreaming() async {
    guard isRegistered else {
      errorMessage = "Connect your glasses first."
      return
    }
    guard camera == nil else { return }
    wantsStream = true

    if let session, session.state == .started {
      await beginStreamWithPermission(on: session)
    } else if session == nil {
      startSession()
      // The session state listener calls beginStreamWithPermission once started.
    }
  }

  /// Stops the video and ends the session.
  func stopStreaming() {
    wantsStream = false
    camera?.stop()
    session?.stop()
  }

  /// Takes a photo while streaming. The result lands in `lastPhoto`.
  func capturePhoto() {
    guard isStreaming, let camera else {
      errorMessage = "Start streaming before taking a photo."
      return
    }
    if !camera.stream.capturePhoto(format: .jpeg) {
      errorMessage = "Couldn't capture photo. Try again in a moment."
    }
  }

  // MARK: - Recording

  func toggleRecording() {
    if isRecording {
      Task { await stopRecording() }
    } else {
      startRecording()
    }
  }

  /// Starts recording the live stream to a video file (video only, no audio).
  func startRecording() {
    guard isStreaming, !isRecording else {
      errorMessage = "Start streaming before recording."
      return
    }
    recorder.start()
    isRecording = true
    recordingStartDate = Date()
  }

  /// Finishes the file. The result lands in `lastVideoURL`.
  func stopRecording() async {
    guard isRecording else { return }
    isRecording = false
    recordingStartDate = nil
    switch await recorder.stop() {
    case .completed(let url):
      lastVideoURL = url
    case .noRecording:
      errorMessage = "No video was recorded. Try recording for a bit longer."
    case .failed:
      errorMessage = "Couldn't save the recording. Try again."
    }
  }

  /// Deletes a recording's temp file once you're done with it.
  func discardVideo() {
    if let url = lastVideoURL {
      try? FileManager.default.removeItem(at: url)
    }
    lastVideoURL = nil
  }

  // MARK: - Session internals

  private func startSession() {
    do {
      let newSession = try wearables.createSession(deviceSelector: deviceSelector)
      session = newSession
      // Subscribe before start() so no state change is missed.
      newSession.statePublisher.listen { [weak self] state in
        guard let self else { return }
        Task { @MainActor in self.handleSessionState(state) }
      }.store(in: sessionTokens)
      newSession.errorPublisher.listen { [weak self] error in
        guard let self else { return }
        Task { @MainActor in
          log.error("Session error: \(String(describing: error), privacy: .public)")
          self.errorMessage = error.localizedDescription
        }
      }.store(in: sessionTokens)
      sessionState = .starting
      try newSession.start()
    } catch {
      log.error("Couldn't create/start session: \(String(describing: error), privacy: .public)")
      errorMessage = error.localizedDescription
      cleanUpSession()
    }
  }

  private func handleSessionState(_ state: DeviceSessionState) {
    log.info("Session state: \(String(describing: state), privacy: .public)")
    sessionState = state
    switch state {
    case .started:
      if wantsStream, camera == nil, let session {
        Task { await beginStreamWithPermission(on: session) }
      }
    case .stopped:
      cleanUpStream()
      cleanUpSession()
    default:
      break
    }
  }

  private func cleanUpSession() {
    sessionTokens.clear()
    session = nil
    sessionState = .idle
    wantsStream = false
  }

  // MARK: - Stream internals

  private func beginStreamWithPermission(on session: DeviceSession) async {
    do {
      if try await wearables.checkPermissionStatus(.camera) != .granted {
        log.info("Requesting camera permission (opens Meta AI)")
        isRequestingPermission = true
        defer { isRequestingPermission = false }
        // Opens the Meta AI app; resumes when the user comes back.
        guard try await wearables.requestPermission(.camera) == .granted else {
          errorMessage = "Camera permission denied."
          return
        }
      }
    } catch {
      log.error("Permission error: \(String(describing: error), privacy: .public)")
      errorMessage = error.localizedDescription
      return
    }
    // The session can drop while we were away in Meta AI. If it did, start a
    // fresh one; the .started handler will come back here.
    guard let current = self.session, current.state == .started else {
      log.info("Session ended during permission prompt, restarting")
      if self.session == nil, wantsStream { startSession() }
      return
    }
    beginStream(on: current)
  }

  private func beginStream(on session: DeviceSession) {
    guard camera == nil else { return }
    // .raw gives decoded frames we can turn straight into UIImages.
    let config = StreamConfiguration(videoCodec: .raw, resolution: .medium, frameRate: 24)
    do {
      guard let newCamera = try session.addCamera(config: config) else {
        log.error("addCamera returned nil (session state: \(String(describing: session.state), privacy: .public))")
        errorMessage = "Couldn't start the glasses camera. Try again."
        return
      }
      camera = newCamera
      listen(to: newCamera.stream)
      streamState = .starting
      newCamera.stream.start()
    } catch {
      log.error("addCamera failed: \(String(describing: error), privacy: .public)")
      camera = nil
      errorMessage = error.localizedDescription
    }
  }

  private func listen(to stream: MWDATCamera.Stream) {
    stream.statePublisher.listen { [weak self] state in
      guard let self else { return }
      Task { @MainActor in
        log.info("Stream state: \(String(describing: state), privacy: .public)")
        self.streamState = state
        if state == .stopped { self.cleanUpStream() }
      }
    }.store(in: streamTokens)

    let recorder = self.recorder
    stream.videoFramePublisher.listen { [weak self] frame in
      guard let self else { return }
      // Write to the recorder (no-op unless recording), off the main thread.
      recorder.append(frame.sampleBuffer)
      // Convert off the main thread, then publish to the UI.
      guard let image = frame.makeUIImage() else { return }
      Task { @MainActor in
        // Hold the preview still while a photo/video sheet is open, so the
        // screen isn't redrawing 24x a second underneath it.
        guard self.lastPhoto == nil, self.lastVideoURL == nil else { return }
        self.currentFrame = image
      }
    }.store(in: streamTokens)

    stream.photoDataPublisher.listen { [weak self] photo in
      guard let self else { return }
      Task { @MainActor in self.lastPhoto = UIImage(data: photo.data) }
    }.store(in: streamTokens)

    stream.errorPublisher.listen { [weak self] error in
      guard let self else { return }
      Task { @MainActor in
        log.error("Stream error: \(String(describing: error), privacy: .public)")
        self.errorMessage = error.localizedDescription
      }
    }.store(in: streamTokens)
  }

  private func cleanUpStream() {
    // Stream ended (stopped, disconnected, backgrounded): save any recording.
    if isRecording {
      Task { await stopRecording() }
    }
    streamTokens.clear()
    camera?.stop()
    camera = nil
    streamState = .stopped
    currentFrame = nil
  }
}
