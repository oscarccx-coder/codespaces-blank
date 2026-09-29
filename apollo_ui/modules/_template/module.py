class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "example",
                "description": "Example action exposed to Apollo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Some text"}
                    },
                    "required": ["text"]
                }
            }
        ]

    def self_test(self):
        # Optional. Raise an exception or return False to block installation.
        return True

    def run(self, action, arguments):
        if action == "example":
            return {"echo": arguments.get("text", "")}
        raise KeyError(action)
