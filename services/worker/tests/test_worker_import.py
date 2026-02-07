import services.worker.worker.main as worker_main


def test_worker_module_imports() -> None:
    assert worker_main.__doc__ is not None
