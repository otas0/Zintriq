# HAL Mapping Pack 示例

社区板文件放在 `fixtures/boards/`。本仓库额外提供：

| id | 名称 | 家族 |
| --- | --- | --- |
| esp32 | ESP32 DevKitC | esp32 |
| esp32-c3 | ESP32-C3 DevKit | esp32 |
| rp2040 | Raspberry Pi Pico | rp2040 |
| stm32 | STM32 Nucleo-F401RE | stm32 |
| stm32f103 | STM32F103 Blue Pill | stm32 |

贡献步骤：

1. 复制一份 YAML，改 `id` / `name` / `pins`。
2. `mcuFamily` 只能是 `esp32` | `stm32` | `rp2040`。
3. 运行 `pnpm --filter hal-registry test`。
4. 在 PR 描述里贴 `curl http://127.0.0.1:4317/boards` 的片段截图或文本。

发布日志中该类贡献归在 **硬件适配包** 标题下。
