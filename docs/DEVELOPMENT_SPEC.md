# 景明研环 — 开发规范与注意事项

> **受众**：AI Agent（Claude Code、Cursor、Codex 等），以及新加入的人类贡献者。
> **目的**：让接手该项目的 agent 或开发者能在最短时间内理解项目结构、技术栈、架构约束和编码规范，高效开展工作。
> **语言**：讨论用中文；代码、注释、文件路径、变量名、Git 提交信息一律英文。

---

## 1. 项目概览

**景明研环**（景明研环）是一个开源、本地优先、模型无关、可复现的 AI 科研工作台。支持 macOS / Windows / Linux 桌面端，以及通过 Remote Access Gateway 在手机浏览器上使用。

- **Brand name**：景明研环
- **Bundle ID**：`com.jingming.yanhuan`
- **内部包名**：`@jingming/*`
- **版本**：0.2.5
- **许可证**：MIT
- **包管理器**：pnpm 9.4.0
- **Node 要求**：>= 20
- **仓库**：<https://github.com/hzf716666/jingming-yanhuan>

### 核心定位

> 不是普通的论文总结工具。它是一个本地优先、模型无关、可复现、可审计的研究 agent 工作台。

核心能力：文献检索 → 论文解析 → 数据分析 → 代码执行 → 图表生成 → 报告撰写 → 引文检查 → 溯源追踪 → 可复用工作流。

---

## 2. 仓库结构

```
jingming-yanhuan/
├── apps/desktop/             # Tauri 2 + React 桌面应用（主战场）
│   ├── src/                  #   React 前端源码
│   │   ├── app/              #     路由、布局、全局 Provider
│   │   ├── components/       #     UI 组件（按功能分目录）
│   │   ├── features/         #     功能占位目录（.gitkeep 占位，待实现）
│   │   ├── lib/              #     核心逻辑库（runtime store、tauri 桥接、文件、溯源等）
│   │   ├── i18n/             #     国际化（7 种语言 + 2 种未启用）
│   │   └── test/             #     测试配置（setup.ts、render.tsx）
│   ├── src-tauri/            #   Rust 后端（Tauri commands）
│   │   ├── src/              #     每个 .rs 文件对应一个功能模块
│   │   ├── binaries/         #     捆绑的 sidecar 二进制（git-ignored，脚本拉取）
│   │   ├── icons/            #     应用图标（多平台）
│   │   └── tauri.conf.json   #     Tauri 配置
│   ├── index.html            #   入口 HTML
│   ├── vite.config.ts        #   Vite 配置（含 vitest）
│   ├── tailwind.config.js    #   Tailwind CSS 配置
│   └── tsconfig.json         #   TypeScript 配置
├── packages/                 # 内部共享包
│   ├── sdk/                  #   OpenCodeClient — 前端与 agent runtime 的唯一通信边界
│   ├── shared/               #   共享领域类型 + 图表调色板
│   └── ui/                   #   共享 UI 包（占位，当前为空）
├── runtime/                  # 运行时知识 + 技能
│   ├── skills/core/          #   第一方科研审查技能
│   ├── skills/external/      #   外部技能（构建时拉取，git-ignored）
│   ├── harness/              #   运行时 harness 知识
│   ├── kernel/               #   Python/R 内核桥接脚本
│   ├── goal-plugin/          #   目标循环插件（JS，构建时拉取）
│   ├── mcp/                  #   MCP 运行时笔记
│   └── opencode-profile/     #   景明研环 的 OpenCode 配置/profile
├── docs/                     # 产品和设计文档
│   ├── PRD.md                #   产品需求文档
│   ├── TECHNICAL_DESIGN.md   #   技术设计文档
│   ├── DEVELOPMENT_SPEC.md   #   本文档
│   └── rfc/                  #   RFC（agent-runtime、remote-access-gateway 等）
├── scripts/                  # 构建和发布脚本
│   ├── dev/                  #   拉取 sidecar/uv/skills/goal-plugin 的脚本
│   └── release/              #   发布脚本
├── examples/                 # 内置示例项目（bci-trends、climate-trends）
├── AGENTS.md                 # Agent 上下文规则（CLAUDE.md 是此文件的符号链接）
├── PROGRESS.md               # 唯一进度文件
├── package.json              # 根 package.json（定义 workspace 脚本）
└── pnpm-workspace.yaml       # pnpm workspace 配置
```

