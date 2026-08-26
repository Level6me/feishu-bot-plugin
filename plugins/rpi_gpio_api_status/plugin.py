"""
🍓 Raspberry Pi GPIO LED Status Indicator Plugin (API Gateway Edition)
for antigravity-feishu-bot.

Features:
- Connects to central pi_led_api gateway (http://127.0.0.1:8080 / https://piled.abab.pw)
- Full Interactive Button Configuration Panel for Gateway URL, Tokens, and Settings
- Live Gateway connectivity & latency test with interactive card feedback
- Full AI dialogue lifecycle indicators (Thinking, Breathing, Success, Error, Restart)
- Interactive Feishu Action Cards with instant buttons and timers
"""

import os
import time
import json
import requests
import threading
from typing import Optional, Dict, Any, Tuple

from plugin_base import BasePlugin
from logger import log
from lark_client import patch_interactive_card_sdk, send_reply_sdk

DEFAULT_API_URL = "http://127.0.0.1:8080"
DEFAULT_API_TOKEN = os.getenv("API_TOKEN", "ipad_pro_secret_888")

class RpiGpioApiStatusPlugin(BasePlugin):

    def initialize(self):
        self.config_data = self.get_config() or {}
        self.enabled = self.config_data.get("enabled", True)
        if not self.enabled:
            log.info(f"[Plugin:{self.plugin_id}] Disabled via config.json.")
            return

        self.api_url = self.config_data.get("api_url", DEFAULT_API_URL).rstrip("/")
        self.api_token = self.config_data.get("api_token", DEFAULT_API_TOKEN)
        self.auto_indicator = self.config_data.get("auto_indicator_enabled", True)
        self.success_duration = int(self.config_data.get("success_duration_sec", 300))
        self.current_state = "off"
        self.last_test_result: Optional[dict] = None

        log.info(f"[Plugin:{self.plugin_id}] Initialized with central gateway at {self.api_url}")
        self.on_startup_complete()

    def save_config_file(self, new_configs: dict):
        """保存配置到插件本地 config.json 并实时热更新内存属性"""
        self.config_data.update(new_configs)
        if "api_url" in new_configs:
            self.api_url = new_configs["api_url"].rstrip("/")
        if "api_token" in new_configs:
            self.api_token = new_configs["api_token"]
        if "auto_indicator_enabled" in new_configs:
            self.auto_indicator = new_configs["auto_indicator_enabled"]
        if "success_duration_sec" in new_configs:
            self.success_duration = int(new_configs["success_duration_sec"])

        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
            log.info(f"[Plugin:{self.plugin_id}] 配置已成功保存至 {config_path}")
        except Exception as e:
            log.error(f"[Plugin:{self.plugin_id}] 保存配置失败: {e}")

    def _get_headers(self, custom_token: Optional[str] = None) -> dict:
        tok = custom_token if custom_token is not None else self.api_token
        headers = {"Content-Type": "application/json"}
        if tok:
            if tok.startswith("ey"):
                headers["Authorization"] = f"Bearer {tok}"
            else:
                headers["X-API-Key"] = tok
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

    def test_gateway_connection(self, custom_url: Optional[str] = None, custom_token: Optional[str] = None) -> dict:
        """测试目标网关连通性并测量网络 RTT 延迟"""
        target_url = (custom_url or self.api_url).rstrip("/")
        headers = self._get_headers(custom_token)
        start_t = time.perf_counter()
        try:
            res = requests.get(f"{target_url}/api/status", headers=headers, timeout=3.0)
            latency_ms = round((time.perf_counter() - start_t) * 1000, 1)
            if res.status_code == 200:
                data = res.json()
                result = {
                    "success": True,
                    "url": target_url,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "driver_mode": data.get("hardware", {}).get("mode", "UNKNOWN"),
                    "gamma_enabled": data.get("hardware", {}).get("gamma_correction", False),
                    "registered_devices": data.get("auth", {}).get("registered_devices_count", 0),
                    "timestamp": time.strftime("%H:%M:%S", time.localtime())
                }
            else:
                result = {
                    "success": False,
                    "url": target_url,
                    "status_code": res.status_code,
                    "latency_ms": latency_ms,
                    "error": f"HTTP {res.status_code}: {res.text[:100]}",
                    "timestamp": time.strftime("%H:%M:%S", time.localtime())
                }
        except Exception as e:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 1)
            result = {
                "success": False,
                "url": target_url,
                "status_code": 0,
                "latency_ms": latency_ms,
                "error": str(e),
                "timestamp": time.strftime("%H:%M:%S", time.localtime())
            }
        self.last_test_result = result
        return result

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
        if not getattr(self, "enabled", True): return
        self.current_state = "restarting_yellow_blink"
        self._call_api_async("/api/state", "POST", {"state": "restarting"})

    # ==================== AI 对话生命周期拦截 ====================
    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        if not getattr(self, "enabled", True): return user_text, session_data
        self.set_state_thinking()
        return user_text, session_data

    async def on_tool_call(self, tool_name: str, tool_args: dict):
        if not getattr(self, "enabled", True): return
        self.set_state_breathing_yellow()

    async def on_after_ai(self, ai_response_text: str, chat_id: str, session_data: dict) -> str:
        if not getattr(self, "enabled", True): return ai_response_text
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
            card = self.build_control_card(snapshot, view_mode="control")
            self.send_reply_card(message_id, card)
            return True

        elif subcmd in ["test", "ping"]:
            res = self.test_gateway_connection()
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode="control", test_banner=res)
            self.send_reply_card(message_id, card)
            return True

        elif subcmd == "config":
            if len(args_parts) >= 2:
                new_url = args_parts[1].strip()
                new_token = args_parts[2].strip() if len(args_parts) >= 3 else self.api_token
                self.save_config_file({"api_url": new_url, "api_token": new_token})
                res = self.test_gateway_connection()
                snapshot = self._fetch_snapshot_sync()
                card = self.build_control_card(snapshot, view_mode="config", test_banner=res)
                self.send_reply_card(message_id, card)
            else:
                snapshot = self._fetch_snapshot_sync()
                card = self.build_control_card(snapshot, view_mode="config")
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
                "• `/led test`：测试当前网关连通性与网络延迟\n"
                "• `/led config`：进入交互式按钮配置面板\n"
                "• `/led config <url> [token]`：快捷修改网关 URL 与 Token\n"
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

        act = action or (value.get("action") if isinstance(value, dict) else "")

        # 1. 连通性测试
        if act == "test_gateway_connection":
            test_res = self.test_gateway_connection()
            snapshot = self._fetch_snapshot_sync()
            current_view = value.get("view", "control")
            card = self.build_control_card(snapshot, view_mode=current_view, test_banner=test_res)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 2. 视图切换
        elif act == "switch_led_view":
            target_view = value.get("view", "control")
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode=target_view)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 3. 交互式按钮：设置网关 URL
        elif act == "set_gateway_url":
            target_url = value.get("url", DEFAULT_API_URL)
            self.save_config_file({"api_url": target_url})
            test_res = self.test_gateway_connection()
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode="config", test_banner=test_res)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 4. 交互式按钮：设置网关 Token
        elif act == "set_gateway_token":
            target_token = value.get("token", "")
            self.save_config_file({"api_token": target_token})
            test_res = self.test_gateway_connection()
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode="config", test_banner=test_res)
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 5. 交互式按钮：切换自动状态联动开关
        elif act == "toggle_auto_indicator":
            new_auto = not self.auto_indicator
            self.save_config_file({"auto_indicator_enabled": new_auto})
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode="config")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 6. 交互式按钮：设置成功保持秒数
        elif act == "set_success_duration":
            dur = int(value.get("duration", 300))
            self.save_config_file({"success_duration_sec": dur})
            snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(snapshot, view_mode="config")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 7. 控制面板：切换系统预设状态
        elif act == "set_led_state":
            target_state = value.get("state", "off")
            dur = int(value.get("duration", 300))
            self._call_api_async("/api/state", "POST", {"state": target_state, "duration": dur})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot, view_mode="control")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 8. 控制面板：播放动效
        elif act == "play_led_pattern":
            pat_name = value.get("pattern", "police_alert")
            self._call_api_async("/api/pattern", "POST", {"name": pat_name, "repeat": 5})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot, view_mode="control")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 9. 控制面板：启动智能倒计时
        elif act == "start_led_timer":
            color = value.get("color", "green")
            secs = int(value.get("duration_sec", 60))
            self._call_api_async("/api/timer", "POST", {"color": color, "duration_sec": secs, "fade_out_sec": 5})
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot, view_mode="control")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 10. 控制面板：一键熄灭
        elif act == "turn_off_all":
            self.turn_all_off()
            time.sleep(0.3)
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot, view_mode="control")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        # 11. 控制面板：刷新卡片
        elif act == "refresh_led_card":
            new_snapshot = self._fetch_snapshot_sync()
            card = self.build_control_card(new_snapshot, view_mode="control")
            patch_interactive_card_sdk(card_message_id, card)
            return True

        return False

    # ==================== 构建飞书交互式卡片 ====================
    def build_control_card(self, snapshot: Optional[dict] = None, view_mode: str = "control", test_banner: Optional[dict] = None) -> dict:
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

        masked_token = f"{self.api_token[:3]}****{self.api_token[-3:]}" if len(self.api_token) > 6 else (self.api_token or "无 (未设置)")
        elements = []

        # 1. Test Result Banner (If present)
        if test_banner or self.last_test_result:
            tb = test_banner or self.last_test_result
            if tb.get("success"):
                elements.append({
                    "tag": "markdown",
                    "content": f"✅ **连通性测试通过** (`{tb.get('timestamp')}`)\n• **目标 URL**：`{tb.get('url')}`\n• **响应耗时**：**`{tb.get('latency_ms')} ms`** | 驱动：`{tb.get('driver_mode')}`"
                })
            else:
                elements.append({
                    "tag": "markdown",
                    "content": f"❌ **连通性测试失败** (`{tb.get('timestamp')}`)\n• **目标 URL**：`{tb.get('url')}`\n• **错误原因**：`{tb.get('error')}`"
                })
            elements.append({"tag": "hr"})

        if view_mode == "config":
            # ==================== 交互式按钮配置面板 ====================
            is_local = "127.0.0.1" in self.api_url or "localhost" in self.api_url
            is_prod = "piled.abab.pw" in self.api_url
            is_test_server = "43.155.173.146" in self.api_url

            is_ipad_tok = self.api_token == "ipad_pro_secret_888"
            is_bot_tok = self.api_token == "default_feishu_bot_token"
            is_empty_tok = not self.api_token

            elements.extend([
                {
                    "tag": "markdown",
                    "content": (
                        "**⚙️ pi_led_api 网关参数交互式配置面板**\n\n"
                        f"• **当前网关地址**：`{self.api_url}`\n"
                        f"• **当前 API Token**：`{masked_token}`\n"
                        f"• **自动联动状态**：`{'🟢 开启' if self.auto_indicator else '⚪ 已关闭'}`\n"
                        f"• **成功常亮时长**：`{self.success_duration} 秒`"
                    )
                },
                {"tag": "hr"},
                {
                    "tag": "markdown",
                    "content": "**🌐 1. 点击按钮切换网关 URL：**"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_local else ''}🏠 本地 (127.0.0.1:8080)"},
                            "type": "primary" if is_local else "default",
                            "value": {"action": "set_gateway_url", "url": "http://127.0.0.1:8080"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_prod else ''}🌐 生产域名 (piled.abab.pw)"},
                            "type": "primary" if is_prod else "default",
                            "value": {"action": "set_gateway_url", "url": "https://piled.abab.pw"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_test_server else ''}☁️ 测试服 (43.155:8080)"},
                            "type": "primary" if is_test_server else "default",
                            "value": {"action": "set_gateway_url", "url": "http://43.155.173.146:8080"}
                        }
                    ]
                },
                {
                    "tag": "markdown",
                    "content": "**🔑 2. 点击按钮切换预设 API Token：**"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_ipad_tok else ''}📱 iPad Pro Token"},
                            "type": "primary" if is_ipad_tok else "default",
                            "value": {"action": "set_gateway_token", "token": "ipad_pro_secret_888"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_bot_tok else ''}🤖 Bot 默认 Token"},
                            "type": "primary" if is_bot_tok else "default",
                            "value": {"action": "set_gateway_token", "token": "default_feishu_bot_token"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if is_empty_tok else ''}🚫 清空 Token (免密)"},
                            "type": "danger" if is_empty_tok else "default",
                            "value": {"action": "set_gateway_token", "token": ""}
                        }
                    ]
                },
                {
                    "tag": "markdown",
                    "content": "**⏱️ 3. 成功常亮保持时长与自动联动：**"
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"联动: {'🟢 开启中' if self.auto_indicator else '⚪ 已停用'}"},
                            "type": "primary" if self.auto_indicator else "default",
                            "value": {"action": "toggle_auto_indicator"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if self.success_duration == 60 else ''}60 秒"},
                            "type": "primary" if self.success_duration == 60 else "default",
                            "value": {"action": "set_success_duration", "duration": 60}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if self.success_duration == 300 else ''}300 秒"},
                            "type": "primary" if self.success_duration == 300 else "default",
                            "value": {"action": "set_success_duration", "duration": 300}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": f"{'✓ ' if self.success_duration == 600 else ''}600 秒"},
                            "type": "primary" if self.success_duration == 600 else "default",
                            "value": {"action": "set_success_duration", "duration": 600}
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
                            "text": {"tag": "plain_text", "content": "🔌 测试当前配置连通性"},
                            "type": "primary",
                            "value": {"action": "test_gateway_connection", "view": "config"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔙 返回控制面板"},
                            "type": "default",
                            "value": {"action": "switch_led_view", "view": "control"}
                        }
                    ]
                }
            ])
            header_title = "⚙️ 树莓派 LED 网关参数配置 (交互式按钮)"
            header_color = "blue"

        else:
            # ==================== 控制台视图 ====================
            elements.extend([
                {
                    "tag": "markdown",
                    "content": (
                        f"**💡 当前硬件状态**：**{display_name}**\n\n"
                        f"• **网关服务**：`{self.api_url}` (Token: `{masked_token}`)\n"
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
                            "text": {"tag": "plain_text", "content": "🔌 测试连通性"},
                            "type": "primary",
                            "value": {"action": "test_gateway_connection", "view": "control"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "⚙️ 交互式配置"},
                            "type": "default",
                            "value": {"action": "switch_led_view", "view": "config"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 刷新状态"},
                            "type": "default",
                            "value": {"action": "refresh_led_card"}
                        }
                    ]
                }
            ])
            header_title = "🍓 树莓派 LED 状态指示控制台 (API 版)"

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": header_title
                },
                "template": header_color
            },
            "elements": elements
        }
