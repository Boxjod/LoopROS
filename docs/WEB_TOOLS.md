# Web tools

Loop 对话可调用 `web_search`、`web_fetch`、`web_weather`，无需额外工具 API Key。原有模型 API 配置继续使用，未修改用户凭据或服务商设置。重启已经运行的 Loop 会话以加载新工具。

直接对话示例：

- `上海今天天气怎么样？`
- `搜索 ROS 2 官方文档，并打开原文核对。`
- `读取 https://example.com 并总结。`

如果用户只问“今天天气”，且对话没有可靠城市信息，Master 应先询问城市；不会自动读取 IP 定位或提供模拟天气。同名城市查询返回第一匹配地点及其他候选，应在有歧义时明确地点。天气返回时区、数据时间、单位和来源；属于天气模型数据，不是本地传感器实测。

## 工具和权限

| 工具 | 参数 | 结果 |
| --- | --- | --- |
| web_search | query；可选 limit=1..5，默认5 | Bing RSS 标题、摘要、来源链接、抓取时间 |
| web_fetch | url | 网页标题、文本、最终URL、抓取时间及截断标记 |
| web_weather | location；可选 days=1..7，默认3；country_code如CN | 地点、当前天气、每日预报、单位、时区、数据源 |

三项作为只读工具默认 allow，在 plan 模式可使用；定时对话经过相同权限检查。使用现有 `/permissions deny web_search` 或 `/permissions ask web_fetch` 可单独控制。已注册的子 Agent 不自动获得联网工具；本次未扩大其工具授权。

支持现有 Chat Completions 与 Responses 的 function tool 编码，不依赖特定模型服务商的内置搜索。默认工具目录包含联网工具；由模型按用户请求选择。工具异常包含具体阶段/原因，不能据此声称全机断网；网页文字是资料，不能覆盖用户指令或工具权限。

## 网络与内容边界

使用标准库直接 HTTP(S)，不携带模型 Key、浏览器 Cookie 或用户自定义认证头，不自动读取系统 HTTP_PROXY/HTTPS_PROXY。支持正常直连及操作系统透明代理；需要显式 HTTP 代理的环境尚未适配。

仅允许80/443端口，拒绝嵌入凭据的URL、本地文件、localhost、.local及私有/链路本地目标。解析后的地址固定到连接，每次重定向重新检查，TLS 校验保留。为兼容本次机器的 TUN Fake-IP DNS，允许公开域名经198.18.0.0/15映射连接，但仅限443上的HTTPS且仍验证原域名证书；不允许直接访问此IP字面量，也不允许HTTP使用该映射。其他私有地址不会被这一例外放行。

每次请求采用15秒网络预算、最多4次重定向、1 MiB响应限制；系统DNS解析可能受系统解析器超时影响，不宣称硬实时截止。单次搜索可尝试两个Bing入口；天气通常需要地名查询及预报两个请求。现有取消机制在阻塞网络调用返回或超时后生效。

网页正文最多6000字符，不执行JavaScript，不读取PDF、图像或登录页面。搜索RSS是无需Key的尽力服务，可能限流、拒绝或返回不相关结果；应打开原始来源核对，失败时明确返回 search_unavailable，不绕过验证码。大型页面或不支持类型返回明确错误。

天气使用 [Open-Meteo Forecast API](https://open-meteo.com/en/docs) 与 [Geocoding API](https://open-meteo.com/en/docs/geocoding-api)，遵循服务方使用条款、额度和署名要求；免费公共入口的非商业使用范围不等于产品商业授权。商用部署需按服务条款选用合适端点/方案，本次未接商业认证。输出保留 Open-Meteo 来源与链接。

## 实现与验证

实现：[web.py](../terminal/web.py)、[注册与分发](../terminal/app.py)、[权限](../terminal/permissions.py)、[通用上下文](../terminal/conversation_context.py)。

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_web.py' -v
```

2026-09-05：13项新增测试通过，覆盖提取/截断、地址和重定向检查、Fake-IP边界、TLS错误、下载上限、搜索失败/回退、中文城市/无结果、权限/定时调用、模型工具反馈及两种协议编码。真实联网验证网页读取、搜索来源和上海天气成功；模型调用使用替身，未测试真实模型是否每次主动选择正确工具。不以联网工具成功宣称机器人任务成功。


## 天气对话（2026-09-07）

已删除自然语言天气拦截器。模型负责理解城市/日期、缺参数提问和结果说明，查询通过同一个web_weather工具循环执行。权限、地点查询、1至7天范围、来源/单位和网络错误仍由工具实现约束。

[test_weather_dialog](../tests/test_weather_dialog.py)用模型协议替身验证多轮缺城市询问、换城调用、错误/拒绝回执及编程请求不被天气词拦截；[test_web](../tests/test_web.py)验证实际工具的数据解析和网络边界。尚未把这些离线测试视为真实模型语义理解验收。
