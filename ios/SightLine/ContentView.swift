//
//  ContentView.swift
//  SightLine
//
//  Created by Brian Tran on 10/9/26.
//

import SwiftUI
import SwiftData

struct ContentView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Item.timestamp, order: .reverse) private var items: [Item]
    @State private var showGlasses = false // Meta glasses screen

    var body: some View {
        NavigationSplitView {
            List {
                #if DEBUG
                Section("Debug") {
                    // Bundled clip from SightLine/Resources; tests the upload
                    // without needing glasses (SIG ticket: upload a video).
                    UploadButton(
                        title: "Upload test clip",
                        fileURL: Bundle.main.url(forResource: "test-clip", withExtension: "mp4"),
                        date: Date()
                    )
                }
                #endif

                ForEach(items) { item in
                    NavigationLink {
                        CaptureDetailView(item: item)
                    } label: {
                        CaptureRow(item: item)
                    }
                }
                .onDelete(perform: deleteItems)
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    EditButton()
                }
                ToolbarItem {
                    Button(action: addItem) {
                        Label("Add Item", systemImage: "plus")
                    }
                }
            }
        } detail: {
            Text("Select an item")
        }
        .sheet(isPresented: $showGlasses) {
            GlassesView()
        }
    }

    /// + opens the glasses screen; photos/videos taken there are saved to this list.
    private func addItem() {
        showGlasses = true
    }

    private func deleteItems(offsets: IndexSet) {
        withAnimation {
            for index in offsets {
                CaptureStorage.deleteFile(for: items[index])
                modelContext.delete(items[index])
            }
        }
    }
}

#Preview {
    ContentView()
        .modelContainer(for: Item.self, inMemory: true)
}
