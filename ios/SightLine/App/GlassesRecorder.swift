//
//  GlassesRecorder.swift
//  SightLine
//
//  Writes live glasses frames to an H.264 .mov in the temp folder.
//  Video only (no audio). GlassesManager feeds it every frame; it only
//  writes while a recording is active.
//

import AVFoundation
import CoreMedia
import CoreVideo
import os

enum GlassesRecordingResult {
  case completed(URL)
  case noRecording
  case failed
}

/// Thread-safe: frames arrive on the SDK's thread, start/stop come from the UI.
nonisolated final class GlassesRecorder: @unchecked Sendable {
  private let lock = NSLock()
  private let log = Logger(subsystem: "SightLine", category: "Glasses")

  private var wantsRecording = false
  private var writer: AVAssetWriter?
  private var input: AVAssetWriterInput?
  private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
  private var outputURL: URL?
  private var startDate: Date?
  private var lastTime: CMTime = .invalid

  /// Arms the recorder. The file is created on the next frame.
  func start() {
    lock.lock(); defer { lock.unlock() }
    wantsRecording = true
  }

  /// Call for every frame. Does nothing unless a recording is active.
  func append(_ sampleBuffer: CMSampleBuffer) {
    lock.lock(); defer { lock.unlock() }
    guard wantsRecording, let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

    if writer == nil {
      startWriter(width: CVPixelBufferGetWidth(pixelBuffer), height: CVPixelBufferGetHeight(pixelBuffer))
    }
    guard let writer, let input, let adaptor, let startDate,
      writer.status == .writing, input.isReadyForMoreMediaData
    else { return }

    // Wall-clock timing keeps the clip in real time even if frames arrive unevenly.
    let time = CMTime(seconds: Date().timeIntervalSince(startDate), preferredTimescale: 600)
    if lastTime.isValid, time <= lastTime { return }
    if adaptor.append(pixelBuffer, withPresentationTime: time) {
      lastTime = time
    } else {
      log.error("Recorder append failed: \(String(describing: writer.error), privacy: .public)")
    }
  }

  /// Finishes the file and returns where it is.
  func stop() async -> GlassesRecordingResult {
    let (writer, input, url, wroteFrames) = lock.withLock {
      () -> (AVAssetWriter?, AVAssetWriterInput?, URL?, Bool) in
      wantsRecording = false
      let taken = (self.writer, self.input, self.outputURL, lastTime.isValid)
      self.writer = nil
      self.input = nil
      self.adaptor = nil
      self.outputURL = nil
      self.startDate = nil
      self.lastTime = .invalid
      return taken
    }

    guard let writer, let input, let url else { return .noRecording }
    guard wroteFrames else {
      writer.cancelWriting()
      try? FileManager.default.removeItem(at: url)
      return .noRecording
    }

    input.markAsFinished()
    await writer.finishWriting()
    if writer.status == .completed {
      log.info("Recording saved: \(url.lastPathComponent, privacy: .public)")
      return .completed(url)
    }
    log.error("Recording failed: \(String(describing: writer.error), privacy: .public)")
    return .failed
  }

  // Called with the lock held.
  private func startWriter(width: Int, height: Int) {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("glasses_\(Int(Date().timeIntervalSince1970)).mov")
    do {
      let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
      let input = AVAssetWriterInput(
        mediaType: .video,
        outputSettings: [
          AVVideoCodecKey: AVVideoCodecType.h264,
          AVVideoWidthKey: width,
          AVVideoHeightKey: height,
        ]
      )
      input.expectsMediaDataInRealTime = true
      let adaptor = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: input, sourcePixelBufferAttributes: nil)
      guard writer.canAdd(input) else {
        log.error("Recorder can't add video input")
        wantsRecording = false
        return
      }
      writer.add(input)
      guard writer.startWriting() else {
        log.error("Recorder failed to start: \(String(describing: writer.error), privacy: .public)")
        wantsRecording = false
        return
      }
      writer.startSession(atSourceTime: .zero)

      self.writer = writer
      self.input = input
      self.adaptor = adaptor
      self.outputURL = url
      self.startDate = Date()
      self.lastTime = .invalid
      log.info("Recording started (\(width)x\(height))")
    } catch {
      log.error("Recorder couldn't create file: \(error.localizedDescription, privacy: .public)")
      wantsRecording = false
    }
  }
}
