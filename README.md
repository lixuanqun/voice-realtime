# voice-realtime

[![CI](https://github.com/lixuanqun/voice-realtime/actions/workflows/ci.yml/badge.svg)](https://github.com/lixuanqun/voice-realtime/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Go 1.21+](https://img.shields.io/badge/go-1.21+-00ADD8.svg)](https://go.dev/dl/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![OpenAI Realtime](https://img.shields.io/badge/protocol-OpenAI%20Realtime-412991.svg)](https://platform.openai.com/docs/guides/realtime)

**[中文](#voice-realtime-1)** · **[English](#voice-realtime-en)** · **[架构](docs/ARCHITECTURE.md)** · **[路线](docs/ROADMAP.md)** · **[RFC](docs/rfc/README.md)** · **[贡献](CONTRIBUTING.md)**

---

## voice-realtime

> **一套 OpenAI Realtime 协议，对接多家国内端到端语音大模型。**

换云厂商不改客户端 —— 只需修改 WebSocket URL 上的 `provider` 参数。

```text
ws://localhost:8080/v1/realtime?provider=zhipu&model=glm-realtime-flash
ws://localhost:8080/v1/realtime?provider=stepfun&model=stepaudio-2.5-realtime
ws://localhost:8080/v1/realtime?provider=volcengine
ws://localhost:8080/v1/realtime?provider=bailian
```

```bash
export ZHIPU_API_KEY=your_key
go run ./cmd/voice-realtime
```

### 为什么需要这个项目？

国内端到端语音大模型（豆包、百炼、智谱、阶跃等）**协议各不相同**：有的兼容 OpenAI Realtime，有的是二进制帧，有的带复杂状态机。voice-realtime 在中间做**统一网关**：

```text
  你的客户端（Vui / OpenClaw / 自研 App）
              │
              │  OpenAI Realtime（PCM16 24kHz）
              ▼
       ┌──────────────┐
       │ voice-realtime│  ← 密钥只在服务端，客户端无感换云
       └──────┬───────┘
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
  智谱     阶跃     火山     百炼
```

### 支持的云厂商

| 厂商 | `provider` | 适配策略 | 状态 |
|------|-------------|----------|------|
| 智谱 GLM-Realtime | `zhipu` | 透明代理 | 🚧 骨架可用，待联调 |
| 阶跃星辰 StepFun | `stepfun` | 透明代理 | 🚧 骨架可用，待联调 |
| 火山豆包 | `volcengine` | 二进制协议转换 | 🚧 开发中 |
| 阿里云百炼 | `bailian` | 多模态状态机 | 🚧 开发中 |

> 状态说明见 [开发路线](docs/ROADMAP.md)。

### 核心机制（30 秒版）

| 机制 | 说明 |
|------|------|
| **北向统一** | 客户端只讲 OpenAI Realtime API |
| **Provider 插件** | 新厂商 = 实现一个 Go 接口 + 注册 |
| **双适配策略** | 透明代理（智谱/阶跃）或 协议转换（火山/百炼） |
| **服务端持钥** | API Key 不下发客户端 |
| **音频管线** | 自动 24 kHz ↔ 16 kHz 重采样 |

详细架构图与序列图 → **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

### 快速开始

```bash
git clone https://github.com/lixuanqun/voice-realtime.git
cd voice-realtime
cp .env.example .env    # 填入你要用的厂商 Key

go test ./...
go run ./cmd/voice-realtime
```

### 参与贡献

我们**特别欢迎**以下贡献：

- 有火山 / 百炼账号的同学帮忙**真实联调**
- 编写 **Python / JS 示例客户端**（`good first issue`）
- **新增云厂商** Provider 插件
- 文档翻译、协议映射表补充

→ [CONTRIBUTING.md](CONTRIBUTING.md) · [Good First Issues](https://github.com/lixuanqun/voice-realtime/issues?q=is%3Aopen+label%3A%22good+first+issue%22)

Python 用户可以从 [examples/python_client](examples/python_client/README.md) 开始，使用 OpenAI Realtime 事件连接本地网关。

### 文档索引

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 现状/目标五层架构、六大机制、对照表 |
| [ROADMAP.md](docs/ROADMAP.md) | Phase 0–5，P1a/P1b/P1c 拆分 |
| [rfc/](docs/rfc/README.md) | 架构 RFC（Middleware、热路径 Tier） |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献流程、新增 Provider 指南 |
| [providers/](docs/providers/) | 各厂商协议映射表 |

### License

[MIT](LICENSE)

---

## voice-realtime (EN)

> **One OpenAI Realtime API. Multiple Chinese cloud voice LLMs.**

Switch providers without changing your client — just update the `provider` query parameter.

**Supported**: Zhipu GLM-Realtime · StepFun · Volcengine Doubao · Alibaba Bailian

| Doc | Description |
|-----|-------------|
| [Architecture](docs/ARCHITECTURE.md) | Diagrams, plugin model, adapter strategies |
| [Roadmap](docs/ROADMAP.md) | Phased delivery plan |
| [Contributing](CONTRIBUTING.md) | How to add a new provider |

**We need help with**: real-account integration testing, sample clients, new provider plugins.

For a minimal Python WebSocket client, see [examples/python_client](examples/python_client/README.md).

```bash
go run ./cmd/voice-realtime
# ws://localhost:8080/v1/realtime?provider=zhipu&model=glm-realtime-flash
```

MIT License.