---

## 3. 技术栈

| 层 | 技术 | 备注 |
| --- | --- | --- |
| **桌面壳** | Tauri 2（Rust） | 非 Electron；用 OS 原生 WebView |
| **前端** | React 18 + TypeScript + Vite | strict mode |
| **样式** | Tailwind CSS + Radix UI | shadcn 风格组件 |
| **状态管理** | Zustand（`useRuntimeStore`） | 全局 store 在 `src/lib/runtime.ts` |
| **路由** | React Router v6 | 定义在 `src/app/router.tsx` |
| **测试** | Vitest + Testing Library | jsdom 环境 |
| **国际化** | i18next + react-i18next | 7 种已发布语言 |
| **Agent Runtime** | OpenCode 1.17.13（捆绑 sidecar） | 固定版本，不与用户本地安装冲突 |
| **通信协议** | OpenCode HTTP + SSE API | 前端通过 `OpenCodeClient`（`packages/sdk`）调用 |
| **存储** | 本地文件 + SQLite + JSONL | provenance.jsonl、runs.jsonl |
| **打包** | Tauri DMG / NSIS / MSI / .deb / .rpm | GitHub Actions CI |
| **图表** | 自定义 `CHART_PALETTE`（`@jingming/shared`） | 统一调色板，同时用于 App 图表和 matplotlib 样式 |

### 包间依赖方向

```
@jingming/shared  ←  @jingming/sdk  ←  @jingming/desktop
   (类型)         (客户端)       (主应用)
```

**关键约束**：UI 永远不能直接调用 OpenCode，必须通过 `packages/sdk` 中的 `OpenCodeClient`。

---

## 4. 架构详解

### 4.1 三层架构

```
┌─────────────────────────────────────────┐
│  React Frontend (apps/desktop/src/)     │
│  - Zustand store (lib/runtime.ts)       │
│  - Components (components/)             │
│  - Pages (app/routes/)                  │
└──────────────┬──────────────────────────┘
               │ @jingming/sdk (AgentRuntime interface)
┌──────────────▼──────────────────────────┐
│  OpenCodeClient (packages/sdk/)         │
│  - HTTP + SSE 协议实现                   │
│  - 事件归一化（SSE → OpenCodeEvent）      │
│  - AgentRuntime 接口                    │
└──────────────┬──────────────────────────┘
               │ HTTP + SSE (loopback)
┌──────────────▼──────────────────────────┐
│  Rust Backend (apps/desktop/src-tauri/) │
│  - 管理 sidecar 生命周期                 │
│  - 文件系统操作、内核管理、网关等          │
│  - Tauri IPC (invoke)                   │
└─────────────────────────────────────────┘
```

### 4.2 Agent Runtime（OpenCode sidecar）

- **捆绑**：固定在 `OPENCODE_VERSION = "1.17.13"`（`packages/sdk/src/types.ts:7`）。
- **隔离**：
  - 使用**捆绑的二进制文件**，不依赖用户 PATH。
  - 使用**专用空闲端口**，不占用默认 4096。
  - 使用**应用私有** `XDG_CONFIG_HOME`/`XDG_DATA_HOME`（`~/Library/Application Support/com.jingming.yanhuan/runtime/`）。
  - 共享用户登录凭据（只读复制 `auth.json`），但从不修改用户数据。
  - 退出时自动终止。
- **启动流程**：`User opens app → Tauri starts → Frontend loads → startRuntime() → Sidecar spawns → SDK connects`

### 4.3 前端核心状态管理

状态中心在 `src/lib/runtime.ts` 的 `useRuntimeStore`（Zustand store）：

