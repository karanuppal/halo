import SwiftUI

struct RootView: View {
    var body: some View {
        TabView {
            ActivityView()
                .tabItem { Label("Activity", systemImage: "list.bullet") }

            SetupView()
                .tabItem { Label("Setup", systemImage: "gearshape") }
        }
    }
}
