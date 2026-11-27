# 隐私与数据边界

Fin-Wiki 核心库本身不收集、不上传、不持久化用户数据。

## 1. 核心库

`fin_wiki/` 的确定性账本、编译器、算子、Resolver 等模块在本地运行，
不发起网络请求，不写入外部服务。

## 2. LLM adapter

`fin_wiki/adapters.py` 只提供边界，不内置 provider。调用方注入的
OpenAI-compatible provider 可能会接收输入文本：

```text
FINWIKI_LLM_BASE_URL
FINWIKI_LLM_API_KEY
FINWIKI_LLM_MODEL
```

使用云端 provider 时，输入文本会发送给第三方。请遵守：

- 不发送个人信息、客户数据、未公开业务资料；
- 默认只使用合成或已脱敏文本；
- 真实数据接入的合规责任由部署方承担；
- 优先使用本地 provider（Ollama / vLLM / llama.cpp）处理敏感场景。

## 3. 密钥

密钥只从环境变量读取，不写入仓库、不打印、不落盘。不要把
`.env`、`*.pem`、`*.key` 或任何真实 token 提交到仓库。

## 4. 不构成专业意见

本项目的输出不构成审计、税务、法律或投资意见；案例评估只输出
“疑似/需核”，不输出“违规”结论。

## 5. 报告安全问题

见 [SECURITY.md](../SECURITY.md)。不要在公开 issue 中粘贴个人信息、
客户数据、真实年报或密钥。
