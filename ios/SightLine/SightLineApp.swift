//
//  SightLineApp.swift
//  SightLine
//
//  Created by Brian Tran on 10/9/26.
//

import SwiftUI
import SwiftData
import MWDATCore

@main
struct SightLineApp: App {
    // Meta glasses: SDK setup + shared manager (see App/GlassesManager.swift)
    @State private var glasses: GlassesManager

    init() {
        do {
            try Wearables.configure()
        } catch {
            print("Failed to configure Meta Wearables SDK: \(error)")
        }
        _glasses = State(wrappedValue: GlassesManager())
    }

    var sharedModelContainer: ModelContainer = {
        let schema = Schema([
            Item.self,
        ])
        let modelConfiguration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: false)

        do {
            return try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            fatalError("Could not create ModelContainer: \(error)")
        }
    }()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(glasses)
                // Meta AI app calls back here after pairing / permission prompts
                .onOpenURL { url in
                    Task { await glasses.handleURL(url) }
                }
        }
        .modelContainer(sharedModelContainer)
    }
}
