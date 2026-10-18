"""Home Assistant Smart Home Plugin for feishu-bot-plugin & antigravity-feishu-bot.

Provides:
1. Multi-area grouped smart home interactive control dashboard (/ha, /home).
2. Sub-50ms fast-path local voice/text command execution (Zero-LLM latency).
3. In-place interactive card patching for real-time button toggles (Zero screen spamming).
4. One-click token setup, diagnostics, and automatic system MCP injection.
"""

import os
import re
import json
import asyncio
from typing import Tuple, Dict, Any, Optional

import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from plugin_base import BasePlugin
from logger import log
from lark_client import patch_interactive_card_sdk

try:
    from ha_client import ha_client
    from ha_cards import build_dashboard_card, build_setup_card
except ImportError:
    from .ha_client import ha_client
    from .ha_cards import build_dashboard_card, build_setup_card


class HomeAssistantPlugin(BasePlugin):
    """Home Assistant integration plugin."""

    def __init__(self, plugin_dir: str, manifest: dict):
        super().__init__(plugin_dir, manifest)
        self.current_area_id = "all"

    def initialize(self):
        log.info(f"[Plugin:{self.plugin_id}] Home Assistant plugin initialized. Loaded {len(ha_client.entities)} entities across {len(ha_client.areas)} areas.")

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        cmd = command.lower()
        if cmd in ["/ha", "/home", "/smart"]:
            args_clean = (args or "").strip()
            
            # Subcommand: /ha setup
            if args_clean.startswith("setup") or args_clean.startswith("config"):
                card = build_setup_card(ha_client.config)
                self.send_reply_card(message_id, card)
                return True

            # Subcommand: /ha token <token_value>
            if args_clean.startswith("token"):
                token_val = args_clean[5:].strip()
                if not token_val:
                    self.send_reply_text(message_id, "⚠️ 请提供 Token，例如：`/ha token eyJhbGciOiJIUz...`")
                    return True
                
                ha_client.save_config(ha_token=token_val)
                ok, msg = await ha_client.sync_all_states()
                alert = f"✅ Token 已保存并写入系统 MCP！{msg}" if ok else f"⚠️ Token 已保存，但连通测试提示: {msg}"
                card = build_setup_card(ha_client.config, alert_msg=alert)
                self.send_reply_card(message_id, card)
                return True

            # Subcommand: /ha sync
            if args_clean.startswith("sync"):
                ok, msg = await ha_client.sync_all_states()
                devices = ha_client.get_devices_by_area(self.current_area_id)
                stats = ha_client.get_summary_stats()
                card = build_dashboard_card(ha_client.areas, self.current_area_id, devices, stats, alert_text=msg)
                self.send_reply_card(message_id, card)
                return True

            # Default: Show area-partitioned dashboard
            devices = ha_client.get_devices_by_area(self.current_area_id)
            stats = ha_client.get_summary_stats()
            card = build_dashboard_card(ha_client.areas, self.current_area_id, devices, stats)
            self.send_reply_card(message_id, card)
            return True

        return False

    async def on_card_action(self, action: str, value: dict, chat_id: str, card_message_id: str) -> bool:
        """Handles interactive card button clicks with in-place patching."""
        if not action.startswith("ha_"):
            return False

        area_id = value.get("area_id", self.current_area_id)

        # 1. Toggle single device
        if action == "ha_toggle":
            eid = value.get("entity_id", "")
            if eid:
                ok, msg = await ha_client.toggle_device(eid)
                alert = f"已切换 {ha_client.entities.get(eid, {}).get('name', eid)}" if ok else f"切换失败: {msg}"
                devices = ha_client.get_devices_by_area(area_id)
                stats = ha_client.get_summary_stats()
                new_card = build_dashboard_card(ha_client.areas, area_id, devices, stats, alert_text=alert)
                patch_interactive_card_sdk(card_message_id, new_card)
                return True

        # 2. Switch area tab
        elif action == "ha_switch_area":
            new_area_id = value.get("area_id", "all")
            self.current_area_id = new_area_id
            devices = ha_client.get_devices_by_area(new_area_id)
            stats = ha_client.get_summary_stats()
            new_card = build_dashboard_card(ha_client.areas, new_area_id, devices, stats)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 3. Refresh dashboard states
        elif action == "ha_refresh":
            await ha_client.sync_all_states()
            devices = ha_client.get_devices_by_area(area_id)
            stats = ha_client.get_summary_stats()
            new_card = build_dashboard_card(ha_client.areas, area_id, devices, stats, alert_text="状态已刷新")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 4. Turn off all lights
        elif action == "ha_all_off":
            lights = [eid for eid, ed in ha_client.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await ha_client.call_service(eid.split(".")[0], "turn_off", eid)
            devices = ha_client.get_devices_by_area(area_id)
            stats = ha_client.get_summary_stats()
            new_card = build_dashboard_card(ha_client.areas, area_id, devices, stats, alert_text=f"🌙 已向 {len(lights)} 处灯光和开关下发关闭指令")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 5. Open setup card
        elif action == "ha_open_setup":
            new_card = build_setup_card(ha_client.config)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 6. Back to dashboard
        elif action == "ha_back_dashboard":
            devices = ha_client.get_devices_by_area(self.current_area_id)
            stats = ha_client.get_summary_stats()
            new_card = build_dashboard_card(ha_client.areas, self.current_area_id, devices, stats)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 7. Test connectivity
        elif action == "ha_test_conn":
            ok, msg, info = await ha_client.test_connection()
            new_card = build_setup_card(ha_client.config, test_result=msg)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 8. Full sync devices
        elif action == "ha_sync_devices":
            ok, msg = await ha_client.sync_all_states()
            new_card = build_setup_card(ha_client.config, alert_msg=msg)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 9. Inject system MCP
        elif action == "ha_inject_mcp":
            ha_client._sync_to_system_mcp_config()
            new_card = build_setup_card(ha_client.config, alert_msg="✅ 已成功将 Home Assistant 服务注入 ~/.gemini/config/mcp_config.json！")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 10. Toggle Jev System 1 routing
        elif action in ["ha_toggle_jev", "ha_toggle_jev_disabled"]:
            has_token, reason = ha_client.check_jev_token_status()
            if not has_token:
                # /s1 缺失 Token 时拦截并提示
                devices = ha_client.get_devices_by_area(area_id)
                stats = ha_client.get_summary_stats()
                new_card = build_dashboard_card(
                    ha_client.areas, area_id, devices, stats,
                    alert_text="⚠️ Jev 未配置正确：检测到 /s1 未配置 TypeSafe API Token，无法开启！请先发送 /s1 完成配置。"
                )
                patch_interactive_card_sdk(card_message_id, new_card)
                return True

            target_state = value.get("target_state", not ha_client.is_jev_enabled())
            ha_client.save_config(jev_enabled=target_state)
            alert = "⚡ 已开启 Jev 秒级意图分发通道（~200ms 解析口语）" if target_state else "💤 已关闭 Jev 秒级分发，恢复通用大模型思考"
            devices = ha_client.get_devices_by_area(area_id)
            stats = ha_client.get_summary_stats()
            new_card = build_dashboard_card(ha_client.areas, area_id, devices, stats, alert_text=alert)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        return False

    def is_jev_enabled(self) -> bool:
        """Returns True if Jev intent dispatch is enabled and valid."""
        return ha_client.is_jev_enabled()

    async def handle_nlp_intent(self, user_text: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        """Handles smart_home intent dispatched directly from Jev (System 1 Gate)."""
        if not self.is_jev_enabled():
            return False

        clean = (user_text or "").strip()
        if not clean:
            return False

        # 1. Inquiry / Dashboard
        if any(kw in clean for kw in ["看板", "面板", "控制板", "所有设备", "设备列表", "家里状态", "家庭状态"]):
            devices = ha_client.get_devices_by_area(self.current_area_id)
            stats = ha_client.get_summary_stats()
            card = build_dashboard_card(ha_client.areas, self.current_area_id, devices, stats, alert_text="⚡ 由 Jev 策略模型秒级调度")
            self.send_card(chat_id, card)
            return True

        # 2. Turn off all lights / sleep
        if any(kw in clean for kw in ["全关灯", "全屋关灯", "关掉所有灯", "我要睡觉了", "把灯都关了", "关所有灯"]):
            lights = [eid for eid, ed in ha_client.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await ha_client.call_service(eid.split(".")[0], "turn_off", eid)
            self.send_text(chat_id, f"🌙 晚安！[Jev秒级调度] 已为您关闭全屋 {len(lights)} 处灯光与开关。")
            return True

        # 3. Match specific entity from text
        matched = ha_client.match_entity_from_text(clean)
        if matched:
            eid, action = matched
            domain = eid.split(".")[0]
            service = "turn_on" if action == "turn_on" else "turn_off"
            dev_name = ha_client.entities.get(eid, {}).get("name", eid)
            ok, msg = await ha_client.call_service(domain, service, eid)
            action_desc = "开启" if service == "turn_on" else "关闭"
            if ok:
                self.send_text(chat_id, f"⚡ [Jev秒级调度] 已为您{action_desc}【{dev_name}】。")
            else:
                self.send_text(chat_id, f"⚠️ [Jev秒级调度] 操作【{dev_name}】未成功: {msg}")
            return True

        return False

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> Tuple[str, dict]:
        """Sub-50ms Local FastPath for natural smart home commands."""
        clean = (user_text or "").strip()
        if not clean:
            return user_text, session_data

        # 1. Direct dashboard inquiry
        if any(clean == kw for kw in ["家庭看板", "智能家居", "全屋智能", "家居控制", "控制面板"]):
            devices = ha_client.get_devices_by_area(self.current_area_id)
            stats = ha_client.get_summary_stats()
            card = build_dashboard_card(ha_client.areas, self.current_area_id, devices, stats)
            self.send_card(chat_id, card)
            return "", session_data

        # 2. Global sleep / turn off all
        if any(kw in clean for kw in ["全关灯", "全屋关灯", "关掉所有灯", "我要睡觉了", "把灯都关了"]):
            lights = [eid for eid, ed in ha_client.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await ha_client.call_service(eid.split(".")[0], "turn_off", eid)
            self.send_text(chat_id, f"🌙 晚安！已为您关闭全屋 {len(lights)} 处灯光与开关。")
            return "", session_data

        # 3. Match device from text
        matched = ha_client.match_entity_from_text(clean)
        if matched:
            eid, action = matched
            domain = eid.split(".")[0]
            service = "turn_on" if action == "turn_on" else "turn_off"
            dev_name = ha_client.entities.get(eid, {}).get("name", eid)
            ok, msg = await ha_client.call_service(domain, service, eid)
            if ok:
                action_desc = "开启" if service == "turn_on" else "关闭"
                self.send_text(chat_id, f"✅ 已为您{action_desc}【{dev_name}】。")
            else:
                self.send_text(chat_id, f"⚠️ 操作【{dev_name}】未成功: {msg}")
            return "", session_data

        return user_text, session_data
