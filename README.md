# edunet-cli

一个面向锐捷 ePortal 校园网的命令行工具，支持登录、登出、网络状态检查和门户诊断。使用 **Typer + Rich + HTTPX**，通过 **uv** 管理依赖与运行环境。

**测试环境：黄淮学院校园网**，默认门户为 `http://10.100.200.3`。项目基于该校园网的登录抓包、成功认证响应和门户网页算法实现，**不是所有锐捷部署的通用客户端**。目前已完成离线协议测试，尚未使用真实账号完成新 CLI 的端到端验证。

## 快速开始

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)。在克隆或下载后的项目目录运行：

```sh
uv sync --locked
uv run edunet --help
uv run edunet login
```

连接校园网后，`login` 会提示输入账号与密码，密码隐藏输入。外网探测通过时直接退出，不重复提交认证。

也可以将当前项目安装为独立命令：

```sh
uv tool install .
edunet --version
edunet login
```

更新本地安装：`uv tool install --force .`。本项目尚未发布到 PyPI，上面的安装命令使用当前目录。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `uv run edunet login` | 登录；缺少凭据时交互输入 |
| `uv run edunet logout` | 登出当前会话，无需重新输入密码 |
| `uv run edunet status` | 检测是否能访问返回空 204 的探测地址 |
| `uv run edunet status --portal` | 同时检查校园网门户是否可达 |
| `uv run edunet doctor` | 获取当前登录参数并检查 RSA 公钥，不提交凭据 |
| `uv run edunet --version` | 显示版本 |
| `uv run edunet login --help` | 查看子命令选项 |

### 登录地址无法自动发现

打开浏览器的校园网登录页，复制地址栏**包含问号后参数的完整地址**：

```sh
uv run edunet login --portal-url "http://10.100.200.3/eportal/index.jsp?填写当前完整参数"
```

相同选项也适用于 `doctor`。示例是占位说明，不能直接执行。脚本不会复用旧抓包的 IP、MAC 或会话值。

### 登出会话无法自动发现

打开校园网当前登录成功页，复制其完整地址：

```sh
uv run edunet logout --success-url "http://10.100.200.3/eportal/success.jsp?userIndex=填写当前会话值"
```

自动发现会话不依赖本地缓存；本工具不将 `userIndex` 写入磁盘。如果门户无法自动找回会话，需使用该选项。成功页地址包含会话凭据，不要在 issue、截图或公开日志中贴出真实值。

### 自动化与凭据

支持以下环境变量，不会自动读取 `.env` 文件：

| 环境变量 | 默认值 / 用途 |
| --- | --- |
| `EDUNET_USERNAME` | 登录账号 |
| `EDUNET_PASSWORD` | 登录密码；没有 `--password` 参数 |
| `EDUNET_SERVICE` | 空字符串，与当前门户的请求一致 |
| `EDUNET_SERVER` | `http://10.100.200.3` |
| `EDUNET_PROBE_URL` | `http://connectivitycheck.gstatic.com/generate_204` |
| `EDUNET_TIMEOUT` | `8` 秒，每次网络请求的超时 |
| `NO_COLOR` | 设置后禁用彩色输出 |

由任务运行环境或秘密管理器提供账号、密码后：

```sh
uv run edunet --json login --no-input
```

也可让秘密管理器通过管道提供一行密码，运行 `edunet login -u YOUR_USERNAME --password-stdin`。标准输入密码优先于 `EDUNET_PASSWORD`。避免把真实密码作为命令参数或写入 shell 历史。

`--json`、`--no-input` 或非交互终端均不会提示输入凭据。密码缺失时退出，不无限等待。`login --force` 可在探测已通过时仍提交一次登录，通常不需要。

### 门户、探测地址与超时

全局选项必须放在子命令**前面**：

```sh
uv run edunet --server http://10.100.200.3 --timeout 5 status
uv run edunet --probe-url http://conn1.oppomobile.com/generate_204 status
uv run edunet --no-color doctor
```