```typescript
// 核心状态字段
interface RuntimeStore {
  url: string;              // sidecar 的 base URL
  status: RuntimeStatus;    // "connecting" | "ready" | "error" | "offline"
  sessions: Session[];      // 所有会话
  currentId: string | null; // 当前活动会话 ID
  threads: Map<string, ThreadBlock[]>;  // 每个会话的线程块
  providers: ProviderInfo[];  // 可用模型提供者
  ...
}
```

**重要**：`foldEvent()` 函数处理从 SSE 流接收的每一个事件，将其折叠到对应会话的 `threads` 中。这是前端最核心的数据流函数。

### 4.4 三种运行模式

应用支持三种运行模式：

| 模式 | 触发条件 | 特点 |
| --- | --- | --- |
| **Tauri 桌面** | `isTauri === true` | 完整功能，Rust 后端 |
| **Web 开发** | `pnpm dev`（无 Tauri） | 前端调试，部分功能不可用 |
| **Gateway Web** | `isGatewayWeb === true`（`window.__OS_WEB__`） | 通过 Remote Access Gateway 在浏览器中运行 |

- 代码使用 `isTauri`、`isGatewayWeb` 守卫来条件性地执行平台特定代码。
- `lib/tauri.ts` 中的所有函数在浏览器中返回 `null`/`[]`/空操作。
- 必须在手机宽度视口下工作（`useIsMobile()` + Tailwind 响应式）。

---

## 5. 开发工作流

### 5.1 环境准备

```bash
# 克隆仓库
git clone https://github.com/hzf716666/jingming-yanhuan
cd jingming-yanhuan

# 安装依赖
pnpm install

# 拉取捆绑的 sidecar 和技能（git-ignored）
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
bash scripts/dev/fetch-skills.sh
bash scripts/dev/fetch-goal-plugin.sh
```

### 5.2 常用命令

```bash
# 开发模式（仅前端，在浏览器中运行）
pnpm dev

# Tauri 开发模式（启动 Rust 后端 + 前端）
pnpm --filter @jingming/desktop tauri dev

# 构建桌面安装包
pnpm --filter @jingming/desktop tauri build

# 测试（前端）
pnpm test

# 类型检查
pnpm typecheck

# 代码检查
pnpm lint

# Rust 测试
cd apps/desktop/src-tauri && cargo test
```

### 5.3 新增功能的开发流程

1. **理解现有代码**：阅读相关 RFC（`docs/rfc/`）和 `AGENTS.md`。
2. **最小化变更**：每次变更应该是可验证的最小集合。
3. **测试先行**：添加测试覆盖新逻辑。
4. **运行检查**：`pnpm typecheck && pnpm lint && pnpm test` 全部通过。
5. **记录进度**：在 `PROGRESS.md` 顶部追加一行（`YYYY-MM-DD HH:MM · 简短结论`）。

### 5.4 PROGRESS.md 规范

- **唯一的进度文件**，格式：每行一条 `YYYY-MM-DD HH:MM · 一句话结论`，最新在上。
- **只记录结果和阻塞项**，不要长篇大论。
- 不要随意新增 Markdown 文档——文档多了就是债务。

---

## 6. 编码规范

### 6.1 TypeScript / React 规范

#### 文件组织

- **组件** → `src/components/<功能域>/<ComponentName>.tsx`
- **测试文件** → 与源文件同目录，命名为 `<ComponentName>.test.tsx`
- **逻辑库** → `src/lib/<功能域>.ts`
- **路由页面** → `src/app/routes/<PageName>.tsx`
- **每个目录都有 `.gitkeep`** 占位，即使目录暂时为空也不要删除它。

#### 命名规范

- **组件**：PascalCase — `LiveSessionPage`、`ModelPicker`、`ToolCallRow`
- **文件**：PascalCase（组件）、camelCase（模块）— `runtime.ts`、`modelCatalog.ts`
- **函数/变量**：camelCase — `foldEvent`、`listProviders`、`currentId`
- **常量**：UPPER_SNAKE_CASE — `DEFAULT_OPENCODE_URL`、`DRAFT_KEY`
- **类型/接口**：PascalCase — `ThreadBlock`、`SessionMeta`、`ToolCallStatus`
- **事件类型**：`领域.动作`（如 `text.updated`、`session.idle`、`question.asked`）

