# Apollo Module API

A candidate module is not installed until it passes validation and the user
explicitly accepts it.

Required basic shape:

```python
class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "example",
                "description": "What this action does.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            }
        ]

    def self_test(self):
        return True

    def run(self, action, arguments):
        if action == "example":
            return {"ok": True}
        raise KeyError(action)
```

Optional `tests.py` is executed in a separate Python process during validation.
Tests must be non-interactive and must exit nonzero or raise an exception on
failure.

Apollo V6.2 can automatically repair files under `pending_modules/`, rerun the
validator, and repeat until they pass or the retry limit is reached.

Automatic repair can modify only:

- manifest.json
- module.py
- tests.py
- README.md

It cannot install the module and cannot modify Apollo core files.


## Optional UI page

A module can expose a UI page by adding:

```json
"ui": {
  "enabled": true,
  "title": "My Module",
  "default_placement": "apps"
}
```

and implementing:

```python
def build_ui(self, parent=None, ui_context=None):
    ...
    return QWidget(...)
```

Users can move the page between Apps, Sidebar, or Hidden from Apollo's Modules
page without editing the module.
