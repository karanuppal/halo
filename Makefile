.PHONY: backend.test backend.acceptance backend.run ios.generate ios.build ios.test

backend.test:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

backend.acceptance:
	uv run pytest services/api/tests/test_mvp_acceptance.py

backend.run:
	uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload

ios.generate:
	cd apps/ios && xcodegen generate

IOS_DEST ?= platform=iOS Simulator,name=iPhone 16 Pro,OS=18.4

ios.build: ios.generate
	xcodebuild -project apps/ios/Halo.xcodeproj -scheme HaloApp -destination '$(IOS_DEST)' build


ios.test: ios.generate
	xcodebuild -project apps/ios/Halo.xcodeproj -scheme HaloApp -destination '$(IOS_DEST)' test