探测 URL 必须是 HTTP(S) 地址，预期响应为 `204` 且内容为空。可按所在网络调整，但探测失败不能单独证明未登录。重定向不视为探测成功。修改 `--server` 只是修改目标，不保证兼容其他门户。

网络请求忽略环境代理，直接连接目标；每个 GET 最多处理 6 次响应以限制重定向循环。登录、登出 POST 不自动重试，也不跟随重定向。单次超时不是整条命令的总时限。

### JSON 输出和退出码

```sh
uv run edunet --json status
```

示例：

```json
{"ok": true, "event": "status", "message": "外网探测通过。", "online": true}
```

操作结果使用单个 JSON 对象输出到 stdout，不包含账号、密码、MAC、原始门户响应或会话标识。`ok` 表示本次操作的结果；登录响应的 `authenticated` 与 `online` 分别表示门户确认和外网探测状态。

| 退出码 | 含义 |
| --- | --- |
| `0` | 操作成功，或外网已通而跳过登录 |
| `1` | 网络、门户失败，或状态探测未通过 |
| `2` | 用法错误、参数或凭据缺失 |
| `3` | 门户已确认登录成功，但外网探测未通过；不应立即重试密码 |
| `130` | 操作被取消 |

参数解析错误（例如未知选项）由 Typer 输出到 stderr，仍可能是文本；`--help` 和 `--version` 也是文本。JSON 模式只约定有效命令的操作结果。

可使用 `uv run edunet --show-completion` 查看 shell 补全脚本，或 `--install-completion` 安装补全。若希望长期使用补全，先用 `uv tool install .` 安装命令。

## systemd 定时检测与自动登录（Linux）

附带用户级 [service](contrib/systemd/edunet-check.service) 和 [timer](contrib/systemd/edunet-check.timer)。默认每两分钟运行一次 `login --no-input --require-portal`，附加最多 10 秒随机延迟：

1. 外网探测通过：直接结束，不提交登录。
2. 外网探测失败、校园网门户不可达：跳过登录，记录失败。
3. 外网探测失败、门户可达：读取配置凭据，获取当前参数，提交一次登录。
4. 门户确认成功后最多做三次外网探测；结果写入 journal。

每轮只提交一次登录，失败后等待下一次 timer，不在进程内重试密码。若密码错误，后续轮次仍会尝试，请及时停用 timer 并修正凭据。外网探测站点自身故障也可能触发登录，可按实际网络更换探测地址。

### 安装与配置

在项目目录执行（已有安装先运行 `uv tool install --force .`）：

```sh
uv tool install .
mkdir -p ~/.config/edunet ~/.config/systemd/user
(umask 077; cp -i contrib/systemd/check.env.example ~/.config/edunet/check.env)
chmod 600 ~/.config/edunet/check.env
```

编辑 `~/.config/edunet/check.env`，填写 `EDUNET_USERNAME` 和 `EDUNET_PASSWORD`，保留实际门户与探测地址。该文件使用 systemd `EnvironmentFile` 语法，不写 `export`；含空格的值需要引号。文件包含明文凭据，请勿提交到仓库或公开分享。

然后安装并启动：

```sh
cp contrib/systemd/edunet-check.service contrib/systemd/edunet-check.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now edunet-check.timer
```

配置文件缺失时 service 不启动；凭据为空时，离线状态下 CLI 返回 `2`，不进入交互。service 默认执行 `~/.local/bin/edunet`。如使用自定义 uv 安装目录，用 `uv tool dir --bin` 检查路径并修改 `ExecStart`。任务运行时不调用 uv，也不下载依赖。

### 查看状态与日志

```sh
systemctl --user list-timers edunet-check.timer
systemctl --user start edunet-check.service
journalctl --user -u edunet-check.service -n 30 --no-pager
```

成功结束后 oneshot service 显示 `inactive (dead)` 正常；timer 应为 `active (waiting)`。失败后 timer 继续安排下一轮。退出码 `3` 表示门户已确认成功但外网探测未通过，日志会明确区分。日志不含密码或会话值，也不会主动发送邮件通知。

