//
//  Item.swift
//  SightLine
//
//  Created by Brian Tran on 10/9/26.
//

import Foundation
import SwiftData

@Model
final class Item {
    var timestamp: Date
    /// Glasses capture: "photo" or "video" (nil for plain items).
    var mediaKind: String?
    /// File name inside Documents/Captures (see App/CaptureStorage.swift).
    var mediaFileName: String?

    init(timestamp: Date, mediaKind: String? = nil, mediaFileName: String? = nil) {
        self.timestamp = timestamp
        self.mediaKind = mediaKind
        self.mediaFileName = mediaFileName
    }
}
