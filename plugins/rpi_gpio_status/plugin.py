"""Raspberry Pi GPIO LED Status Indicator Plugin for antigravity-feishu-bot."""

import os
import time
import asyncio
import threading
from plugin_base import BasePlugin
from logger import log

# Gracefully import RPi.GPIO or fallback to Mock Mode on non-Raspberry Pi environments
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except Exception:
    GPIO = None


class RpiGpioStatusPlugin(BasePlugin):

    def initialize(self):
        cfg = self.get_config()
        self.pins = cfg.get("gpio_pins", {"red": 17, "yellow": 27, "green": 22})
        self.blink_interval = cfg.get("blink_interval_sec", 0.3)
        self._blinking_thread = None
        self._stop_blink = False

        if GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                for pin in self.pins.values():
                    GPIO.setup(pin, GPIO.OUT)
                log.info(f"[Plugin:{self.plugin_id}] GPIO initialized successfully (BCM Pins: {self.pins}).")
            except Exception as e:
                log.error(f"[Plugin:{self.plugin_id}] Failed to init GPIO pins: {e}")
        else:
            log.info(f"[Plugin:{self.plugin_id}] RPi.GPIO module not detected. Running in Mock/Simulation mode.")

        # Default Standby State (Green LED ON)
        self.set_state_idle()

    def _set_pin(self, pin_name: str, state: bool):
        pin = self.pins.get(pin_name)
        if pin is None:
            return
        if GPIO_AVAILABLE:
            try:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            except Exception as e:
                log.error(f"[Plugin:{self.plugin_id}] GPIO output error on pin {pin}: {e}")
        else:
            status_str = "HIGH ON" if state else "LOW OFF"
            log.debug(f"[Plugin:{self.plugin_id}] [MOCK-GPIO] Pin {pin} ({pin_name.upper()}) -> {status_str}")

    def _stop_active_blinking(self):
        self._stop_blink = True
        if self._blinking_thread and self._blinking_thread.is_alive():
            self._blinking_thread.join(timeout=1.0)

    def set_state_idle(self):
        """State: Standby / Ready -> Green ON, Yellow OFF, Red OFF."""
        self._stop_active_blinking()
        self._set_pin("green", True)
        self._set_pin("yellow", False)
        self._set_pin("red", False)

    def set_state_running(self):
        """State: AI Executing / Thinking -> Yellow ON, Green OFF, Red OFF."""
        self._stop_active_blinking()
        self._set_pin("green", False)
        self._set_pin("red", False)
        self._set_pin("yellow", True)

    def set_state_success(self):
        """State: Execution Finished Successfully -> Green ON, Yellow OFF, Red OFF."""
        self._stop_active_blinking()
        self._set_pin("yellow", False)
        self._set_pin("red", False)
        self._set_pin("green", True)

    def set_state_error(self):
        """State: Execution Failed / Exception -> Red ON, Yellow OFF, Green OFF."""
        self._stop_active_blinking()
        self._set_pin("green", False)
        self._set_pin("yellow", False)
        self._set_pin("red", True)

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        """Hook called before AI pipeline execution -> Turn on Yellow LED (Running)."""
        self.set_state_running()
        return user_text, session_data

    async def on_after_ai(self, ai_response_text: str, chat_id: str, session_data: dict) -> str:
        """Hook called after AI pipeline completion -> Update LED based on response status."""
        if any(err_kw in ai_response_text.lower() for err_kw in ["⚠️", "❌", "错误", "失败", "超时"]):
            self.set_state_error()
        else:
            self.set_state_success()
        return ai_response_text

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        if command.lower() in ["/light", "/led"]:
            sub_cmd = args.strip().lower()
            if sub_cmd == "red":
                self.set_state_error()
                self.send_reply_text(message_id, "🔴 红色 LED 指示灯已切换为常亮 (模拟任务报错)。")
            elif sub_cmd == "yellow":
                self.set_state_running()
                self.send_reply_text(message_id, "🟡 黄色 LED 指示灯已切换为常亮 (模拟 AI 运行中)。")
            elif sub_cmd == "green":
                self.set_state_success()
                self.send_reply_text(message_id, "🟢 绿色 LED 指示灯已切换为常亮 (模拟系统就绪)。")
            elif sub_cmd == "off":
                self._stop_active_blinking()
                for p in ["red", "yellow", "green"]:
                    self._set_pin(p, False)
                self.send_reply_text(message_id, "⚪ 所有 GPIO LED 指示灯已关闭。")
            else:
                gpio_mode = "硬件 RPi.GPIO 物理接口" if GPIO_AVAILABLE else "模拟日志模式 (Non-RPi)"
                info_card = {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": "💡 树莓派 LED 状态指示灯控制台"},
                        "template": "wathet"
                    },
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": f"**当前硬件工作模式**：`{gpio_mode}`\n\n"
                                       f"**GPIO 引脚映射 (BCM 编号)**：\n"
                                       f"• 🔴 **红灯 (Error/Fault)**：GPIO `{self.pins.get('red')}`\n"
                                       f"• 🟡 **黄灯 (Running/Thinking)**：GPIO `{self.pins.get('yellow')}`\n"
                                       f"• 🟢 **绿灯 (Ready/Idle)**：GPIO `{self.pins.get('green')}`\n\n"
                                       f"**测试控制命令**：\n"
                                       f"• `/light green` - 点亮绿灯 (就绪状态)\n"
                                       f"• `/light yellow` - 点亮黄灯 (运行状态)\n"
                                       f"• `/light red` - 点亮红灯 (异常状态)\n"
                                       f"• `/light off` - 关闭全部指示灯"
                        }
                    ]
                }
                self.send_reply_card(message_id, info_card)
            return True
        return False
