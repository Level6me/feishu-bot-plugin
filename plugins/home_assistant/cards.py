"""Interactive Feishu Card Builders for Home Assistant Plugin.

Features:
1. Multi-area grouped dashboard with quick device toggles.
2. Real-time status indicators (🟢 ON, ⚪ OFF, ❄️ Climate, 📺 Media).
3. Full interactive card-based configuration & diagnostic controls.
"""

from typing import List, Dict, Any, Optional


def build_dashboard_card(
    areas: List[Dict[str, Any]],
    current_area_id: str,
    devices: List[Dict[str, Any]],
    summary_stats: Dict[str, Any],
    alert_text: Optional[str] = None
) -> dict:
    """Builds the clean, area-partitioned smart home control dashboard card."""
    total = summary_stats.get("total", len(devices))
    total_on = summary_stats.get("total_on", 0)

    # 1. Summary Header
    elements = []
    
    status_summary = f"**全屋概况**：已发现 **{total}** 处设备  |  ⚡ 当前开启：**{total_on}** 处"
    if alert_text:
        status_summary += f"\n> 💡 {alert_text}"

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": status_summary
        }
    })

    # 2. Area Navigation Tabs (Buttons)
    area_buttons = []
    
    # "All" tab
    all_btn_type = "primary" if current_area_id == "all" else "default"
    area_buttons.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "🏠 全部"},
        "type": all_btn_type,
        "value": {"action": "ha_switch_area", "area_id": "all"}
    })

    # Top area buttons
    for a in areas[:5]:
        aid = a["id"]
        aname = a["name"]
        btn_type = "primary" if current_area_id == aid else "default"
        area_buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": aname},
            "type": btn_type,
            "value": {"action": "ha_switch_area", "area_id": aid}
        })

    elements.append({
        "tag": "action",
        "actions": area_buttons
    })
    elements.append({"tag": "hr"})

    # 3. Devices in Current Area
    if not devices:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "✨ *该区域当前没有匹配到受控智能设备。*"
            }
        })
    else:
        # Show up to 10 key devices cleanly to keep the card compact & snappy
        for d in devices[:10]:
            eid = d.get("entity_id", "")
            dname = d.get("name", eid)
            domain = d.get("domain", "")
            state = str(d.get("state", "off")).lower()

            # Icons & Status formatting
            if domain == "light":
                icon = "💡"
                is_active = (state == "on")
                status_str = "<font color='green'>● 开启</font>" if is_active else "<font color='grey'>○ 关闭</font>"
            elif domain == "switch":
                icon = "🔌"
                is_active = (state == "on")
                status_str = "<font color='green'>● 通电</font>" if is_active else "<font color='grey'>○ 断电</font>"
            elif domain == "climate":
                icon = "❄️"
                is_active = (state not in ["off", "unavailable"])
                status_str = f"<font color='blue'>● {state}</font>" if is_active else "<font color='grey'>○ 待机</font>"
            elif domain == "media_player":
                icon = "📺"
                is_active = (state in ["playing", "on"])
                status_str = "<font color='green'>● 运行</font>" if is_active else "<font color='grey'>○ 关机</font>"
            else:
                icon = "⚙️"
                is_active = (state == "on")
                status_str = state

            toggle_btn_text = "⚪ 关闭" if is_active else "🟢 开启"
            toggle_btn_type = "default" if is_active else "primary"

            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"{icon} **{dname}**\n状态：{status_str}"
                },
                "extra": {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": toggle_btn_text},
                    "type": toggle_btn_type,
                    "value": {
                        "action": "ha_toggle",
                        "entity_id": eid,
                        "area_id": current_area_id
                    }
                }
            })

    # 4. Bottom Controls
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔄 刷新状态"},
                "type": "default",
                "value": {"action": "ha_refresh", "area_id": current_area_id}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🌙 全关灯光"},
                "type": "default",
                "value": {"action": "ha_all_off", "area_id": current_area_id}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⚙️ 快捷配置"},
                "type": "default",
                "value": {"action": "ha_open_setup"}
            }
        ]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🏠 Home Assistant 全屋控制看板"},
            "template": "turquoise"
        },
        "elements": elements
    }


def build_setup_card(
    config: Dict[str, Any],
    test_result: Optional[str] = None,
    alert_msg: Optional[str] = None
) -> dict:
    """Builds the interactive setup and diagnostics card for Home Assistant."""
    ha_url = config.get("ha_url", "http://10.0.0.2:8123")
    has_token = bool(config.get("ha_token"))
    wh = config.get("webhook_url", "")

    token_display = "已绑定 (********)" if has_token else "未绑定 (点击或输入指令绑定)"
    wh_display = wh if wh else "未设置"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**当前 Home Assistant 配置参数：**\n"
                    f"• **服务地址**：`{ha_url}`\n"
                    f"• **访问令牌**：`{token_display}`\n"
                    f"• **MCP Webhook**：`{wh_display}`\n\n"
                    f"💡 **快捷绑定说明**：\n"
                    f"在对话框直接发送 `/ha token <您的长期访问令牌>` 即可一键完成全自动装配与 MCP 注册！"
                )
            }
        }
    ]

    if test_result:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"> 🔍 **连通性测试反馈**：\n> {test_result}"
            }
        })

    if alert_msg:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"> 📢 **操作结果**：\n> {alert_msg}"
            }
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔍 测试连通性"},
                "type": "primary",
                "value": {"action": "ha_test_conn"}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔄 全量同步硬件"},
                "type": "default",
                "value": {"action": "ha_sync_devices"}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📋 写入系统 MCP"},
                "type": "default",
                "value": {"action": "ha_inject_mcp"}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⬅️ 返回看板"},
                "type": "default",
                "value": {"action": "ha_back_dashboard"}
            }
        ]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚙️ Home Assistant 接入与配置中心"},
            "template": "indigo"
        },
        "elements": elements
    }
