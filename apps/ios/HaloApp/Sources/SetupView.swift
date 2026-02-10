import SwiftUI

struct SetupView: View {
    @AppStorage("halo_base_url") private var baseURL: String = "http://127.0.0.1:8000"
    @AppStorage("halo_household_id") private var householdId: String = "hh-1"
    @AppStorage("halo_user_id") private var userId: String = "u-1"

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("Base URL", text: $baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    TextField("Household ID", text: $householdId)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                    TextField("User ID", text: $userId)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                }

                Section("Notes") {
                    Text("For simulator, http://127.0.0.1:8000 usually reaches your Mac host.")
                        .font(.footnote)
                    Text("For a physical phone, you’ll need a reachable backend (Cloud Run) or your Mac’s LAN IP.")
                        .font(.footnote)
                }
            }
            .navigationTitle("Setup")
        }
    }
}
