# 长安启源车机 · 工程模式与 ADB / USB 模式切换

> 记录长安启源车机（C589 PHEV / 启源 OS / Android 9）上，"工程模式"里的
> **U 盘模式 ⇄ ADB 模式**切换到底是怎么实现的，以及第三方应用有哪些可行路径。
>
> **适用版本**：启源 OS（Android 9 / API 28），2026-08 实车验证。
> 其他年款、配置或 OTA 版本可能不同，请以你的车为准。

---

## 一句话结论

车机上的"工程模式"不是 MTK 的 EngineerMode，而是长安自研的 **TSP Factory**。
它的 USB 切换最终落到一条 **MCU 厂商属性**（`ID_MCU_USB_MODE_SELECT = 557921325`），
而不是常见的 `sys.usb.config` 或 `Settings.Global.adb_enabled`。
第三方应用想做到同样的事，需要跨过 CarService 的入口校验；本仓库记录了这个校验的
机制、三条候选路径，以及实车验证的结果。

**本仓库只讲机制与验证结论，不提供可直接运行的绕过工具，也不包含任何口令、PIN、
证书或白名单具体值。**

---

## 三条路径速览

| 路径 | 做法 | 结果 | 风险 |
|---|---|---|---|
| A. `Settings.Global` | 写 `adb_enabled` / `usb_mass_storage_enabled` | 开发者选项同款机制；在本车 TSP Factory 的 USB 切换场景下**实测不生效**（无监听者） | 🟢 低 |
| B. MCU 属性直写 | 通过 CarService 写 `557921325`，值 1=ADB / 2=U 盘 | 与 TSP Factory 同款；需要跨过 CarService 入口校验 | 🟠 中 |
| C. 界面自动化 | 拉起 TSP Factory，输 PIN，点按钮 | **实车判死**：切换前有二级认证（绑定手机号），自动化过不去 | 🟡 中 |

详细拆解：[docs/01-原理.md](docs/01-原理.md) ·
验证过程：[docs/02-验证.md](docs/02-验证.md) ·
风险与恢复：[docs/03-风险与恢复.md](docs/03-风险与恢复.md)

---

## 这套机制里最值得记住的三点

1. **权限跟着进程域走，不跟代码走**。MTK EngineerMode 能写 `sys.usb.config`，
   是因为它运行在 radio/platform 域并有 `set_prop` 权限；把同样的代码抄进普通应用
   并不会获得同样的权限。
2. **长安 TSP Factory 的两道门是独立的**。PIN 门在界面上，二级认证只挡 UI 操作，
   不挡底层属性写入——这是"界面能挡住、属性写不挡"的根源。
3. **CarService 的入口校验只看进程名**。这个结论决定了路径 B 是否可行；具体校验逻辑
   与影响面见 [docs/01-原理.md](docs/01-原理.md) 第 3 节。

---

## 仓库结构

```
qiyuan-adb-switch/
├── README.md               ← 你在这里
├── docs/
│   ├── 01-原理.md           两个工程模式、PIN/二级认证、USB 切换的真实落点
│   ├── 02-验证.md           失败路径、成功路径、实车记录与证据形式
│   └── 03-风险与恢复.md     切错模式怎么恢复、权限与保修风险
├── DISCLAIMER.md
├── SECURITY.md
├── LICENSE
└── .gitignore
```

---

## 适合谁看

- 想搞清楚"为什么网上抄的 `settings put global adb_enabled 1` 在我车上没用"的车友；
- 在做车机工具、需要理解 CarService 入口校验的开发者；
- 想评估"开 ADB 会不会影响保修/安全"的车主。

如果你只是想临时开 ADB，先看 [docs/03-风险与恢复.md](docs/03-风险与恢复.md) 的
"最小风险做法"一节，不要直接照搬路径 B。

---

## 免责声明（摘要）

- 仅在你拥有或获明确授权的车辆上操作；
- 切换 USB 模式可能导致 ADB 断开、U 盘识别异常，需按文档恢复；
- 修改系统设置、进程名或车辆属性可能影响保修、OTA 与系统稳定性；
- 作者不对任何损失负责。完整条款见 [DISCLAIMER.md](DISCLAIMER.md)。

## 许可证

- 文档：CC BY-NC-SA 4.0（见 [LICENSE](LICENSE) 顶部说明）
- 示例代码：MIT

> 文中提及的第三方应用、商标与协议归各自权利人所有。本仓库仅做技术分析，
> 不包含、也不分发任何第三方 APK、固件或私钥。