# 02 · 进阶：APK 直接切换（不再走工程模式）

> 前提：你已经通过[路线一](01-首次开启-工程模式与认证.md)打开过 ADB。
>
> 目标：装一个自研 APK，以后在车机上点一下就能在 ADB / U 盘模式之间切换，
> 不用再开热点、跑假服务器、输 PIN。

---

## 1. 为什么需要 APK

路线一解决了"第一次"：

- 工程模式有 PIN + 二级认证；
- 普通应用直接写 USB 模式会被 CarService 拒绝；
- 所以第一次必须借工程模式的 UI 让车机自己切。

但每次车机重启、或切到 U 盘模式后，ADB 可能断开。如果每次都要重来一遍
工程模式流程，体验很差。

APK 的作用是：**利用已开启的 ADB 把应用装进去，之后由应用直接写 MCU 属性。**

---

## 2. 关键前提：通过 CarService 的入口校验

### 2.1 校验发生在哪里

普通应用调用：

```java
Car car = Car.createCar(context);
Object mgr = car.getCarManager("mcu");   // 或 Car.MCU_SERVICE
```

会先经过 CarService 的入口检查：

```
ICarImpl.getCarService
  → CarServiceUtils.isHaveSecurityPermission
    → 取 Binder 调用方 PID
    → 查 RunningAppProcessInfo.processName
    → 判断是否在硬编码列表里
```

不在列表里会抛：

```
SecurityException: <pkg> is not in white list!
```

### 2.2 校验的弱点

它查的是**进程名**，不是包名、UID 或签名。而 Android 允许应用在
`AndroidManifest.xml` 里用 `android:process` 指定进程名。

因此，一个能通过校验的应用需要：

1. 声明一个与白名单成员同名的进程；
2. 该进程名在当前车机上没有被其他应用占用（否则会冲突）；
3. 应用本身能装上（安装门另说）。

> 本仓库不提供具体的白名单进程名。你需要从自己的车机上查（只读命令见
> [04-验证记录.md](04-验证记录.md)），并自行确认风险。

### 2.3 进入之后的权限

通过入口后，属性读写层的检查在 2026-08 的固件上未实际拦截
（`assertPermission` 丢弃了 `checkCallingOrSelfPermission` 的返回值）。
所以应用能直接写 vendor 段属性。

**这不代表"应该写"**。`mcu` 下还有电源、驱动、灯光等属性，误写可能影响车辆功能。

---

## 3. 目标属性

```
CarMcuManager.ID_MCU_USB_MODE_SELECT = 557921325  (0x2141342D)
```

| 值 | 含义 |
|---|---|
| 1 | ADB 模式 |
| 2 | U 盘模式 |

调用形态（不同固件 API 名称可能不同）：

```java
// 示意：实际类型名请按你车机的 CarService 反编译结果调整
Object mcuMgr = car.getCarManager("mcu");
int[] params = {0, mode};          // {index, value}
// setIntVecProperty(557921325, params)
```

TSP Factory 内部走的就是这条路径，所以效果与工程模式按钮一致。

---

## 4. APK 设计要点

### 4.1 Manifest

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.usbmode">

    <!-- 占位：替换为你从自己车机查到的、未被占用的白名单进程名 -->
    <application
        android:process="<WHITELIST_PROCESS>"
        android:label="USB 模式切换">

        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
    </application>
</manifest>
```

要点：

- `android:process` 必须与目标白名单成员一致；
- 进程名冲突会导致应用起不来，先在车机上确认该名字未被使用；
- 不需要 `android.car.permission.*`（入口校验过了之后不检查）。

### 4.2 最小代码

```java
public class UsbMode {
    private static final int PROP_USB_MODE = 557921325;

    public static void switchMode(Context ctx, int mode) throws Exception {
        Car car = Car.createCar(ctx);
        car.connect();                       // 必须显式 connect
        try {
            Object mgr = car.getCarManager("mcu");
            if (mgr == null) throw new IllegalStateException("no mcu manager");

            // 不同固件可能是 setIntVecProperty / setProperty / 厂商 SDK
            java.lang.reflect.Method m = mgr.getClass().getMethod(
                    "setIntVecProperty", int.class, int[].class);
            m.invoke(mgr, PROP_USB_MODE, new int[]{0, mode});
        } finally {
            car.disconnect();
        }
    }
}
```

说明：

- 用反射是为了兼容不同固件的 API 名称；
- `car.connect()` 不能省，TSP Factory 也是 createCar 后显式 connect；
- 建议每次切换后读取一次状态或提示用户，避免"以为切了其实没切"。

### 4.3 UI 与开机自启

- 主界面放两个按钮：切 ADB / 切 U 盘；
- 切换前弹确认框，提示"切到 U 盘后 ADB 会断开"；
- 如果要做开机自启，注意：ADB 关闭时应用仍能运行，但 U 盘模式下 adb 不可用，
  这属于预期行为；
- 不要做"静默定时切换"，避免在 OTA 或诊断时误切。

### 4.4 安装方式

ADB 已开启时：

```bash
adb install -r usbmode.apk
```

如果安装被拒绝，属于"安装门"问题（签名/白名单），不在本文范围。
查看拒绝原因：

```bash
adb install -r usbmode.apk 2>&1
```

---

## 5. 完整流程回顾

```
第一次：
  工程模式 → 假认证服务器 → 切换为 ADB → adb devices 可见
      ↓
  adb install usbmode.apk
      ↓
以后：
  打开 usbmode → 点"ADB"/"U盘" → 直接写 557921325
```

---

## 6. 限制

| 限制 | 说明 |
|---|---|
| 进程名冲突 | 白名单进程名被占用时应用无法启动 |
| 固件差异 | 属性 ID 与 API 名称可能随 OTA 变化 |
| 权限边界 | 入口校验可能在新版本修复 |
| U 盘模式 | 切过去后 adb 断开，恢复方法见 [03-风险与恢复.md](03-风险与恢复.md) |
| 保修 | 修改系统级属性可能影响保修与 OTA |

---

## 7. 不应该做的事

- ❌ 不要在 APK 里批量写其他车辆属性；
- ❌ 不要把白名单进程名硬编码进公开仓库；
- ❌ 不要做成"一键开启 ADB"并公开分发——不同车型/版本风险不可控；
- ❌ 不要在 U 盘模式下尝试 OTA。

---

回到：[README.md](../README.md) · [01-首次开启](01-首次开启-工程模式与认证.md) ·
[03-风险与恢复](03-风险与恢复.md) · [04-验证记录](04-验证记录.md)