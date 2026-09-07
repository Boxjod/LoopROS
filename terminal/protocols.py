"""Normalize supported HTTP protocols to the existing ChatAgent contract."""


def encode(config, messages, tools):
    if config.get("protocol", "openai") == "openai":
        body = {"model": config["model"], "messages": [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages],
                config.get("token_field", "max_tokens"): config.get("max_output_tokens", 4096), "stream": False}
        if config.get('reasoning_effort') is not None:
            body['reasoning_effort'] = config['reasoning_effort']
        if tools:
            body["tools"] = tools
        return "/chat/completions", body
    items = []
    for message in messages:
        if "_responses_output" in message:
            items.extend(message["_responses_output"])
        elif message["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                          "output": message["content"]})
        else:
            content = message.get("content") or ""
            if isinstance(content, list):
                content = [{"type": "input_text", "text": part["text"]} if part["type"] == "text"
                           else {"type": "input_image", "image_url": part["image_url"]["url"]}
                           for part in content]
            items.append({"role": message["role"], "content": content})
    body = {"model": config["model"], "input": items, "max_output_tokens": config.get("max_output_tokens", 4096),
            "stream": False, "store": False, "include": ["reasoning.encrypted_content"]}
    if config.get('reasoning_effort') is not None:
        body['reasoning'] = {'effort': config['reasoning_effort']}
    if tools:
        body["tools"] = [{"type": "function", **tool["function"], "strict": False} for tool in tools]
    return "/responses", body


def decode(config, payload):
    if config.get("protocol", "openai") == "openai":
        return payload["choices"][0]["message"]
    if payload.get("status") != "completed":
        raise ValueError("Response did not complete")
    output = payload["output"]
    text, calls = [], []
    for item in output:
        if item["type"] == "message":
            text.extend(part.get("text", part.get("refusal", "")) for part in item["content"])
        elif item["type"] == "function_call":
            calls.append({"id": item["call_id"], "type": "function",
                          "function": {"name": item["name"], "arguments": item["arguments"]}})
    return {"role": "assistant", "content": "\n".join(text), "tool_calls": calls,
            "_responses_output": output}