#### 类型安全

- **严格模式**（`strict: true`）：所有类型必须显式声明。
- **禁止未使用的变量和参数**（`noUnusedLocals: true`、`noUnusedParameters: true`）。
- **使用 `import type`** 导入仅用作类型的导出。
- **避免 `any`**：使用 `unknown` 并在必要时进行类型守卫。

#### React 模式

- **函数组件** + Hooks，无 Class 组件。
- **Zustand store** 选择器：从 store 中选择最小所需数据，避免不必要的重渲染。
  ```typescript
  // ✅ 好：只选择需要的数据
  const thread = useRuntimeStore((s) => s.threads.get(sessionId));
  
  // ❌ 坏：订阅整个 store
  const store = useRuntimeStore();
  ```
- **性能关键组件**使用 `React.memo`：`AgentMessage`、`ToolCallRow`、`UserMessage` 等。
- **使用 `useThrottledValue`** hook 来限制高频更新的重渲染（如流式 markdown 解析，90ms 节流）。

#### Import 路径

- **路径别名**：`@/*` → `src/*`、`@jingming/shared`、`@jingming/sdk`
- **不要使用相对路径跨目录引用**，始终使用别名。
  ```typescript
  // ✅ 好
  import { useRuntimeStore } from "@/lib/runtime";
  import type { ThreadBlock } from "@jingming/shared";
  
  // ❌ 坏
  import { useRuntimeStore } from "../../lib/runtime";
  ```

#### 平台守卫

当功能只能在特定平台工作时：

```typescript
// 桌面端独有功能
if (!isTauri) return null;

// 仅在桌面 WebView 中（非 Web 模式）
if (isGatewayWeb) return <WebFallback />;

// 仅在 Tauri 中执行
const { invoke } = await import("@tauri-apps/api/core");
```

对于无法在 Web 模式下工作的功能，应隐藏控件而不是显示一个会失败的控件。

### 6.2 Rust 规范

#### 文件组织

- 每个功能模块一个 `.rs` 文件：`runtime.rs`、`gateway.rs`、`provenance.rs`、`runs.rs` 等。
- `lib.rs` 是 Tauri 入口：注册所有 Tauri commands、plugin 和 managed state。
- `main.rs` 只调用 `lib::run()`。

#### Tauri Command 模式

```rust
#[tauri::command(async)]
pub fn my_command(app: AppHandle, state: State<'_, MyState>, arg: String) -> Result<String, String> {
    // 1. 参数验证
    // 2. 业务逻辑
    // 3. 返回 Result<Output, String>
}
```

- 所有命令使用 `#[tauri::command(async)]`。
- 错误返回 `Result<T, String>`（`Err("human readable error")`）。
- 使用 `AppHandle` 获取路径、配置等。
- 使用 `State<'_, MyState>` 管理应用级状态。
- **Windows 特定**：所有子进程启动使用 `quiet_command()` 而非 `std::process::Command::new()`，避免弹出控制台窗口。
- **Windows 特定**：`enriched_path()` 预置 conda 路径，因为 GUI 应用的 PATH 不包含用户 shell 配置。

#### 安全性

- 敏感数据目录调用 `tighten_private()` 设置 Unix 权限 700/600。
- 密码永不被持久化：`server_password()` 使用 `OnceLock`，只在内存中。
- 使用 `random_hex()`（OS CSPRNG）生成令牌。

### 6.3 国际化（i18n）

- **7 种已发布语言**：en、zh-Hans、ja、es、de、fr、ko
- **2 种注册但未启用**：pt-BR、ar
- **翻译文件位置**：`src/i18n/locales/<code>/translation.json`
- **命名空间**：按功能领域（`session:`、`settings:`、`files:`、`common:` 等）
- **新增 i18n key 时**：
  1. 在 `en/translation.json` 中添加英文文本
  2. 在所有 7 个 `locales` 目录中添加对应翻译（可使用 `en` 作为占位符）
  3. 运行 i18n 奇偶校验测试确保一致性
