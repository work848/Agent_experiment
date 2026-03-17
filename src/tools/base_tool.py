import inspect

REGISTERED_TOOLS = []


def tool(func):
    """
    Register a function as a tool and auto generate schema
    """

    sig = inspect.signature(func)

    properties = {}
    required = []

    for name, param in sig.parameters.items():

        properties[name] = {
            "type": "string"
        }

        if param.default == inspect._empty:
            required.append(name)

    schema = {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": func.__doc__ or "",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }

    REGISTERED_TOOLS.append((schema, func))

    return func