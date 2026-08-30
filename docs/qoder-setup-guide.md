# Qoder 后端使用说明

## 架构概述

```
用户界面 → QoderClient (前端) → HTTP+SSE → qoder-server.mjs (Node sidecar) → @qoder-ai/qoder-agent-sdk → Qoder 云端
```

## 新用户 git clone 后需要什么？

### 1. 自动获得的（`pnpm install` 后就有）

| 组件 | 来源 | 说明 |
|------|------|------|
| `@qoder-ai/qoder-agent-sdk` | `package.json` 依赖 | `pnpm install` 自动安装 |
| `qodercli.exe` (v1.1.7) | SDK 内置 | 在 `node_modules/.../@qoder-ai/qoder-agent-sdk/dist/_bundled/qodercli.exe` |
| `qoder-server.mjs` | 项目自带 | 在 `runtime/qoder-sidecar/qoder-server.mjs` |
| `QoderClient.ts` | 项目自带 | 在 `packages/sdk/src/QoderClient.ts` |

**不需要额外下载任何东西。** `pnpm install` 就够了。

### 2. 需要用户手动做的（首次使用 Qoder 后端时）

#### 认证登录（二选一）：

**方式 A：qodercli 登录（推荐，和 OpenCode 体验一致）**

```bash
# 用 SDK 内置的 qodercli 登录
node node_modules/.pnpm/@qoder-ai+qoder-agent-sdk@*/node_modules/@qoder-ai/qoder-agent-sdk/dist/_bundled/qodercli.exe login
```

这会打开浏览器扫码登录，登录后凭证保存在 `~/.qoder/` 或 `~/.qoder-cn/` 目录下。之后 QoderClient 自动复用登录态，**无需再次登录**。

**方式 B：PAT 环境变量**

```bash
# 设置 Personal Access Token
set QODER_PERSONAL_ACCESS_TOKEN=your_token_here
```

在 [qoder.com](https://qoder.com) 生成 PAT。

### 3. 切换后端

在桌面应用中：**设置 → 运行时 → Backend 下拉框 → 选择 Qoder CN**

应用会自动启动 `qoder-server.mjs` sidecar（端口 4097），通过 HTTP+SSE 连接 Qoder 云端。

---

## 和 OpenCode 的对比

| | OpenCode | Qoder CN |
|---|---|---|
| 二进制 | Tauri 内置 `opencode.exe` | SDK 内置 `qodercli.exe` |
| 认证 | **无需认证**（纯本地） | **需要登录一次**（云端服务） |
| 首次使用 | 装好就能用 | 装好 + 登录一次就能用 |
| sidecar | Tauri Rust 启动 | Tauri Rust 启动 Node sidecar |
| 网络 | 纯本地 | 需要联网 |

---

## 总结

> **别人 git clone 后，`pnpm install` 就拥有了所有依赖。** 切换到 Qoder CN 后端时，只需要**首次登录一次**（扫码或 PAT），之后就和 OpenCode 一样随时切换使用。

唯一的区别是 OpenCode 完全离线可用，而 Qoder 是云端服务需要账号认证。代码层面已经做到了"装好就能用"，不需要用户额外下载 CLI 或 exe。

---

## 故障排查

### Qoder 连接失败

1. **检查登录状态**
   ```bash
   # 查看是否有登录凭证
   ls ~/.qoder/
   ls ~/.qoder-cn/
   ```

2. **重新登录**
   ```bash
   node node_modules/.pnpm/@qoder-ai+qoder-agent-sdk@*/node_modules/@qoder-ai/qoder-agent-sdk/dist/_bundled/qodercli.exe login
   ```

3. **检查 sidecar 是否运行**
   ```bash
   # 查看端口 4097 是否被占用
   netstat -ano | findstr 4097
   ```

4. **查看日志**
   - 前端控制台（F12）
   - Tauri 应用日志

### 常见问题

**Q: 为什么切换到 Qoder 后一直显示 connecting？**
A: 可能是 qoder-server.mjs sidecar 没有启动成功。检查 Node.js 是否可用，以及 `runtime/qoder-sidecar/` 目录是否存在。

**Q: 登录后还是连接失败？**
A: 尝试重启应用。登录凭证保存在 `~/.qoder/` 目录，重启后会自动加载。

**Q: 可以用 PAT 代替登录吗？**
A: 可以。设置环境变量 `QODER_PERSONAL_ACCESS_TOKEN` 后，QoderClient 会优先使用 PAT 认证。

---

## 技术细节

### 认证流程

1. `QoderClient.connect()` 被调用
2. Tauri Rust 后端启动 `qoder-server.mjs` sidecar
3. Sidecar 调用 `qodercliAuth()` 或读取 `QODER_PERSONAL_ACCESS_TOKEN`
4. SDK 建立与 Qoder 云端的连接
5. 前端通过 SSE 接收流式响应

### 文件位置

```
ai4s-jingming-yanhuan-master/
├── packages/sdk/src/
│   └── QoderClient.ts          # 前端客户端
├── runtime/qoder-sidecar/
│   ├── qoder-server.mjs        # Node sidecar
│   ── package.json
├── apps/desktop/src-tauri/src/
│   └── runtime.rs              # Tauri Rust 后端（启动 sidecar）
└── node_modules/.../@qoder-ai/qoder-agent-sdk/
    └── dist/_bundled/
        └── qodercli.exe        # 内置 CLI
```
