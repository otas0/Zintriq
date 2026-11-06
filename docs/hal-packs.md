# HAL Mapping Pack 示例

社区板文件放在 `fixtures/boards/`。本仓库额外提供：

| id | 名称 | 家族 |
| --- | --- | --- |
| esp32 | ESP32 DevKitC | esp32 |
| esp32-c3 | ESP32-C3 DevKit | esp32 |
| rp2040 | Raspberry Pi Pico | rp2040 |
| stm32 | STM32 Nucleo-F401RE | stm32 |
| stm32f103 | STM32F103 Blue Pill | stm32 |

## 贡献模板（YAML）

复制下列骨架到 `fixtures/boards/<id>.yaml`：

```yaml
id: my-board
name: My Board Name
mcuFamily: esp32 # esp32 | stm32 | rp2040
toolchain:
  compiler: xtensa-esp32-elf-g++
  flags: ["-std=c++17"]
pins:
  LED: GPIO2
  BTN: GPIO0
peripherals:
  - name: uart0
    kind: uart
    pins: [BTN]
```

机器校验：对照 `fixtures/boards/board.schema.json`，并跑 `pnpm --filter @zintriq/hal-registry test`（含全部 YAML 的 Zod 校验）。

## 截图 / curl 检查清单（PR 必贴）

合并前在本地 core-service 跑通，并在 PR 里贴输出或截图：

```bash
# 1. 启动
corepack pnpm --filter core-service dev

# 2. 确认新板出现
curl -s http://127.0.0.1:4317/boards | python3 -m json.tool | grep -A2 '"id": "my-board"'

# 3. 用新板做一次合法构建
curl -s -X POST http://127.0.0.1:4317/build \
  -H 'content-type: application/json' \
  -d '{"boardId":"my-board","entryFile":"main.cpp","files":[{"path":"main.cpp","content":"int main(){return 0;}\n"}]}'
```

勾选项：

- [ ] `mcuFamily` 仅为 `esp32` | `stm32` | `rp2040`
- [ ] `id` 全局唯一，文件名与 `id` 一致
- [ ] `pnpm --filter @zintriq/hal-registry test` 通过
- [ ] `GET /boards` 输出含新板（文本或截图）
- [ ] `POST /build` 用新 `boardId` 返回 `success` 或可解释的本地编译器错误（非 `BOARD_NOT_FOUND`）
- [ ] PR 描述归在 **硬件适配包** 标题下

发布日志中该类贡献归在 **硬件适配包** 标题下。
