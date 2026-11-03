import SwiftUI

@MainActor
struct ContentView: View {
    var body: some View {
        NavigationStack {
            LogInView()
        }
        // These Figma screens have a fixed light paper palette.
        .preferredColorScheme(.light)
    }
}

#Preview {
    ContentView()
}