- **代码中使用**：`const { t } = useTranslation();` 然后 `t('namespace:key')`

### 6.4 样式规范

- **使用 Tailwind CSS** 类，不要写内联样式或 CSS 模块。
- **主题**：使用 CSS 变量（由 `ThemeProvider` 管理），支持 light / warm / dark 三种主题。
- **颜色**：使用 Tailwind 的语义化颜色类（`bg-card`、`text-foreground`、`border-border`）。
- **响应式**：使用 Tailwind 断点（`sm:`、`md:`、`lg:`），确保手机宽度下可用。
- **图表调色板**：使用 `@jingming/shared` 中的 `CHART_PALETTE` — 这是应用内图表和 agent 生成 matplotlib 图的唯一颜色来源。

---

## 7. 测试规范

### 7.1 测试配置

- **框架**：Vitest（vitest 配置在 `vite.config.ts` 的 `test` 字段）
- **环境**：jsdom
- **setup 文件**：`src/test/setup.ts`（polyfills、localStorage shim、i18n 初始化）
- **断言**：Testing Library + `@testing-library/jest-dom`

### 7.2 测试文件组织

- 测试文件与源文件在同一目录，命名为 `<Name>.test.tsx` 或 `<Name>.test.ts`。
- `src/test/render.tsx` 导出一个包装了 providers 的 `render` 函数，用于组件测试。
- `src/test/setup.ts` 处理 DOM polyfills 和 i18n 初始化。

### 7.3 测试要求

- **新增功能必须添加测试**。
- **修复 bug 应添加回归测试**。
- **运行所有测试**：`pnpm test`（所有前端测试）。
- **Rust 测试**：`cargo test`（在 `src-tauri` 目录下）。

### 7.4 前端测试模式

```typescript
// 组件测试
import { render, screen } from "@/test/render";

test("renders the component", async () => {
  render(<MyComponent />);
  expect(screen.getByText("Hello")).toBeInTheDocument();
});

// Store/逻辑测试
import { foldEvent } from "@/lib/runtime";

test("folds a text event into the thread", () => {
  const result = foldEvent(thread, { type: "text.updated", ... });
  expect(result[0]).toMatchObject({ kind: "agent", markdown: "..." });
});
```

---

## 8. 关键模式与反模式

### 8.1 正确模式 ✅

1. **通过 SDK 通信**：始终通过 `OpenCodeClient`/`AgentRuntime` 接口与 runtime 交互，绝不直接调用 OpenCode HTTP API。
2. **状态选择器**：Zustand store 使用选择器 `useRuntimeStore(s => s.xxx)`，而非解构整个 store。
3. **React.memo**：对于在流式更新期间频繁重渲染的线程块组件，使用 `React.memo`。
4. **平台守卫**：使用 `isTauri`、`isGatewayWeb` 守卫平台特定代码。
5. **增量变更**：每次 PR 应该是可验证的最小变更集。
6. **`import type`**：仅用作类型的导入使用 `import type`。
7. **保持文档最小化**：不要随意新增 .md 文件；优先更新现有文档。

### 8.2 错误模式 ❌

1. **❌ 直接从 UI 调用 `fetch('http://127.0.0.1:4096/...')`**：必须通过 SDK。
2. **❌ 使用 `useRuntimeStore()` 无选择器**：会导致每次 store 更新都重渲染。
3. **❌ 在浏览器 dev 模式下期望 Tauri 功能可用**：始终检查 `isTauri`。
4. **❌ 硬编码颜色/调色板值**：使用 Tailwind 类或 `@jingming/shared` 的调色板。
5. **❌ 将推测当作事实陈述**：所有结论必须与代码或数据绑定。
6. **❌ 向 workspace 的 git 设置 remote 或 push**：绝不做。

---

## 9. 重要约束与护栏

### 9.1 安全约束（不可协商）

