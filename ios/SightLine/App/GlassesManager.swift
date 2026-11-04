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
//    glasses.stopStreaming()
//

import MWDATCamera
import MWDATCore
import Observation
import SwiftUI
import UIKit

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
  /// Set when startStreaming() is called before the session has finished starting.
  @ObservationIgnored private var wantsStream = false

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
    backgroundTasks.append(Task { [weak self] in
      for await _ in NotificationCenter.default.notifications(
        named: UIApplication.didEnterBackgroundNotification)
      {
        self?.stopStreaming()
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
      _ = try await wearables.handleUrl(url)
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

  // MARK: - Session internals

  private func startSession() {
    do {
      let newSession = try wearables.createSession(deviceSelector: deviceSelector)
      session = newSession
      // Subscribe before start() so no state change is missed.
      newSession.statePublisher.listen { [weak self] state in
        Task { @MainActor in self?.handleSessionState(state) }
      }.store(in: sessionTokens)
      newSession.errorPublisher.listen { [weak self] error in
        Task { @MainActor in self?.errorMessage = error.localizedDescription }
      }.store(in: sessionTokens)
      sessionState = .starting
      try newSession.start()
    } catch {
      errorMessage = error.localizedDescription
      cleanUpSession()
    }
  }

  private func handleSessionState(_ state: DeviceSessionState) {
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
        // Opens the Meta AI app; resumes when the user comes back.
        guard try await wearables.requestPermission(.camera) == .granted else {
          errorMessage = "Camera permission denied."
          return
        }
      }
    } catch {
      errorMessage = error.localizedDescription
      return
    }
    beginStream(on: session)
  }

  private func beginStream(on session: DeviceSession) {
    guard camera == nil else { return }
    // .raw gives decoded frames we can turn straight into UIImages.
    let config = StreamConfiguration(videoCodec: .raw, resolution: .medium, frameRate: 24)
    do {
      guard let newCamera = try session.addCamera(config: config) else {
        errorMessage = "Couldn't start the glasses camera. Try again."
        return
      }
      camera = newCamera
      listen(to: newCamera.stream)
      streamState = .starting
      newCamera.stream.start()
    } catch {
      camera = nil
      errorMessage = error.localizedDescription
    }
  }

  private func listen(to stream: MWDATCamera.Stream) {
    stream.statePublisher.listen { [weak self] state in
      Task { @MainActor in
        self?.streamState = state
        if state == .stopped { self?.cleanUpStream() }
      }
    }.store(in: streamTokens)

    stream.videoFramePublisher.listen { [weak self] frame in
      // Convert off the main thread, then publish to the UI.
      guard let image = frame.makeUIImage() else { return }
      Task { @MainActor in self?.currentFrame = image }
    }.store(in: streamTokens)

    stream.photoDataPublisher.listen { [weak self] photo in
      Task { @MainActor in self?.lastPhoto = UIImage(data: photo.data) }
    }.store(in: streamTokens)

    stream.errorPublisher.listen { [weak self] error in
      Task { @MainActor in self?.errorMessage = error.localizedDescription }
    }.store(in: streamTokens)
  }

  private func cleanUpStream() {
    streamTokens.clear()
    camera?.stop()
    camera = nil
    streamState = .stopped
    currentFrame = nil
  }
}
