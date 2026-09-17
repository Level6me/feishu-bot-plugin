# FoloToy AI Passport (ESP32-C3) 嵌入式固件工程

本工程为 **FoloToy AI Passport** 专用定制固件，严格对齐官方开发规范与硬件抽象层事实来源（[`components/bsp/include/bsp_pins.h`](https://github.com/FoloToy/ai-passport/blob/main/components/bsp/include/bsp_pins.h)），用于与局域网内的 **Antigravity 飞书机器人 (`antigravity-feishu-bot`)** 实现软硬件全双工协同联动。

---

## 硬件外设与引脚分配（对齐官方 BSP 单一事实来源）

| 外设模块 | 核心芯片 / 方案 | ESP32-C3 引脚 | 电气特性与工作规范 |
| :--- | :--- | :--- | :--- |
| **彩色显示屏** | ST7789P3 (240×320) | MOSI:`9`, SCLK:`8`, CS:`1`, DC:`20`, RST:`-1`, BL:`21` | SPI2 40MHz 高速驱动，RST 硬接 3.3V 走 SWRESET 软复位，强制反色 (INVON) |
| **实体交互按键** | 3 键共用单个 ADC | **GPIO 0** (ADC1_CH0) | 板载 10k 外部上拉，电阻分压识别：<br>• **上键** (0Ω): `0 ~ 150 mV`<br>• **下键** (1kΩ): `150 ~ 447 mV`<br>• **确定键** (2.2kΩ): `447 ~ 1900 mV`<br>• **松开态**: `3300 mV` |
| **I2C 控制总线** | ES8311 + CW2017 | SDA:`10`, SCL:`7` | I2C0 总线共享，ES8311 (`0x18`) 负责音频，CW2017 (`0x63`) 负责电池计量 |
| **数字音频总线** | ES8311 (I2S 全双工) | MCLK:`6`, BCLK:`5`, WS:`3`, DOUT:`2`, DIN:`4` | 16kHz 16bit 单声道标准 I2S，MCU DOUT 播放，DIN 麦克风录音 |

---

## 快速上手与刷机指南

### 1. 配置 Wi-Fi
打开 `include/config.h`，填入你的局域网 Wi-Fi 名称和密码：
```c
#define DEFAULT_WIFI_SSID       "你的_WiFi_名称"
#define DEFAULT_WIFI_PASSWORD   "你的_WiFi_密码"
```

### 2. 编译与 0x0 合并固件生成
将 AI Passport 用 Type-C 数据线插入树莓派或电脑 USB 口，运行：
```bash
./flash_firmware.sh
```
脚本将全自动完成：
1. 编译 PlatformIO 工程源码；
2. 按照官方规范自动合成为从 `0x0` 刷写的单一镜像：`merged_firmware_0x0.bin`；
3. 检测串口并在获得确认后完成高速烧录。

> 💡 **官方 Web 刷机工具支持**：生成的 `merged_firmware_0x0.bin` 支持直接打开 [FoloToy 官方 Web Flasher](https://ai-passport.folotoy.cn/tools/web-flasher/)，在浏览器中一键安装至硬件。

---

## 核心操作与交互说明

* **常态看板**：开机自动通过 UDP 8765 端口发现飞书机器人主机，并建立 WebSocket 长连接。屏幕实时显示时间、网络状态、当前活跃工程空间；
* **按住对讲 (PTT)**：长按 **确定键 (OK)** 进入录音模式，麦克风将音频流以 16kHz PCM 实时推向服务端；松开按键后自动转为思考中并由扬声器播报，手机飞书同步推送完整卡片；
* **看板与项目切换**：短按 **上键 (Up)** 刷新看板，长按 **上键 (Up)** 提示当前活跃工程；
* **紧急熔断**：长按 **下键 (Down)** 触发 Physical Stop 物理安全熔断，立即终止服务端所有正在运行的后台 Agent 进程。
