# 🍓 树莓派 GPIO 状态灯指示插件 (API 网关独立版)

基于 [pi_led_api](https://github.com/Level6me/pi_led_api) 集中式 HTTP 网关控制树莓派红绿黄三色 LED 指示灯，与飞书 Bot 全生命周期联动，并提供完整的飞书交互式控制面板。

---

## 🎯 与原物理直驱版的区别

| 特性 | 原版本 (`rpi_gpio_status`) | API 网关独立版 (`rpi_gpio_api_status`) |
| :--- | :--- | :--- |
| **驱动模式** | 独占本机 `lgpio` / `RPi.GPIO` 驱动 | HTTP RESTful 调用集中式网关服务 |
| **多服务共存**| 多进程同时运行会产生引脚竞争冲突 | 支持多 Bot、Web 控制台、iOS 快捷指令同时联动 |
| **高级能力** | 基础常亮 / 闪烁 | 支持 CIE 1931 正弦呼吸、动效剧场、智能倒计时渐暗关灯 |

---

## 🎯 核心联动规则

1. **🟡 黄灯 (思考中 / 工具调用 / 重启)**：
   - **Bot 开始思考时**：常亮黄灯 (`thinking`)
   - **Bot 正在调用工具执行任务时**：正弦平滑呼吸黄灯 (`breathing`)
   - **Bot 正在热重启中**：闪烁黄灯 (`restarting`)
2. **🟢 绿灯 (任务完成 / 启动自检)**：
   - **Bot 启动自检完成**：绿灯连闪 5 次 (`startup`)
   - **Bot 任务成功完成**：常亮绿灯 300 秒，随后自动熄灭 (`success`)
3. **🔴 红灯 (异常报错 / 强制停止)**：
   - **执行出现异常报错或被 `/stop` 强停**：常亮红灯 (`error`)

---

## 💬 飞书交互指令

| 指令 | 说明 |
| :--- | :--- |
| `/led` 或 `/light` | 弹出飞书交互式控制面板卡片（支持点击按钮即时控制） |
| `/led thinking` | 切换为【思考中】(常亮黄灯) |
| `/led breathing` | 切换为【任务执行中】(正弦呼吸黄灯) |
| `/led success` | 切换为【任务完成】(常亮绿灯 300s) |
| `/led error` | 切换为【系统异常】(常亮红灯) |
| `/led startup` | 触发【开机自检】(绿灯连闪 5 次) |
| `/led timer <color> <sec>` | 启动指定通道倒计时（结束前自动平滑渐暗熄灭） |
| `/led pattern <name>` | 播放动效序列 (`police_alert`, `rainbow_flow`, `pulse_heartbeat` 等) |
| `/led off` | 熄灭所有通道 |

---

## ⚙️ 配置文件说明 (`config.json`)

```json
{
  "enabled": true,
  "api_url": "http://127.0.0.1:8080",
  "api_token": "ipad_pro_secret_888",
  "auto_indicator_enabled": true,
  "success_duration_sec": 300
}
```
