# FoloToy AI Passport (ESP32-C3) 嵌入式固件工程

本工程为 **FoloToy AI Passport** 专用定制固件，严格对齐官方开发规范与硬件抽象层事实来源（[`components/bsp/include/bsp_pins.h`](https://github.com/FoloToy/ai-passport/blob/main/components/bsp/include/bsp_pins.h)），用于与局域网内的 **Antigravity 飞书机器人 (`antigravity-feishu-bot`)** 实现软硬件全双工协同联动。

---

## 硬件外设与引脚分配（对齐官方 BSP 单一事实来源）

| 外设模块 | 核心芯片 / 方案 | ESP32-C3 引脚 | 电气特性与工作规范 |
| :--- | :--- | :--- | :--- |
| **彩色显示屏** | ST7789P3 (240×320) | MOSI:`9`, SCLK:`8`, CS:`1`, DC:`20`, RST:`-1`, BL:`21` | SPI2 40MHz 高速驱动，RST 硬接 3.3V 走 SWRESET 软复位，强制反色 (INVON) |
| **实体交互按键** | 3 键共用单个 ADC | **GPIO 0** (ADC1_CH0) | 板载 10k 外部上拉，电阻分压识别：<br>• **上键** (0Ω): `0 ~ 150 mV`<br>• **下键** (1kΩ): `150 ~ 447 mV`<br>• **确定键** (2.2kΩ): `447 ~ 1900 mV`<br>• **松开态**: `3300 mV` |
| **I2C 控制总线** | ES8311 + CW2017 | SDA:`10`, SCL:`7` | I2C0 总线共享，ES8311 (`0x18`) 负责音频，CW2017 (`0x63`) 负责高精度电池计量 |
| **数字音频总线** | ES8311 (I2S 全双工) | MCLK:`6`, BCLK:`5`, WS:`3`, DOUT:`2`, DIN:`4` | 16kHz 16bit 单声道标准 I2S，MCU DOUT 播放，DIN 麦克风录音 |
| **背光调光控制** | LEDC PWM 智能调光 | **GPIO 21** | 硬件 PWM 平滑渐变调光，支持超时节能息屏 |

---

## 固件核心功能与交互特性

1. **真实电量与状态栏监控**：
   - 驱动底层板载 **CW2017 库仑计**，精准获取电池端电压（mV）与剩余电量百分比（SOC%）；
   - 顶部状态栏动态呈现 Wi-Fi 信号阶梯格、电量百分比、充电状态指示（CHG）与飞书长连接指示；
   - 具备 **5% 临界低电自动安全预警**（屏幕告警弹窗 + 警报蜂鸣音），避免锂电池过放损坏。

2. **灵动拟人化表情系统 (Cyber Avatar)**：
   - 空闲待机时具有智能眨眼、瞳孔高光的灵动表情；
   - 对讲录音时自动切换为专注聆听表情，并驱动 8 频段跳动频谱律动（Equalizer）；
   - 思考中与 AI 讲话时呈现对应动效并联动多行文字排版。

3. **操作听觉反馈音效 (Earcons / Prompt Tones)**：
   - 确定键按住开启对讲（PTT）：播放清脆升调提示音；
   - 松开按键发送：播放轻柔降调截止音；
   - 局域网网关连线成功：播报三和弦提示音；
   - 紧急告警弹窗：双重短促警报音。

4. **智能节能背光管理 (Smart Dimming)**：
   - 45 秒无按键操作自动平滑渐变淡出至低功耗背光（20%）；
   - 120 秒无操作完全熄屏休眠；
   - 任意按键按下或飞书下发新通知时瞬间平滑唤醒。

5. **多视图卡片分页轮播**：
   - **页面 1（飞书协同）**：当前活跃工作区、Agent 状态、语音引擎联动；
   - **页面 2（硬件诊断）**：CW2017 电池参数、ESP32-C3 内存 Heap、Wi-Fi IP/RSSI、芯片温度与运行时间；
   - **页面 3（通知详情）**：飞书交互卡片与语音对讲快捷指引。
   - 在主界面短按 **上键 (Up)** 或 **下键 (Down)** 即可在三屏之间滑动切换。

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
