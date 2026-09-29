import ast
import math
import operator


BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
NAMES = {
    "pi": math.pi,
    "e": math.e,
}


def safe_eval(expression):
    tree = ast.parse(expression, mode="eval")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("Exponent is too large.")
            return BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARYOPS:
            return UNARYOPS[type(node.op)](visit(node.operand))
        if isinstance(node, ast.Name) and node.id in NAMES:
            return NAMES[node.id]
        raise ValueError("Unsupported expression.")

    result = visit(tree)
    if isinstance(result, complex):
        raise ValueError("Complex results are not supported.")
    return result


class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "calculate",
                "description": "Calculate a mathematical arithmetic expression accurately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Arithmetic expression, for example (12.5 * 4) + 3"
                        }
                    },
                    "required": ["expression"]
                }
            }
        ]

    def run(self, action, arguments):
        if action != "calculate":
            raise KeyError(action)
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            raise ValueError("No expression supplied.")
        if len(expression) > 500:
            raise ValueError("Expression is too long.")
        return {
            "expression": expression,
            "answer": safe_eval(expression),
        }
