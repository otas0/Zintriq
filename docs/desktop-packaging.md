# 桌面安装包 — Zintriq Editor

`appId`：`com.editor`。本机 Python 3.9–3.12。

## 创建虚拟环境

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd desktop && npm install && npm run dist
```

## 运行时

- 仅 `127.0.0.1`
- `ZINTRIQ_DESKTOP_TOKEN` 由 Electron 生成
- 工作区：`ZINTRIQ_WORKSPACE`（默认 `$ZINTRIQ_DATA_DIR/workspace`）

签名 / 公证：产品完成前默认关闭（`CSC_IDENTITY_AUTO_DISCOVERY=false`）。

旧产品树：`git checkout archive/pre-editor-pivot`。
