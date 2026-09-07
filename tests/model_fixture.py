"""Protocol fixtures: model-selected tools, without network inference."""
import json


def call(tool_name, **args):
    return {'tool_calls': [{'id': tool_name, 'function': {'name': tool_name, 'arguments': json.dumps(args)}}]}
