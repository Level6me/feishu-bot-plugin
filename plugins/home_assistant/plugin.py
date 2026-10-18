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
import time
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

    def _get_live_modules(self):
        """Force reloads and returns latest ha_client and ha_cards modules to prevent staleness."""
        import importlib
        try:
            import ha_client as mod_cli
            importlib.reload(mod_cli)
            cli = mod_cli.ha_client
        except Exception:
            try:
                from . import ha_client as mod_cli
                importlib.reload(mod_cli)
                cli = mod_cli.ha_client
            except Exception:
                cli = ha_client

        try:
            import ha_cards as mod_cards
            importlib.reload(mod_cards)
            b_dash = mod_cards.build_dashboard_card
            b_setup = mod_cards.build_setup_card
        except Exception:
            try:
                from . import ha_cards as mod_cards
                importlib.reload(mod_cards)
                b_dash = mod_cards.build_dashboard_card
                b_setup = mod_cards.build_setup_card
            except Exception:
                b_dash = build_dashboard_card
                b_setup = build_setup_card

        return cli, b_dash, b_setup

    def initialize(self):
        cli, _, _ = self._get_live_modules()
        log.info(f"[Plugin:{self.plugin_id}] Home Assistant plugin initialized. Loaded {len(cli.entities)} entities across {len(cli.areas)} areas.")

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        cmd = command.lower()
        if cmd in ["/ha", "/home", "/smart"]:
            cli, b_dash, b_setup = self._get_live_modules()
            args_clean = (args or "").strip()
            
            # Subcommand: /ha setup
            if args_clean.startswith("setup") or args_clean.startswith("config"):
                card = b_setup(cli.config)
                self.send_reply_card(message_id, card)
                return True

            # Subcommand: /ha token <token_value>
            if args_clean.startswith("token"):
                token_val = args_clean[5:].strip()
                if not token_val:
                    self.send_reply_text(message_id, "⚠️ 请提供 Token，例如：`/ha token eyJhbGciOiJIUz...`")
                    return True
                
                cli.save_config(ha_token=token_val)
                ok, msg = await cli.sync_all_states()
                alert = f"✅ Token 已保存并写入系统 MCP！{msg}" if ok else f"⚠️ Token 已保存，但连通测试提示: {msg}"
                card = b_setup(cli.config, alert_msg=alert)
                self.send_reply_card(message_id, card)
                return True

            # Subcommand: /ha sync
            if args_clean.startswith("sync"):
                ok, msg = await cli.sync_all_states()
                devices = cli.get_devices_by_area(self.current_area_id)
                stats = cli.get_summary_stats()
                card = b_dash(cli.areas, self.current_area_id, devices, stats, alert_text=msg)
                self.send_reply_card(message_id, card)
                return True

            # Default: Show area-partitioned dashboard
            if time.time() - cli.last_sync_time > 30:
                await cli.sync_all_states()
            devices = cli.get_devices_by_area(self.current_area_id)
            stats = cli.get_summary_stats()
            card = b_dash(cli.areas, self.current_area_id, devices, stats)
            self.send_reply_card(message_id, card)
            return True

        return False

    async def on_card_action(self, action: str, value: dict, chat_id: str, card_message_id: str) -> bool:
        """Handles interactive card button clicks with in-place patching."""
        if not action.startswith("ha_"):
            return False

        cli, b_dash, b_setup = self._get_live_modules()
        area_id = value.get("area_id", self.current_area_id)

        # 1. Toggle single device
        if action == "ha_toggle":
            eid = value.get("entity_id", "")
            if eid:
                ok, msg = await cli.toggle_device(eid)
                alert = f"已切换 {cli.entities.get(eid, {}).get('name', eid)}" if ok else f"切换失败: {msg}"
                devices = cli.get_devices_by_area(area_id)
                stats = cli.get_summary_stats()
                new_card = b_dash(cli.areas, area_id, devices, stats, alert_text=alert)
                patch_interactive_card_sdk(card_message_id, new_card)
                return True

        # 2. Switch area tab
        elif action == "ha_switch_area":
            new_area_id = value.get("area_id", "all")
            self.current_area_id = new_area_id
            devices = cli.get_devices_by_area(new_area_id)
            stats = cli.get_summary_stats()
            new_card = b_dash(cli.areas, new_area_id, devices, stats)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 3. Refresh dashboard states
        elif action == "ha_refresh":
            await cli.sync_all_states()
            devices = cli.get_devices_by_area(area_id)
            stats = cli.get_summary_stats()
            new_card = b_dash(cli.areas, area_id, devices, stats, alert_text="状态已刷新")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 4. Turn off all lights
        elif action == "ha_all_off":
            lights = [eid for eid, ed in cli.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await cli.call_service(eid.split(".")[0], "turn_off", eid)
            devices = cli.get_devices_by_area(area_id)
            stats = cli.get_summary_stats()
            new_card = b_dash(cli.areas, area_id, devices, stats, alert_text=f"🌙 已向 {len(lights)} 处灯光和开关下发关闭指令")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 5. Open setup card
        elif action == "ha_open_setup":
            new_card = b_setup(cli.config)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 6. Back to dashboard
        elif action == "ha_back_dashboard":
            devices = cli.get_devices_by_area(self.current_area_id)
            stats = cli.get_summary_stats()
            new_card = b_dash(cli.areas, self.current_area_id, devices, stats)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 7. Test connectivity
        elif action == "ha_test_conn":
            ok, msg, info = await cli.test_connection()
            new_card = b_setup(cli.config, test_result=msg)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 8. Full sync devices
        elif action == "ha_sync_devices":
            ok, msg = await cli.sync_all_states()
            new_card = b_setup(cli.config, alert_msg=msg)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 9. Inject system MCP
        elif action == "ha_inject_mcp":
            cli._sync_to_system_mcp_config()
            new_card = b_setup(cli.config, alert_msg="✅ 已成功将 Home Assistant 服务注入 ~/.gemini/config/mcp_config.json！")
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        # 10. Toggle Jev System 1 routing
        elif action in ["ha_toggle_jev", "ha_toggle_jev_disabled"]:
            has_token, reason = cli.check_jev_token_status()
            if not has_token:
                # /s1 缺失 Token 时拦截并提示
                devices = cli.get_devices_by_area(area_id)
                stats = cli.get_summary_stats()
                new_card = b_dash(
                    cli.areas, area_id, devices, stats,
                    alert_text="⚠️ Jev 未配置正确：检测到 /s1 未配置 TypeSafe API Token，无法开启！请先发送 /s1 完成配置。"
                )
                patch_interactive_card_sdk(card_message_id, new_card)
                return True

            target_state = value.get("target_state", not cli.is_jev_enabled())
            cli.save_config(jev_enabled=target_state)
            alert = "⚡ 已开启 Jev 秒级意图分发通道（~200ms 解析口语）" if target_state else "💤 已关闭 Jev 秒级分发，恢复通用大模型思考"
            devices = cli.get_devices_by_area(area_id)
            stats = cli.get_summary_stats()
            new_card = b_dash(cli.areas, area_id, devices, stats, alert_text=alert)
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        return False

    def is_jev_enabled(self) -> bool:
        """Returns True if Jev intent dispatch is enabled and valid."""
        cli, _, _ = self._get_live_modules()
        return cli.is_jev_enabled()

    async def handle_nlp_intent(self, user_text: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        """Handles smart_home intent dispatched directly from Jev (System 1 Gate)."""
        cli, b_dash, _ = self._get_live_modules()
        if not cli.is_jev_enabled():
            return False

        clean = (user_text or "").strip()
        if not clean:
            return False

        # 1. Inquiry / Dashboard
        ha_panel_keywords = ["家庭看板", "智能家居", "全屋智能", "家居控制", "家里状态", "家庭状态", "ha看板", "ha面板"]
        is_ha_panel = any(kw in clean for kw in ha_panel_keywords) or (
            any(kw in clean for kw in ["看板", "控制板", "面板"]) and any(ctx in clean for ctx in ["家", "智能", "设备", "灯", "ha", "home"])
        )
        if is_ha_panel or any(kw in clean for kw in ["所有设备", "设备列表"]):
            devices = cli.get_devices_by_area(self.current_area_id)
            stats = cli.get_summary_stats()
            card = b_dash(cli.areas, self.current_area_id, devices, stats, alert_text="⚡ 由 Jev 策略模型秒级调度")
            self.send_card(chat_id, card)
            return True

        # 2. Turn off all lights / sleep
        if any(kw in clean for kw in ["全关灯", "全屋关灯", "关掉所有灯", "我要睡觉了", "把灯都关了", "关所有灯"]):
            lights = [eid for eid, ed in cli.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await cli.call_service(eid.split(".")[0], "turn_off", eid)
            self.send_text(chat_id, f"🌙 晚安！[Jev秒级调度] 已为您关闭全屋 {len(lights)} 处灯光与开关。")
            return True

        # 3. Match specific entity from text
        matched = cli.match_entity_from_text(clean)
        if matched:
            eid, action = matched
            domain = eid.split(".")[0]
            service = "turn_on" if action == "turn_on" else "turn_off"
            dev_name = cli.entities.get(eid, {}).get("name", eid)
            ok, msg = await cli.call_service(domain, service, eid)
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

        cli, b_dash, _ = self._get_live_modules()

        # 1. Direct dashboard inquiry
        if any(clean == kw for kw in ["家庭看板", "智能家居", "全屋智能", "家居控制", "ha控制面板", "ha面板"]):
            devices = cli.get_devices_by_area(self.current_area_id)
            stats = cli.get_summary_stats()
            card = b_dash(cli.areas, self.current_area_id, devices, stats)
            self.send_card(chat_id, card)
            return "", session_data

        # 2. Global sleep / turn off all
        if any(kw in clean for kw in ["全关灯", "全屋关灯", "关掉所有灯", "我要睡觉了", "把灯都关了"]):
            lights = [eid for eid, ed in cli.entities.items() if ed.get("domain") in ["light", "switch"]]
            for eid in lights:
                await cli.call_service(eid.split(".")[0], "turn_off", eid)
            self.send_text(chat_id, f"🌙 晚安！已为您关闭全屋 {len(lights)} 处灯光与开关。")
            return "", session_data

        # 3. Match device from text
        matched = cli.match_entity_from_text(clean)
        if matched:
            eid, action = matched
            domain = eid.split(".")[0]
            service = "turn_on" if action == "turn_on" else "turn_off"
            dev_name = cli.entities.get(eid, {}).get("name", eid)
            ok, msg = await cli.call_service(domain, service, eid)
            if ok:
                action_desc = "开启" if service == "turn_on" else "关闭"
                self.send_text(chat_id, f"✅ 已为您{action_desc}【{dev_name}】。")
            else:
                self.send_text(chat_id, f"⚠️ 操作【{dev_name}】未成功: {msg}")
            return "", session_data

        return user_text, session_data
