.PHONY: backend.test backend.run ios.generate ios.build

backend.test:
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

backend.run:
	uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload

ios.generate:
	cd apps/ios && xcodegen generate

IOS_DEST ?= platform=iOS Simulator,name=iPhone 16 Pro

ios.build: ios.generate
	xcodebuild -project apps/ios/Halo.xcodeproj -scheme HaloApp -destination '$(IOS_DEST)' build