- Agent 只能访问当前工作区。
- 命令执行、文件删除、依赖安装和远程连接需要用户批准（默认手动批准模式——绝不默认 `off`）。
- API 密钥存储在 OS 密钥链/凭据管理器中；绝不进入 provenance、日志、崩溃报告、git 或导出项目。
- 新会话工作区是本地 git 仓库：应用初始化它们并在文件变更后进行 best-effort 本地提交。**绝不设置 remote 或 push**。

### 9.2 架构护栏

- UI **绝不**直接调用 OpenCode——必须通过 `packages/sdk`（`OpenCodeClient`）。
- **固定 OpenCode 版本**（`OPENCODE_VERSION`）并将其作为 sidecar 捆绑。
- 保持前端、桌面壳和 agent runtime **解耦**。
- Skills、MCP 服务器和模型提供者必须保持**可插拔**。
- Artifact schema 和 workflow 模板必须保持**稳定和版本化**。
- 每个功能必须在 Windows、macOS 和 Linux 上运行，**并且**在 gateway web 客户端中可用——包括手机宽度视口。如果某个功能在 Web 上根本不可用，用 `isGatewayWeb` 隐藏它。

### 9.3 设计原则

保持 **简单、明确、清晰、完整**。

- **简单** — 不过度设计；不必要的实体就不要添加。
- **明确** — 没有歧义；没有 bug。
- **清晰** — 一眼就能理解。
- **完整** — 覆盖关键点；安全优先。

---

## 10. 关键文件速查表

| 文件 | 用途 | 重要度 |
| --- | --- | --- |
| `apps/desktop/src/lib/runtime.ts` | **核心 store**：状态管理、事件折叠、线程构建 | ⭐⭐⭐⭐⭐ |
| `packages/sdk/src/OpenCodeClient.ts` | **SDK 实现**：HTTP+SSE 通信、事件归一化 | ⭐⭐⭐⭐⭐ |
| `packages/sdk/src/types.ts` | **事件类型定义**：OpenCodeEvent 等 | ⭐⭐⭐⭐ |
| `packages/sdk/src/runtime.ts` | **AgentRuntime 接口**：运行时无关的抽象 | ⭐⭐⭐⭐ |
| `packages/shared/src/index.ts` | **共享类型**：ThreadBlock、ChartPalette 等 | ⭐⭐⭐⭐ |
| `apps/desktop/src-tauri/src/runtime.rs` | **Rust 后端核心**：sidecar 管理、配置、代理 | ⭐⭐⭐⭐⭐ |
| `apps/desktop/src-tauri/src/gateway.rs` | **Remote Access 网关**：HTTP API、Web 客户端服务 | ⭐⭐⭐⭐ |
| `apps/desktop/src-tauri/src/lib.rs` | **Tauri 入口**：注册所有 commands、插件、状态 | ⭐⭐⭐⭐ |
| `apps/desktop/src/lib/tauri.ts` | **Tauri 桥接层**：前端调用的所有 Rust commands | ⭐⭐⭐⭐ |
| `apps/desktop/src/lib/webMode.ts` | **Web 模式守卫**：isGatewayWeb、token 管理 | ⭐⭐⭐ |
| `apps/desktop/src/lib/artifactFile.ts` | **文件操作**：读取、预览、列表 | ⭐⭐⭐ |
| `apps/desktop/src/app/router.tsx` | **路由定义**：所有页面路由 | ⭐⭐⭐ |
| `apps/desktop/src/i18n/config.ts` | **i18n 配置**：支持的语言、检测逻辑 | ⭐⭐⭐ |
| `docs/TECHNICAL_DESIGN.md` | **技术设计**：架构决策、技术选型理由 | ⭐⭐⭐⭐ |
| `docs/PRD.md` | **产品需求**：功能范围、路线图 | ⭐⭐⭐⭐ |
| `docs/rfc/agent-runtime.md` | **AgentRuntime RFC**：接口设计原理 | ⭐⭐⭐ |
| `docs/rfc/remote-access-gateway.md` | **Gateway RFC**：远程访问网关设计 | ⭐⭐⭐ |
| `apps/desktop/src-tauri/tauri.conf.json` | **Tauri 配置**：窗口、sidecar、资源、图标 | ⭐⭐⭐ |
| `apps/desktop/vite.config.ts` | **Vite 配置**：别名、测试、开发服务器 | ⭐⭐⭐ |
| `PROGRESS.md` | **进度记录**：唯一的实现日志 | ⭐⭐⭐ |

