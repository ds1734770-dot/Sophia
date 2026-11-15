## What does this change?

## How was it tested?

- [ ] `QT_QPA_PLATFORM=offscreen pytest -q` passes
- [ ] `ruff check app main.py tests scripts` passes
- [ ] Tried in the app on: macOS / Windows (say which, or "not tried")

## Safety

- [ ] New actions that change something go through the tool registry with the right risk tier
- [ ] No new dependency, or it is pinned, declared in pyproject.toml and passes `scripts/licenses.py --check`
