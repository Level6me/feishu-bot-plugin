"""
🍓 Raspberry Pi GPIO LED Status Indicator Plugin (API Gateway Edition)
for antigravity-feishu-bot.

Connects to the central pi_led_api service (https://github.com/Level6me/pi_led_api)
via RESTful API & WebSocket for unified hardware control and interactive Feishu cards.
"""

import os
import time
import requests
import threading
from typing import Optional, Dict, Any

from plugin_base import BasePlugin
from logger import log
from lark_client import patch_interactive_card_sdk, send_reply_sdk

DEFAULT_API_URL = "http://127.0.0.1:8080"
DEFAULT_API_TOKEN = os.getenv("API_TOKEN", "ipad_pro_secret_888")

class RpiGpioApiStatusPlugin(BasePlugin):

    def initialize(self):
        cfg = self.get_config() or {}
        self.enabled = cfg.get("enabled", True)
        if not self.enabled:
            log.info(f"[Plugin:{self.plugin_id}] Disabled via config.json.")
            return

        self.api_url = cfg.get("api_url", DEFAULT_API_URL).rstrip("/")
        self.api_token = cfg.get("api_token", DEFAULT_API_TOKEN)
        self.auto_indicator = cfg.get("auto_indicator_enabled", True)
        self.success_duration = int(cfg.get("success_duration_sec", 300))
        self.current_state = "off"

        log.info(f"[Plugin:{self.plugin_id}] Initialized with central gateway at {self.api_url}")
        self.on_startup_complete()

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            if self.api_token.startswith("ey"):
                headers["Authorization"] = f"Bearer {self.api_token}"
            else:
                headers["X-API-Key"] = self.api_token
        return headers

    def _call_api_async(self, endpoint: str, method: str = "POST", json_data: Optional[dict] = None):
        """Asynchronous HTTP request without blocking AI/bot thread."""
        def _worker():
            try:
                url = f"{self.api_url}{endpoint}"
                headers = self._get_headers()
                if method.upper() == "POST":
                    requests.post(url, json=json_data or {}, headers=headers, timeout=2.5)
                elif method.upper() == "DELETE":
                    requests.delete(url, headers=headers, timeout=2.5)
                elif method.upper() == "GET":
                    requests.get(url, headers=headers, timeout=2.5)
            except Exception as e:
                log.debug(f"[Plugin:{self.plugin_id}] Call {endpoint} error: {e}")
        threading.Thread(target=_worker, daemon=True).start()

    def _fetch_snapshot_sync(self) -> Optional[dict]:
        """Synchronously fetch current LED snapshot from gateway."""
        try:
            url = f"{self.api_url}/api/status"
            res = requests.get(url, headers=self._get_headers(), timeout=2.0)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            log.debug(f"[Plugin:{self.plugin_id}] Fetch status error: {e}")
        return None

    # ==================== 状态切换快捷函数 ====================
    def on_startup_complete(self):
        self.current_state = "startup_flashing_green"
        self._call_api_async("/api/state", "POST", {"state": "startup"})

    def set_state_thinking(self):
        if not self.auto_indicator: return
        self.current_state = "thinking_solid_yellow"
        self._call_api_async("/api/state", "POST", {"state": "thinking", "duration": 300})

    def set_state_breathing_yellow(self):
        if not self.auto_indicator: return
        self.current_state = "breathing_yellow"
        self._call_api_async("/api/state", "POST", {"state": "breathing"})

    def set_state_error(self):
        if not self.auto_indicator: return
        self.current_state = "solid_red_error"
        self._call_api_async("/api/state", "POST", {"state": "error"})

    def set_state_success(self):
        if not self.auto_indicator: return
        self.current_state = "success_solid_green"
        self._call_api_async("/api/state", "POST", {"state": "success", "duration": self.success_duration})

    def turn_all_off(self):
        self.current_state = "off"
        self._call_api_async("/api/off", "POST")

    def on_service_restarting(self):
        if not getattr(self, "enabled", True):
            return
        self.current_state = "restarting_yellow_blink"
        self._call_api_async("/api/state", "POST", {"state": "restarting"})

    # ==================== AI 对话生命周期拦截 ====================
    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        if not getattr(self, "enabled", True):
            return user_text, session_data
        self.set_state_thinking()
        return user_text, session_data

    async def on_tool_call(self, tool_name: str, tool_args: dict):
        if not getattr(self, "enabled", True):
            return
        self.set_state_breathing_yellow()

    async def on_after_ai(self, ai_response_text: str, chat_id: str, session_data: dict) -> str:
        if not getattr(self, "enabled", True):
            return ai_response_text
        is_err = session_data.get("last_execution_error", False)
        if not is_err:
            stripped = ai_response_text.strip()
            if stripped.startswith(("❌", "⚠️")) or "traceback (most recent call last):" in stripped.lower():
                is_err = True

        if is_err:
            self.set_state_error()
        else:
            self.set_state_success()
        return ai_response_text

    # ==================== 飞书命令处理 (/led, /light) ====================
    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        if not getattr(self, "enabled", True):
            return False
        if command.lower() not in ["/led", "/light"]:
            return False

        args_parts = args.strip().split() if args else []
        subcmd = args_parts[0].lower() if args_parts else ""

        if not subcmd or subcmd in ["status", "panel"]:
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot)
            self.send_reply_card(message_id, card)
            return True

        elif subcmd in ["off", "stop"]:
            self.turn_all_off()
            self.send_reply_text(message_id, "⏹️ 所有物理指示灯通道已全部熄灭。")
            return True

        elif subcmd in ["thinking", "think"]:
            self.set_state_thinking()
            self.send_reply_text(message_id, "🟡 已切换至【思考中】(黄灯常亮)")
            return True

        elif subcmd in ["breathing", "breath", "run"]:
            self.set_state_breathing_yellow()
            self.send_reply_text(message_id, "✨ 已切换至【任务执行中】(平滑正弦呼吸黄灯)")
            return True

        elif subcmd in ["success", "ok"]:
            self.set_state_success()
            self.send_reply_text(message_id, f"🟢 已切换至【任务完成】(绿灯常亮 {self.success_duration}s)")
            return True

        elif subcmd in ["error", "err", "fail"]:
            self.set_state_error()
            self.send_reply_text(message_id, "🔴 已切换至【系统异常】(红灯常亮)")
            return True

        elif subcmd in ["startup", "check"]:
            self.on_startup_complete()
            self.send_reply_text(message_id, "🔄 已触发【开机自检】(绿灯连闪 5 次)")
            return True

        elif subcmd == "timer" and len(args_parts) >= 3:
            color = args_parts[1].lower()
            try:
                secs = int(args_parts[2])
                self._call_api_async("/api/timer", "POST", {"color": color, "duration_sec": secs, "fade_out_sec": 5})
                self.send_reply_text(message_id, f"⏱️ 已为 {color.upper()} 启动 {secs} 秒智能倒计时 (结束前渐暗关灯)")
            except ValueError:
                self.send_reply_text(message_id, "⚠️ 请输入正确的秒数，格式：`/led timer green 60`")
            return True

        elif subcmd == "pattern" and len(args_parts) >= 2:
            p_name = args_parts[1].lower()
            self._call_api_async("/api/pattern", "POST", {"name": p_name, "repeat": 5})
            self.send_reply_text(message_id, f"🎭 正在播放动效序列：`{p_name}`")
            return True

        else:
            help_text = (
                "🍓 **树莓派 LED 状态指示控制指令 (API 网关版)**：\n\n"
                "• `/led` 或 `/light`：弹出交互式控制面板卡片\n"
                "• `/led thinking`：思考中 (黄灯常亮)\n"
                "• `/led breathing`：任务执行中 (正弦呼吸黄灯)\n"
                "• `/led success`：成功完成 (常亮绿灯 300s)\n"
                "• `/led error`：系统异常 (常亮红灯)\n"
                "• `/led startup`：开机自检 (绿灯连闪 5 次)\n"
                "• `/led timer <color> <sec>`：启动倒计时渐暗关灯\n"
                "• `/led pattern <name>`：播放动效 (police_alert / rainbow_flow 等)\n"
                "• `/led off`：熄灭所有通道"
            )
            self.send_reply_text(message_id, help_text)
            return True

    # ==================== 飞书交互式卡片事件响应 ====================
    async def on_card_action(self, action: str, value: dict, chat_id: str, card_message_id: str) -> bool:
        if not getattr(self, "enabled", True):
            return False
        if action == "set_led_state":
            target_state = value.get("state", "off")
            dur = int(value.get("duration", 300))
            self._call_api_async("/api/state", "POST", {"state": target_state, "duration": dur})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        elif action == "play_led_pattern":
            pat_name = value.get("pattern", "police_alert")
            self._call_api_async("/api/pattern", "POST", {"name": pat_name, "repeat": 5})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        elif action == "start_led_timer":
            color = value.get("color", "green")
            secs = int(value.get("duration_sec", 60))
            self._call_api_async("/api/timer", "POST", {"color": color, "duration_sec": secs, "fade_out_sec": 5})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        elif action == "turn_off_all":
            self.turn_all_off()
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        elif action == "refresh_led_card":
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        return False

    # ==================== 构建飞书交互式卡片 ====================
    def build_control_card(self, snapshot: Optional[dict] = None) -> dict:
        raw_state = "unknown"
        mode_str = "HTTP 网关连接"
        timer_info = "未激活"
        pins_info = "🔴 22 | 🟡 27 | 🟢 17"
        header_color = "blue"

        if snapshot:
            raw_state = snapshot.get("current_state", "off")
            hw = snapshot.get("hardware", {})
            mode_str = f"{hw.get('mode', 'MOCK')} {'(Gamma 2.2)' if hw.get('gamma_correction') else ''}"
            pins = hw.get("pins", {})
            if pins:
                pins_info = f"🔴 GPIO {pins.get('red', 22)} | 🟡 GPIO {pins.get('yellow', 27)} | 🟢 GPIO {pins.get('green', 17)}"
            st = snapshot.get("smart_timer", {})
            if st and st.get("active"):
                timer_info = f"🟢 剩余 {st.get('remaining_seconds')}s / {st.get('total_duration')}s"

        state_map = {
            "thinking_solid_yellow": ("🟡 思考中 (Solid Yellow)", "orange"),
            "thinking": ("🟡 思考中 (Solid Yellow)", "orange"),
            "breathing_yellow": ("✨ 任务执行中 (Breathing Yellow)", "orange"),
            "breathing": ("✨ 任务执行中 (Breathing Yellow)", "orange"),
            "restarting_yellow_blink": ("⚡ 重启中 (Blink Yellow)", "orange"),
            "success_solid_green": ("🟢 任务成功完成 (Solid Green)", "green"),
            "solid_green_success_300s": ("🟢 任务成功完成 (Solid Green)", "green"),
            "solid_red_error": ("🔴 系统异常告警 (Solid Red)", "red"),
            "error": ("🔴 系统异常告警 (Solid Red)", "red"),
            "startup_flashing_green": ("🔄 开机自检中 (Startup)", "blue"),
            "off": ("⏹️ 全部熄灭 (Off)", "grey"),
        }

        display_name, header_color = state_map.get(raw_state, (f"💡 运行中 ({raw_state})", "blue"))

        elements = [
            {
                "tag": "markdown",
                "content": (
                    f"**💡 当前硬件状态**：**{display_name}**\n\n"
                    f"• **网关地址**：`{self.api_url}`\n"
                    f"• **硬件引脚**：`{pins_info}`\n"
                    f"• **驱动模式**：`{mode_str}`\n"
                    f"• **智能倒计时**：`{timer_info}`"
                )
            },
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": "**🎯 快速切换系统预设**"
            },
            {
                "tag": "action",
                "layout": "flow",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🟡 思考中"},
                        "type": "default",
                        "value": {"action": "set_led_state", "state": "thinking", "duration": 300}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✨ 正弦呼吸"},
                        "type": "primary",
                        "value": {"action": "set_led_state", "state": "breathing"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🟢 成功完成"},
                        "type": "primary",
                        "value": {"action": "set_led_state", "state": "success", "duration": self.success_duration}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔴 异常报错"},
                        "type": "danger",
                        "value": {"action": "set_led_state", "state": "error"}
                    }
                ]
            },
            {
                "tag": "markdown",
                "content": "**🎭 动效与智能倒计时**"
            },
            {
                "tag": "action",
                "layout": "flow",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🚨 警报动效"},
                        "type": "danger",
                        "value": {"action": "play_led_pattern", "pattern": "police_alert"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🌈 流水动效"},
                        "type": "default",
                        "value": {"action": "play_led_pattern", "pattern": "rainbow_flow"}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "⏱️ 番茄钟 25m"},
                        "type": "primary",
                        "value": {"action": "start_led_timer", "color": "green", "duration_sec": 1500}
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "⏹️ 熄灭全灯"},
                        "type": "default",
                        "value": {"action": "turn_off_all"}
                    }
                ]
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "flow",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔄 刷新实时状态"},
                        "type": "default",
                        "value": {"action": "refresh_led_card"}
                    }
                ]
            }
        ]

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🍓 树莓派 LED 状态指示控制台 (API 版)"
                },
                "template": header_color
            },
            "elements": elements
        }