每次 HTTP 请求超时为 8 秒，整轮 service 最长 4 分钟，用于容纳多次参数发现请求与探测。上一轮仍在运行时 systemd 不会并发启动同一个 service。用户手动执行的其他 CLI 进程不受此限制。

### 调整与停用

修改 `check.env` 后下次执行生效。要改为每五分钟执行，运行 `systemctl --user edit edunet-check.timer`，填写：

```ini
[Timer]
OnUnitActiveSec=
OnUnitActiveSec=5min
```

然后运行 `systemctl --user daemon-reload` 和 `systemctl --user restart edunet-check.timer`。启动检查以用户 systemd 管理器启动时间为基准，若已超过 30 秒，启用时可立即执行。默认随用户会话运行；若需要退出用户会话后继续运行，可自行执行 `loginctl enable-linger "$USER"`，系统可能要求管理员权限。定时语义见 [systemd.timer 官方文档](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)。

停止自动登录：

```sh
systemctl --user disable --now edunet-check.timer
systemctl --user stop edunet-check.service
```

**手动登出前请先停用 timer，否则下一轮可能自动重新登录。** 仓库只附带配置，安装 Python 包不会自动启用服务。

## 协议与兼容范围

1. 从门户重定向或 HTML 中提取当前 `/eportal/index.jsp` 的网络参数。
2. 调用 `InterFace.do?method=pageInfo` 获取 RSA 公钥。
3. 将密码、`>` 和当前 `mac` 拼接，按照门户 RSAUtils 的反转、零填充、小端分块算法加密。
4. 按观察到的请求进行双重 URL 编码，并向 `InterFace.do?method=login` 提交 `passwordEncrypt=true`。
5. 仅将 `result=success` 视为门户确认成功；随后最多做三次外网探测。
6. 登出使用 `InterFace.do?method=logout` 和当前成功页的 `userIndex`。

页面配置曾返回 `passwordEncrypt=false`，但实际成功请求为 `true`；此客户端固定采用已观察到的加密方式。服务字段默认为空。已观察到的保活间隔为 `0`，当前不发送协议保活请求；可选 systemd timer 提供周期性检查与离线登录，不自动安装或启用任务。

目前仅支持 ASCII 密码（英文、数字、半角符号）；用户名可包含中文。验证码、短信认证、运营商独立密码、CAS/统一认证和其他 RSA 变体尚不支持。检测到验证码要求时会停止；门户变化可能需要重新适配。

这里的 RSA 是旧门户协议的兼容实现，不是通用密码学组件；不能直接替换为现代 RSA-OAEP，否则无法与网页协议匹配。默认门户使用 HTTP，密码字段加密不能代替 TLS 对服务器的认证，也不能防止会话信息被窃听。

## 开发与检查

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=edunet_cli --cov-report=term-missing
uv build
```

测试使用 HTTPX `MockTransport`，禁止实际网络请求。RSA 固定测试向量由门户 JavaScript 对**合成模数和测试字符串**生成；仓库不包含门户 JS、原始抓包或真实凭据。

```text
src/edunet_cli/
  cli.py       # Typer / Rich 交互与 JSON 输出
  client.py    # HTTPX、参数发现、认证协议
  crypto.py    # 门户 RSA 兼容实现
  errors.py    # 可安全展示的错误
tests/         # 协议、CLI、加密兼容性测试
.github/workflows/ci.yml
pyproject.toml
uv.lock
```

CI 配置覆盖 Ubuntu / Windows 和 Python 3.11 / 3.13，检查格式、类型、测试和包构建。本地结果不等同于 CI 已在全部平台运行。依赖版本锁定在 `uv.lock`。

## 贡献与许可

提交方式见 [CONTRIBUTING.md](CONTRIBUTING.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。提交问题时请提供系统、版本、命令结构和脱敏错误；不要上传完整抓包、密码或真实登录地址。

项目代码使用 [MIT License](LICENSE)。本实现未复制用户提供的 GPL Shell 脚本或门户 JavaScript 源码。若后续引入第三方代码，请单独核对并保留其许可要求。
