def test_every_module_imports():
    """
    Catches syntax and import errors in modules no other test touches
    (Sophia itself, main, the watchers).
    """

    import importlib
    import pkgutil

    import app

    failures = []

    for module in pkgutil.walk_packages(app.__path__, "app."):

        try:
            importlib.import_module(module.name)

        except Exception as e:
            failures.append(f"{module.name}: {e!r}")

    assert not failures, "\n".join(failures)

    importlib.import_module("main")
