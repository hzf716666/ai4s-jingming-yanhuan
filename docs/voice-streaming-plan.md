# 语音流式输入实现计划

## Context

用户希望语音输入时能实时显示识别结果（说一个字显示一个字），而不是等到整个语音说完后才显示。

### 当前实现分析

| 组件 | 实现方式 | 流式支持 |
|------|----------|----------|
| Web Speech API (`useWebSpeechRecorder.ts`) | `interimResults = true` | ✅ 真流式 |
| whisper.cpp 后端 (`useVoiceRecorder.ts`) | 每 500ms 截断音频发送 | ❌ 伪流式 |
| Rust sherpa-onnx (`voice_stream.rs`) | stub 实现（仅累积样本） | ❌ 未实现 |

## 实现方案

### Phase 1: 完成 Rust sherpa-onnx 流式识别 (主要工作)

**目标文件:**
- `apps/desktop/src-tauri/src/voice_stream.rs`
- `apps/desktop/src-tauri/src/lib.rs`
- `apps/desktop/src-tauri/Cargo.toml`

**架构:**
```
Frontend → accept_audio_chunk → sherpa-onnx OnlineRecognizer → emit "voice-stream:partial" → Frontend
```

**实现步骤:**

1. **添加依赖** (`Cargo.toml`):
   ```toml
   sherpa-onnx = "1"
   uuid = { version = "1", features = ["v4"] }
   ```

2. **重构数据结构:**
   ```rust
   struct StreamingVoiceInner {
       model_size: Option<String>,
       sessions: HashMap<String, SessionHandle>,  // 每个session独立recognizer
   }

   struct SessionHandle {
       recognizer: sherpa_onnx::OnlineRecognizer,
       stream: sherpa_onnx::OnlineStream,
       sample_rate: i32,
       start_time: Instant,
   }
   ```

3. **实现命令:**
   - `start_streaming_session`: 创建 OnlineRecognizer + OnlineStream，返回 session_id 和 sample_rate
   - `accept_audio_chunk`: 喂入音频 → decode() → emit "voice-stream:partial"
   - `get_streaming_partial`: 返回当前累计文本
   - `end_streaming_session`: 最终decode → emit "voice-stream:final" → 返回完整文本
   - `cancel_streaming_session`: 清理session

4. **更新 lib.rs**: 注册 voice_stream 模块和命令

### Phase 2: 修改 useVoiceRecorder.ts 使用真流式

**目标文件:** `apps/desktop/src/components/voice/useVoiceRecorder.ts`

**改动:**
- 移除 whisper.cpp 批量转写相关代码
- 使用 `ScriptProcessorNode` 捕获原始音频样本 (4096 samples ≈ 256ms per chunk)
- 通过 `acceptAudioChunk` 直接发送音频到 sherpa-onnx
- 监听 `voice-stream:partial` 事件实时更新文本
- 使用 `endStreamingSession` 获取最终文本

### Phase 3: 修复 Web Speech API 流式配置

**目标文件:** `apps/desktop/src/components/voice/useWebSpeechRecorder.ts`

**问题:** 原实现 interim 结果没有实时调用 `onPartial`

**修复:**
- 确认 `interimResults = true`
- 在 interim 结果到达时立即调用 `onPartial`
- 使用 `optionsRef` 避免 stale closure

### Composer.tsx 无需修改

`onPartial` 回调已正确实现流式更新。

## 关键文件

| 文件 | 修改类型 |
|------|----------|
| `apps/desktop/src-tauri/Cargo.toml` | ✅ 添加 sherpa-onnx, uuid 依赖 |
| `apps/desktop/src-tauri/src/voice_stream.rs` | ✅ 完成 sherpa-onnx 流式识别 |
| `apps/desktop/src-tauri/src/lib.rs` | ✅ 注册 voice_stream 命令 |
| `apps/desktop/src/components/voice/useVoiceRecorder.ts` | ✅ 改用 streaming session |
| `apps/desktop/src/components/voice/useWebSpeechRecorder.ts` | ✅ 修复流式逻辑 |
| `apps/desktop/src/lib/tauri.ts` | ✅ 添加 streaming voice APIs |

## API 设计

### Tauri Commands

```rust
// 开始流式会话
start_streaming_session() -> { session_id: String, sample_rate: i32 }

// 发送音频 chunk (16kHz mono f32 [-1,1])
accept_audio_chunk(session_id: String, samples: Vec<f32>) -> ()

// 获取当前部分结果
get_streaming_partial(session_id: String) -> String

// 结束会话，获取最终文本
end_streaming_session(session_id: String) -> String

// 取消会话
cancel_streaming_session(session_id: String) -> ()
```

### Events

| 事件名 | 触发时机 | Payload |
|--------|----------|---------|
| `voice-stream:started` | session 创建成功 | `{ sessionId: string }` |
| `voice-stream:partial` | 每 chunk 解码后 | `{ sessionId, text, elapsedMs }` |
| `voice-stream:final` | session 结束 | `{ sessionId, text, elapsedMs }` |
| `voice-stream:cancelled` | session 取消 | `{ sessionId }` |

## 验证方式

1. 启动桌面应用，按住语音按钮说话
2. 观察输入框是否实时显示识别文字（边说边显示）
3. 测试两个后端: Tauri (sherpa-onnx streaming) 和 Web Speech

## 已知问题

- ScriptProcessorNode 在某些浏览器中被标记为 deprecated，但仍是广泛支持的方式
- 首次编译 sherpa-onnx 需要较长时间（下载和编译 ONNX runtime）
