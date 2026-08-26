# 🍓 树莓派 GPIO 状态灯指示插件 (API 网关独立版 v2.0)

基于 [pi_led_api](https://github.com/Level6me/pi_led_api) 集中式 HTTP 网关控制树莓派红绿黄三色 LED 指示灯，与飞书 Bot 全生命周期联动，并提供完整的飞书交互式控制面板与网关连通性测试。

---

## 🎯 与原物理直驱版的区别

| 特性 | 原版本 (`rpi_gpio_status`) | API 网关独立版 (`rpi_gpio_api_status`) |
| :--- | :--- | :--- |
| **驱动模式** | 独占本机 `lgpio` / `RPi.GPIO` 驱动 | HTTP RESTful 调用集中式网关服务 |
| **多服务共存**| 多进程同时运行会产生引脚竞争冲突 | 支持多 Bot、Web 控制台、iOS 快捷指令同时联动 |
| **高级能力** | 基础常亮 / 闪烁 | 支持 CIE 1931 正弦呼吸、动效剧场、智能倒计时渐暗关灯 |
| **在线配置** | 改代码或手动编辑文件 | 飞书卡片点击按钮输入自定义 URL / Token，即时测试 |

---

## 💬 飞书交互指令与操作

| 指令 | 说明 |
| :--- | :--- |
| `/led` 或 `/light` | 弹出飞书交互式控制面板卡片（支持点击按钮即时控制） |
| `/led test` | 快速测试当前网关连通性与网络 RTT 延迟 |
| `/led config` | 进入交互式配置中心（点击按钮即可直接输入新的 URL 或 Token） |
| `/led thinking` | 切换为【思考中】(常亮黄灯) |
| `/led breathing` | 切换为【任务执行中】(正弦呼吸黄灯) |
| `/led success` | 切换为【任务完成】(常亮绿灯 300s) |
| `/led error` | 切换为【系统异常】(常亮红灯) |
| `/led startup` | 触发【开机自检】(绿灯连闪 5 次) |
| `/led timer <color> <sec>` | 启动指定通道倒计时（结束前自动平滑渐暗熄灭） |
| `/led pattern <name>` | 播放动效序列 (`police_alert`, `rainbow_flow`, `pulse_heartbeat` 等) |
| `/led off` | 熄灭所有通道 |

---

## 🎛️ 飞书卡片可视化操作

1. **🌐 修改网关 URL**：点击【🌐 修改网关 URL】按钮，卡片会提示请直接在聊天框回复新的网关地址，输入后自动保存并立即测试连通性。
2. **🔑 修改 API Token**：点击【🔑 修改 API Token】按钮，卡片会提示请直接在聊天框回复新的 Token，输入后自动持久化并验签。
3. **🔌 测试连通性**：点击【🔌 测试连通性】按钮，即时检测网关状态并在卡片顶部显示响应延迟（ms）、HTTP 状态码及驱动模式。

---

## ⚙️ 配置文件说明 (`config.json`)

```json
{
  "enabled": true,
  "api_url": "http://127.0.0.1:8080",
  "api_token": "your_api_token",
  "auto_indicator_enabled": true,
  "success_duration_sec": 300
}
```
