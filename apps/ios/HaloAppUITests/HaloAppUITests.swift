import XCTest

final class HaloAppUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testLaunchShowsActivityTab() throws {
        let app = XCUIApplication()
        app.launch()

        let activityTab = app.tabBars.buttons["Activity"]
        XCTAssertTrue(activityTab.waitForExistence(timeout: 5))
    }
}
