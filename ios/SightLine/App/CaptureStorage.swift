//
//  CaptureStorage.swift
//  SightLine
//
//  Saves glasses photos/videos into the app (Documents/Captures) and records
//  them as Items so they show up in the main list.
//

import Foundation
import SwiftData
import UIKit

enum CaptureKind: String {
    case photo
    case video
}

enum CaptureStorage {
    /// Documents/Captures, created on first use.
    nonisolated static var directory: URL {
        let dir = URL.documentsDirectory.appendingPathComponent("Captures", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    nonisolated static func url(for fileName: String) -> URL {
        directory.appendingPathComponent(fileName)
    }

    /// Writes the photo as a JPEG and adds it to the list.
    @discardableResult
    static func savePhoto(_ image: UIImage, in context: ModelContext) -> Item? {
        guard let data = image.jpegData(compressionQuality: 0.9) else { return nil }
        let name = "photo_\(UUID().uuidString).jpg"
        do {
            try data.write(to: url(for: name))
        } catch {
            print("Couldn't save photo: \(error)")
            return nil
        }
        return insert(kind: .photo, fileName: name, in: context)
    }

    /// Copies the recorded clip out of the temp folder and adds it to the list.
    @discardableResult
    static func saveVideo(from tempURL: URL, in context: ModelContext) -> Item? {
        let name = "video_\(UUID().uuidString).mov"
        do {
            try FileManager.default.copyItem(at: tempURL, to: url(for: name))
        } catch {
            print("Couldn't save video: \(error)")
            return nil
        }
        return insert(kind: .video, fileName: name, in: context)
    }

    /// Removes the media file behind an item (call before deleting the item).
    static func deleteFile(for item: Item) {
        guard let name = item.mediaFileName else { return }
        try? FileManager.default.removeItem(at: url(for: name))
    }

    private static func insert(kind: CaptureKind, fileName: String, in context: ModelContext) -> Item {
        let item = Item(timestamp: Date(), mediaKind: kind.rawValue, mediaFileName: fileName)
        context.insert(item)
        return item
    }
}

extension Item {
    var captureKind: CaptureKind? { mediaKind.flatMap(CaptureKind.init(rawValue:)) }

    var mediaURL: URL? { mediaFileName.map(CaptureStorage.url(for:)) }
}
