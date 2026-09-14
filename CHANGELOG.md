# Changelog

## Unreleased

- systemd 定时任务改为外网探测失败且门户可达时自动登录，每轮最多提交一次。
- 添加 `login --require-portal`、必需凭据配置与安装说明。

## 0.1.0

- 将单文件脚本整理为可安装的 uv 项目，命令名为 `edunet`。
- 添加 `login`、`logout`、`status`、`doctor` 子命令。
- 支持隐藏密码输入、环境变量、标准输入密码、JSON 输出和无交互模式。
- 使用 HTTPX 管理请求与内存 Cookie，限制 GET 重定向，禁止 POST 自动重试及重定向。
- 添加 `status --portal` 和用户级 systemd 检测 service/timer，默认每两分钟检查门户及外网。
- 加入模拟协议测试、RSA 固定向量、格式检查、类型检查和 GitHub Actions 配置。

迁移：旧 `--logout` 改为 `logout`，`--check` 改为 `status`，`--diagnose` 改为 `doctor`。
旧脚本“门户成功但外网未通”的退出码从 `2` 调整为 `3`，`2` 统一表示用法或输入错误。