---

## 11. 常见陷阱与注意事项

1. **SSE 事件流的自愈机制**：`OpenCodeClient` 在连接断开时会自动重连（最多 8 次），但 `close()` 会取消自愈。切换模型时需要特别小心（见 `setDefaultModel` 的注释）。

2. **模型切换延迟**：`setDefaultModel` 是非阻塞的——server 在后台重建实例（~1s）。在重建完成之前查询 provider 列表可能返回旧数据。

3. **事件流的渲染风暴**（已修复 #34）：始终使用 Zustand 选择器 + `React.memo` 避免 O(N·M) 的重渲染。

4. **Windows GUI PATH 问题**：GUI 应用继承的 PATH 不包含 conda/Python。Rust 侧通过 `enriched_path()` 预置这些路径。

5. **Windows 子进程控制台窗口**：使用 `quiet_command()` 而不是 `std::process::Command::new()`，避免每个子进程弹出黑色控制台窗口。

6. **macOS 窗口交通灯按钮**：透明/磨砂窗口的交通灯按钮在某些机器上会错位。需要在 `Focused`、`Resized` 和 `ThemeChanged` 事件上重新定位。

7. **拖放文件重复问题**（已修复 #44）：Composer 的 `onDragDropEvent` 不能以 `[onSend]` 作为依赖，因为 `onSend` 每次渲染都会创建新函数。改为用 `onDropRef` + 空依赖数组。

8. **自定义 endpoint 的 context 窗口**：不要猜测 context 窗口大小。值为 0 意味着让 OpenCode 跳过溢出计算。已知值来自 probe 或用户手动输入。

9. **Gateway Web 模式下的 API 密钥安全性**：`/global/config` 的 GET 会递归抹除所有敏感字段。Gateway 永远不代理密钥写入请求。

10. **不要对 workspace git 设置 remote**：代码中有 best-effort 本地提交（`refs/jingming-yanhuan/snapshots/*`），但绝不配置 remote 或 push。

---

## 12. 当前开发优先级（v0.3.0 → v0.5.0）

根据 `docs/PRD.md` §9 路线图：

- **v0.3.0 研究 UX**：LaTeX/数学渲染、图片上传→多模态提示、计划优先工作流、自适应批准、系统通知。
- **v0.4.0 可达性与互操作**（北向）：基于 `AgentRuntime` 的统一 API Gateway → LAN Web UI / CLI / 云隧道 / 消息集成 / ACP 服务器。
- **v0.5.0 可插拔与远程运行时**（南向）：远程 agent 运行时、ACP 客户端、远程 Jupyter。

---

## 13. 附录：术语对照

| 术语 | 说明 |
| --- | --- |
| **Agent Runtime** | 实际执行 AI agent 的运行时环境（当前为 OpenCode） |
| **Sidecar** | 与主应用捆绑并受其管理的独立二进制文件 |
| **OpenCodeClient** | `packages/sdk` 中封装 HTTP+SSE 通信的类 |
| **AgentRuntime** | `packages/sdk` 中定义的运行时无关接口 |
| **Gateway** | Remote Access 网关，提供经过认证的 HTTP API |
| **Provenance** | 溯源记录，追踪每个工件的生成来源 |
| **Thread Block** | 对话线程中的一块渲染单元（消息、工具调用、审查卡片等） |
| **foldEvent** | 将 SSE 事件合并到线程状态的核心函数 |
| **Skill** | 可复用的 agent 能力包（Markdown 格式，包含提示词和脚本） |
| **MCP** | Model Context Protocol，用于连接外部工具和数据源 |
| **Web 模式** | Gateway 服务的 Web 客户端模式（`isGatewayWeb === true`） |
| **Tauri 模式** | 原生桌面应用模式（`isTauri === true`） |
