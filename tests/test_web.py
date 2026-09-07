import json
from pathlib import Path
import socket
import ssl
import tempfile
import unittest
from unittest.mock import patch, Mock

from terminal import web
from terminal.app import App, TOOLS
from terminal.config import load_config
from terminal.llm import ChatAgent
from terminal.protocols import encode


def page(body, kind="text/html", url="https://example.com"):
    return {"body": body, "content_type": kind, "url": url, "retrieved_at": "2026-09-05T00:00:00+00:00"}


def address(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class WebTests(unittest.TestCase):
    def test_extracts_visible_text_and_bounds_output(self):
        with patch.object(web, "request", return_value=page('<title>Title</title><script>bad()</script><style>secret</style><p>Hello &amp; world</p>' + 'x' * 7000)):
            result = web.web_fetch("https://example.com")
        self.assertEqual(result["title"], "Title")
        self.assertNotIn("bad()", result["text"])
        self.assertNotIn("secret", result["text"])
        self.assertIn("Hello & world", result["text"])
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["text"]), 6000)

    def test_rejects_nontext(self):
        with patch.object(web, "request", return_value=page("binary", "application/pdf")):
            with self.assertRaises(web.WebError):
                web.web_fetch("https://example.com/file.pdf")

    def test_rejects_unsafe_urls_before_connection(self):
        for url in ("file:///etc/passwd", "https://user:pass@example.com", "http://127.0.0.1", "http://169.254.169.254",
                    "https://localhost", "https://robot.local", "http://[::1]", "https://example.com:8888", "https://example.com/\nX:1"):
            with self.subTest(url=url), patch.object(web.socket, "socket") as connect:
                with self.assertRaises((ValueError, web.WebError)):
                    web.request(url)
                connect.assert_not_called()

    def test_private_dns_and_fake_ip_proxy_rules(self):
        with patch.object(web.socket, "getaddrinfo", return_value=address("10.0.0.1")):
            with self.assertRaises(web.WebError):
                web.public_target("https://example.com")
        with patch.object(web.socket, "getaddrinfo", return_value=address("198.18.1.2")):
            self.assertEqual(web.public_target("https://example.com")[3][0][4][0], "198.18.1.2")
            for url in ("http://example.com", "https://198.18.1.2"):
                with self.assertRaises(web.WebError):
                    web.public_target(url)

    def test_redirect_is_revalidated_and_socket_is_pinned(self):
        response = Mock(status=302)
        response.getheader.side_effect = lambda key, default=None: "http://127.0.0.1/private" if key == "Location" else default
        conn = Mock()
        conn.getresponse.return_value = response
        with patch.object(web.socket, "getaddrinfo", return_value=address("93.184.216.34")), \
             patch.object(web.socket, "socket") as sock, patch.object(web.http.client, "HTTPConnection", return_value=conn):
            with self.assertRaises(web.WebError):
                web.request("http://example.com")
            sock.return_value.connect.assert_called_once_with(("93.184.216.34", 443))
            conn.close.assert_called()

    def test_tls_failure_is_explicit(self):
        with patch.object(web, "public_target", side_effect=ssl.SSLCertVerificationError("bad certificate")):
            with self.assertRaises(web.WebError) as caught:
                web.request("https://example.com")
        self.assertEqual(caught.exception.details["error"], "tls_error")

    def test_request_size_limit_and_cleanup(self):
        response = Mock(status=200)
        response.getheader.side_effect = lambda key, default=None: default
        response.read1.side_effect = [b"x" * 65536] * 17
        conn = Mock()
        conn.getresponse.return_value = response
        with patch.object(web.socket, "getaddrinfo", return_value=address("93.184.216.34")), \
             patch.object(web.socket, "socket"), patch.object(web.http.client, "HTTPConnection", return_value=conn):
            with self.assertRaises(web.WebError) as caught:
                web.request("http://example.com")
        self.assertEqual(caught.exception.details["error"], "response_too_large")
        conn.close.assert_called_once()

    def test_search_fallback_and_source(self):
        xml = '<rss><channel><item><title>A</title><link>https://example.com/a</link><description>Hello &amp; world</description></item></channel></rss>'
        with patch.object(web, "request", side_effect=[web.WebError("http_error", "HTTP 403"), page(xml, "application/rss+xml")]) as fetch:
            result = web.web_search("机器人", 1)
        self.assertEqual(result["results"][0]["snippet"], "Hello & world")
        self.assertIn("cn.bing.com", fetch.call_args.args[0])
        self.assertIn("%E6", fetch.call_args.args[0])

    def test_search_challenge_is_not_a_result(self):
        with patch.object(web, "request", return_value=page("<html>captcha</html>")):
            with self.assertRaises(web.WebError) as caught:
                web.web_search("robot")
        self.assertEqual(caught.exception.details["error"], "search_unavailable")

    def test_weather_location_time_units_and_missing_city(self):
        geo = {"results": [{"name": "上海", "latitude": 31, "longitude": 121, "country": "中国"}]}
        weather = {"current": {"time": "2026-09-05T12:00", "temperature_2m": 25}, "current_units": {"temperature_2m": "°C"},
                   "daily": {"time": ["2026-09-05"]}, "daily_units": {}, "timezone": "Asia/Shanghai"}
        with patch.object(web, "request", side_effect=[page(json.dumps(geo)), page(json.dumps(weather))]) as fetch:
            result = web.web_weather("上海", 1, "CN")
        self.assertEqual(result["timezone"], "Asia/Shanghai")
        self.assertEqual(result["location"]["name"], "上海")
        self.assertEqual(result["current_units"]["temperature_2m"], "°C")
        self.assertIn("countryCode=CN", fetch.call_args_list[0].args[0])
        with patch.object(web, "request") as fetch:
            for args in ({}, {"location": ""}, {"location": "Paris", "days": True}):
                with self.assertRaises(ValueError):
                    web.dispatch("web_weather", args)
            fetch.assert_not_called()

    def test_no_weather_match_does_not_invent_forecast(self):
        with patch.object(web, "request", return_value=page('{}')) as fetch:
            result = web.web_weather("unknown city")
        fetch.assert_called_once()
        self.assertNotIn("current", result)
        self.assertEqual(result["locations"], [])

    def test_permissions_schedule_and_model_feedback(self):
        with tempfile.TemporaryDirectory() as root:
            app = App(load_config(Path(root) / "missing"), root)
            try:
                app.permissions.set_mode("plan")
                with patch("terminal.app.web_dispatch", return_value={"title": "Example", "source_url": "https://example.com"}) as fetch:
                    app.tool("web_fetch", {"url": "https://example.com"})
                    app.scheduled_tool("web_fetch", {"url": "https://example.com"})
                    app.permissions.set_rule("web_fetch", "deny")
                    with self.assertRaises(PermissionError):
                        app.scheduled_tool("web_fetch", {"url": "https://example.com"})
                    self.assertEqual(fetch.call_count, 2)
                    app.permissions.set_rule("web_fetch", "ask")
                    with self.assertRaises(PermissionError):
                        app.tool("web_fetch", {"url": "https://example.com"})
                    request_id = next(iter(app.permissions.requests()))
                    app.permissions.approve(request_id, app.tool)
                    self.assertEqual(fetch.call_count, 3)
                    client = Mock()
                    client.complete.side_effect = [
                        {"tool_calls": [{"id": "web1", "function": {"name": "web_fetch", "arguments": '{"url":"https://example.com"}'}}]},
                        {"content": "来源：https://example.com"}]
                    app.permissions.set_rule("web_fetch", "allow")
                    agent = ChatAgent(client, WEB_TOOLS, app.tool)
                    self.assertIn("https://example.com", agent.reply("读取网页"))
                    self.assertIn("Example", client.complete.call_args.args[0][-1]["content"])
            finally:
                app.close()

    def test_tools_encode_in_both_model_protocols(self):
        for protocol in ("openai", "responses"):
            config = {"protocol": protocol, "model": "test"}
            _, body = encode(config, [{"role": "user", "content": "weather"}], web.WEB_TOOLS)
            names = {t.get("name", t.get("function", {}).get("name")) for t in body["tools"]}
            self.assertEqual(names, web.WEB_NAMES)
        self.assertTrue(web.WEB_NAMES.issubset({t["function"]["name"] for t in TOOLS}))


WEB_TOOLS = web.WEB_TOOLS

if __name__ == "__main__":
    unittest.main()
