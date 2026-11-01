# 示例代码

> 本目录只包含**脱敏后的教学示例**，用于复现
> [01-首次开启-工程模式与认证](../docs/01-首次开启-工程模式与认证.md) 中的流程。
>
> 仅在你拥有或获明确授权的车辆上使用。不要分发、不要商用。

## 文件

| 文件 | 说明 |
|---|---|
| `fake_tlc_server.py` | 本地模拟认证服务：写 hosts / 迷你 DNS / 自签 HTTPS，三个接口返回成功 |
| `gen_cert.sh` | 生成 `server.crt` / `server.key`（自签，CN 为目标域名） |
| `server.crt` / `server.key` | **不随仓库提供**，由 `gen_cert.sh` 生成 |
| `fake_tlc_server.log` | 运行时生成，已被 `.gitignore` 排除 |

## 快速开始

```bash
cd examples

# 1) 生成证书（只需一次）
bash gen_cert.sh

# 2) 以管理员身份启动（Windows 需要绑 443、写 hosts）
python fake_tlc_server.py

# 3) 车机连笔记本热点
# 4) 工程模式 -> 任意手机号 + 验证码 -> 登录
# 5) 点“切换为 ADB 模式”
# 6) 验证
adb devices
```

如果 hosts 方式不生效：

```bash
python fake_tlc_server.py --dns
```

如果只想自测服务是否正常（不涉及车机）：

```bash
python fake_tlc_server.py --test
```

退出时脚本会自动清理 hosts。如果异常退出导致 hosts 残留：

```bash
python fake_tlc_server.py --cleanup
```

## 脱敏说明

公开版相对原始工具做了这些处理：

| 项目 | 处理 |
|---|---|
| 真实 `appid` | 替换为 `YOUR_APPID`；假服务器不校验该字段 |
| 真实 VIN | 替换为 `TESTVIN0000000000` |
| 手机号 | 使用 `13800000000` 等示例值 |
| 签名 `sign` | 自测用固定假值；假服务器不校验 |
| 证书与私钥 | 不提供，需本地生成 |
| 请求日志 | 只记录手机号后四位 |

## 原理速览

```
车机 --连接热点--> 笔记本 192.168.137.1
                     ├─ hosts / DNS: spm.auto-pai.com -> 192.168.137.1
                     └─ HTTPS :443 (自签证书)
                           /tlc/auth/v1/sms       -> {"code":"0000"}
                           /tlc/auth/v1/login     -> {"code":"0000"}
                           /tlc/auth/v1/authQuery -> {"code":"0000"}
```

车机 App 信任所有证书，且只看响应里的 `code` 字段，所以固定 JSON 即可通过。

## 排错

| 现象 | 处理 |
|---|---|
| 绑 443 失败 | 用管理员终端运行 |
| 绑 53 失败 | 退出 Clash/VPN 等占用 53 的软件 |
| 车机登录失败 | 车机 Wi-Fi 断开重连、重启车机；或改用 `--dns` |
| 日志里没有请求 | 车机没走这个域名，或 DNS 仍指向真实服务器 |
| 登录成功但切换失败 | 确认点了“切换为 ADB 模式”；见 [04-验证记录](../docs/04-验证记录.md) |

## 安全提醒

- 脚本会临时修改 Windows hosts，请确保退出时正常清理；
- 不要在公共/公司网络运行；
- 不要把 `server.key`、日志或抓包原文提交到仓库；
- 这套方法绕过的是厂商认证设计，可能违反服务条款，风险自负。