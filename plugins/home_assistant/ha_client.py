"""Home Assistant Client & Device Caching Engine for feishu-bot-plugin.

Supports:
1. Multi-tier discovery: Local storage parsing, REST API querying, and MCP Webhook fallback.
2. Fast in-memory caching of areas, devices, and current states.
3. Rapid service execution (sub-50ms REST API calls).
4. Automatic persistence of configuration and bi-directional sync to ~/.gemini/config/mcp_config.json.
"""

import os
import sys
import json
import time
import asyncio
import urllib.request
import urllib.error
from typing import Optional, Dict, List, Tuple, Any

try:
    import aiohttp
    _HAVE_AIOHTTP = True
except ImportError:
    _HAVE_AIOHTTP = False


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "plugin_data", "home_assistant"))
CONFIG_PATH = os.path.join(PLUGIN_DATA_DIR, "config.json")
CACHE_PATH = os.path.join(PLUGIN_DATA_DIR, "devices_cache.json")
MCP_CONFIG_PATH = os.path.expanduser("~/.gemini/config/mcp_config.json")
HA_STORAGE_AREA = "/home/jiang/homeassistant/.storage/core.area_registry"
HA_STORAGE_DEVICE = "/home/jiang/homeassistant/.storage/core.device_registry"
HA_STORAGE_ENTITY = "/home/jiang/homeassistant/.storage/core.entity_registry"
HA_TOKEN_FILE = "/home/jiang/homeassistant/.storage/ha_token.txt"

DEFAULT_HA_URL = "http://10.0.0.2:8123"
FALLBACK_HA_URLS = ["http://10.0.0.2:8123", "http://127.0.0.1:8123", "http://localhost:8123"]


class HaClient:
    """High-performance Home Assistant client with local entity mapping and cache."""

    def __init__(self):
        os.makedirs(PLUGIN_DATA_DIR, exist_ok=True)
        self.config = self._load_config()
        self.ha_url = self.config.get("ha_url", DEFAULT_HA_URL).rstrip("/")
        self.ha_token = self.config.get("ha_token", "")
        self.webhook_url = self.config.get("webhook_url", "")
        self.areas: List[Dict[str, Any]] = []
        self.entities: Dict[str, Dict[str, Any]] = {}
        self.entity_lookup: Dict[str, str] = {}
        self.last_sync_time: float = 0.0

        # Auto-discover local HA token if unconfigured
        if not self.ha_token and os.path.exists(HA_TOKEN_FILE):
            try:
                with open(HA_TOKEN_FILE, "r", encoding="utf-8") as f:
                    tok = f.read().strip()
                if tok:
                    self.ha_token = tok
                    self.config["ha_token"] = tok
            except Exception:
                pass

        # Try to discover webhook from system MCP config if unconfigured
        if not self.webhook_url and os.path.exists(MCP_CONFIG_PATH):
            try:
                with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                    mcp_data = json.load(f)
                ha_mcp = mcp_data.get("mcpServers", {}).get("homeassistant", {})
                wh = ha_mcp.get("serverUrl") or ha_mcp.get("url")
                if wh:
                    self.webhook_url = wh
                    self.config["webhook_url"] = wh
            except Exception:
                pass

        self._load_local_storage_cache()

    def _load_config(self) -> dict:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "ha_url": DEFAULT_HA_URL,
            "ha_token": "",
            "webhook_url": "http://10.0.0.2:8123/api/webhook/mcp_a58702b889b46c4567c1d420640862d3",
            "jev_enabled": True
        }

    def save_config(
        self,
        ha_url: Optional[str] = None,
        ha_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
        jev_enabled: Optional[bool] = None
    ) -> bool:
        if ha_url is not None:
            self.ha_url = ha_url.rstrip("/")
            self.config["ha_url"] = self.ha_url
        if ha_token is not None:
            self.ha_token = ha_token.strip()
            self.config["ha_token"] = self.ha_token
        if webhook_url is not None:
            self.webhook_url = webhook_url.strip()
            self.config["webhook_url"] = self.webhook_url
        if jev_enabled is not None:
            self.config["jev_enabled"] = bool(jev_enabled)

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self._sync_to_system_mcp_config()
            return True
        except Exception:
            return False

    def check_jev_token_status(self) -> Tuple[bool, str]:
        """Checks whether /s1 has a valid TypeSafe Jev API token configured.
        
        Returns:
            Tuple[bool, str]: (has_token, message)
        """
        token = ""

        # 1. Direct query from system_one_gate if in-process
        try:
            from system_one_gate import get_typesafe_config_state
            ts_state = get_typesafe_config_state()
            token = (ts_state.get("api_key") or "").strip()
        except Exception:
            pass

        # 2. Check config module or environment variable
        if not token:
            try:
                import config
                token = (getattr(config, "TYPESAFE_API_KEY", "") or "").strip()
            except Exception:
                pass

        if not token:
            token = os.getenv("TYPESAFE_API_KEY", "").strip()

        # 3. Read bot .env as reliable local fallback
        if not token:
            bot_env = "/home/jiang/github/antigravity-feishu-bot/.env"
            if os.path.exists(bot_env):
                try:
                    with open(bot_env, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("TYPESAFE_API_KEY="):
                                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except Exception:
                    pass

        if not token or token.lower() in ("none", "null", "your_api_key_here"):
            return False, "未配置 TypeSafe Token（/s1 缺失 API Key）"

        return True, "已正确配置 TypeSafe Token"

    def is_jev_enabled(self) -> bool:
        """Returns True only when /s1 has a token AND jev_enabled is True."""
        has_token, _ = self.check_jev_token_status()
        if not has_token:
            return False
        return self.config.get("jev_enabled", True)

    def _sync_to_system_mcp_config(self):
        """Automatically registers/updates Home Assistant in ~/.gemini/config/mcp_config.json."""
        try:
            os.makedirs(os.path.dirname(MCP_CONFIG_PATH), exist_ok=True)
            mcp_data = {"mcpServers": {}}
            if os.path.exists(MCP_CONFIG_PATH):
                try:
                    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                        mcp_data = json.load(f)
                except Exception:
                    mcp_data = {"mcpServers": {}}
            
            mcp_data.setdefault("mcpServers", {})
            if self.webhook_url:
                mcp_data["mcpServers"]["homeassistant"] = {
                    "serverUrl": self.webhook_url
                }
            elif self.ha_token and self.ha_url:
                mcp_data["mcpServers"]["homeassistant"] = {
                    "serverUrl": f"{self.ha_url}/api/webhook/mcp_a58702b889b46c4567c1d420640862d3"
                }

            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(mcp_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_local_storage_cache(self):
        """Parses local core.area_registry, core.device_registry and core.entity_registry for zero-latency initial load."""
        area_map = {}
        self.areas.clear()
        if os.path.exists(HA_STORAGE_AREA):
            try:
                with open(HA_STORAGE_AREA, "r", encoding="utf-8") as f:
                    areas_raw = json.load(f).get("data", {}).get("areas", [])
                for a in areas_raw:
                    aid = a.get("id", "")
                    aname = a.get("name", aid)
                    if aid and aname:
                        area_map[aid] = aname
                        self.areas.append({"id": aid, "name": aname})
            except Exception:
                pass

        device_area_map = {}
        if os.path.exists(HA_STORAGE_DEVICE):
            try:
                with open(HA_STORAGE_DEVICE, "r", encoding="utf-8") as f:
                    devices_raw = json.load(f).get("data", {}).get("devices", [])
                for d in devices_raw:
                    did = d.get("id")
                    daid = d.get("area_id")
                    if did and daid:
                        device_area_map[did] = daid
            except Exception:
                pass

        if not self.areas:
            self.areas = [
                {"id": "ke_ting", "name": "客厅"},
                {"id": "zhu_wo", "name": "主卧"},
                {"id": "ci_wo", "name": "次卧"},
                {"id": "chu_fang", "name": "厨房"},
                {"id": "ru_hu_xuan_guan", "name": "入户玄关"}
            ]

        if os.path.exists(HA_STORAGE_ENTITY):
            try:
                with open(HA_STORAGE_ENTITY, "r", encoding="utf-8") as f:
                    entities_raw = json.load(f).get("data", {}).get("entities", [])
                for e in entities_raw:
                    eid = e.get("entity_id", "")
                    if not eid:
                        continue
                    domain = eid.split(".")[0]
                    if domain not in ["light", "switch", "climate", "media_player", "sensor", "binary_sensor"]:
                        continue
                    name = e.get("name") or e.get("original_name") or eid
                    dev_id = e.get("device_id")
                    aid = e.get("area_id") or device_area_map.get(dev_id) or "other"
                    aname = area_map.get(aid, "其它区域")

                    self.entities[eid] = {
                        "entity_id": eid,
                        "name": name,
                        "domain": domain,
                        "area_id": aid,
                        "area_name": aname,
                        "state": "off" if domain in ["light", "switch"] else "idle",
                        "attributes": {}
                    }
                    clean_name = name.replace(" ", "").lower()
                    self.entity_lookup[clean_name] = eid
                    if aname and aname != "其它区域":
                        self.entity_lookup[f"{aname}{clean_name}"] = eid
            except Exception:
                pass

        # If cache file exists, merge updated states
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    for eid, val in cached.get("entities", {}).items():
                        if eid in self.entities:
                            self.entities[eid]["state"] = val.get("state", self.entities[eid]["state"])
            except Exception:
                pass

    async def test_connection(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Tests connection to Home Assistant via REST API or MCP Webhook."""
        start_t = time.time()
        info = {
            "ha_url": self.ha_url,
            "has_token": bool(self.ha_token),
            "webhook_url": self.webhook_url
        }

        # 1. Test via REST API if token is available
        if self.ha_token:
            url = f"{self.ha_url}/api/"
            headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}
            try:
                if _HAVE_AIOHTTP:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                            elapsed_ms = int((time.time() - start_t) * 1000)
                            if resp.status == 200:
                                data = await resp.json()
                                info["message"] = data.get("message", "API running")
                                info["latency_ms"] = elapsed_ms
                                return True, f"连通成功 (REST API 响应 {elapsed_ms}ms)", info
                            else:
                                return False, f"HA 返回状态码 {resp.status} (鉴权或配置异常)", info
                else:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        elapsed_ms = int((time.time() - start_t) * 1000)
                        return True, f"连通成功 (REST API 响应 {elapsed_ms}ms)", info
            except Exception as e:
                pass

        # 2. Test via Webhook endpoint
        if self.webhook_url:
            try:
                if _HAVE_AIOHTTP:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(self.webhook_url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                            elapsed_ms = int((time.time() - start_t) * 1000)
                            if resp.status in [200, 405]:
                                info["latency_ms"] = elapsed_ms
                                return True, f"连通成功 (Webhook 响应 {elapsed_ms}ms)", info
                else:
                    req = urllib.request.Request(self.webhook_url)
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        elapsed_ms = int((time.time() - start_t) * 1000)
                        return True, f"连通成功 (Webhook 响应 {elapsed_ms}ms)", info
            except Exception as e:
                return False, f"连接超时或失败: {e}", info

        return False, "未配置有效的 HA Token 或可访问的 Webhook", info

    async def sync_all_states(self) -> Tuple[bool, str]:
        """Queries GET /api/states and refreshes full entity states into memory."""
        if not self.ha_token:
            return False, "尚未配置 Home Assistant 访问令牌 (Token)"

        url = f"{self.ha_url}/api/states"
        headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}
        try:
            if _HAVE_AIOHTTP:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                        if resp.status != 200:
                            return False, f"HA 返回错误码: {resp.status}"
                        states = await resp.json()
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    states = json.loads(resp.read().decode("utf-8"))

            count = 0
            for item in states:
                eid = item.get("entity_id", "")
                if not eid:
                    continue
                domain = eid.split(".")[0]
                if domain not in ["light", "switch", "climate", "media_player", "sensor", "binary_sensor"]:
                    continue

                attrs = item.get("attributes", {})
                name = attrs.get("friendly_name") or eid
                state_val = item.get("state", "unknown")

                if eid not in self.entities:
                    self.entities[eid] = {
                        "entity_id": eid,
                        "name": name,
                        "domain": domain,
                        "area_id": "other",
                        "area_name": "其它区域",
                        "state": state_val,
                        "attributes": attrs
                    }
                else:
                    self.entities[eid]["state"] = state_val
                    self.entities[eid]["name"] = name
                    self.entities[eid]["attributes"] = attrs

                clean_name = name.replace(" ", "").lower()
                self.entity_lookup[clean_name] = eid
                count += 1

            self.last_sync_time = time.time()
            self._save_cache()
            return True, f"成功同步全屋 {count} 处智能硬件状态"
        except Exception as e:
            return False, f"同步异常: {e}"

    def _save_cache(self):
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "last_sync": self.last_sync_time,
                    "entities": self.entities
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    async def call_service(self, domain: str, service: str, entity_id: str, service_data: Optional[dict] = None) -> Tuple[bool, str]:
        """Calls Home Assistant service via REST API with sub-50ms latency."""
        payload = {"entity_id": entity_id}
        if service_data:
            payload.update(service_data)

        # 1. Direct REST service call
        if self.ha_token:
            url = f"{self.ha_url}/api/services/{domain}/{service}"
            headers = {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}
            try:
                body_bytes = json.dumps(payload).encode("utf-8")
                if _HAVE_AIOHTTP:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, data=body_bytes, headers=headers, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                            if resp.status in [200, 201]:
                                if entity_id in self.entities:
                                    if service in ["turn_on", "toggle"]:
                                        self.entities[entity_id]["state"] = "on"
                                    elif service in ["turn_off"]:
                                        self.entities[entity_id]["state"] = "off"
                                return True, "执行成功"
                            else:
                                return False, f"HA 执行返回码 {resp.status}"
                else:
                    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        if resp.status in [200, 201]:
                            return True, "执行成功"
            except Exception as e:
                return False, f"服务调用异常: {e}"

        # 2. Webhook / MCP fallback
        if self.webhook_url:
            try:
                rpc_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "call_service",
                        "arguments": {
                            "domain": domain,
                            "service": service,
                            "target": {"entity_id": entity_id}
                        }
                    },
                    "id": int(time.time() * 1000)
                }
                data_bytes = json.dumps(rpc_payload).encode("utf-8")
                req = urllib.request.Request(self.webhook_url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    return True, "执行成功 (via Webhook)"
            except Exception as e:
                return False, f"Webhook 调用异常: {e}"

        return False, "未配置 HA Token 或有效 Webhook"

    async def toggle_device(self, entity_id: str) -> Tuple[bool, str]:
        """Toggles a device switch or light state."""
        domain = entity_id.split(".")[0]
        cur_state = self.entities.get(entity_id, {}).get("state", "off")

        if domain in ["light", "switch", "input_boolean"]:
            service = "turn_off" if cur_state == "on" else "turn_on"
            res, msg = await self.call_service(domain, service, entity_id)
            if res and entity_id in self.entities:
                self.entities[entity_id]["state"] = "off" if cur_state == "on" else "on"
            return res, msg
        elif domain == "climate":
            service = "turn_off" if cur_state != "off" else "turn_on"
            return await self.call_service(domain, service, entity_id)
        elif domain == "media_player":
            service = "media_play_pause"
            return await self.call_service(domain, service, entity_id)

        return await self.call_service(domain, "toggle", entity_id)

    def get_devices_by_area(self, area_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns list of devices and sensors filtered by area_id."""
        res = []
        for e in self.entities.values():
            domain = e.get("domain", "")
            if domain not in ["light", "switch", "climate", "media_player", "sensor", "binary_sensor"]:
                continue
            if not area_id or area_id == "all" or e.get("area_id") == area_id:
                res.append(e)
        return res

    def get_all_areas_status(self) -> Dict[str, Any]:
        """Calculates rich, real-time status summary for all areas and the whole house."""
        whole_home = {
            "total_devices": len(self.entities),
            "lights_total": 0,
            "lights_on": 0,
            "switches_total": 0,
            "switches_on": 0,
            "climates_total": 0,
            "climates_active": 0,
            "avg_temp": None,
            "avg_humidity": None
        }

        area_data = {}
        for a in self.areas:
            aid = a["id"]
            area_data[aid] = {
                "id": aid,
                "name": a["name"],
                "lights_total": 0,
                "lights_on": 0,
                "on_light_names": [],
                "switches_total": 0,
                "switches_on": 0,
                "climates": [],
                "temps": [],
                "humidity": [],
                "sensors_active": []
            }

        all_temps = []
        all_humids = []

        for eid, e in self.entities.items():
            aid = e.get("area_id", "other")
            if aid not in area_data:
                continue
            dom = e.get("domain", "")
            state = str(e.get("state", "")).lower()
            attrs = e.get("attributes", {})
            name = e.get("name", eid)

            if dom == "light":
                whole_home["lights_total"] += 1
                area_data[aid]["lights_total"] += 1
                if state == "on":
                    whole_home["lights_on"] += 1
                    area_data[aid]["lights_on"] += 1
                    area_data[aid]["on_light_names"].append(name)
            elif dom == "switch":
                whole_home["switches_total"] += 1
                area_data[aid]["switches_total"] += 1
                if state == "on":
                    whole_home["switches_on"] += 1
                    area_data[aid]["switches_on"] += 1
            elif dom == "climate":
                whole_home["climates_total"] += 1
                is_active = state not in ["off", "unavailable", "idle"]
                if is_active:
                    whole_home["climates_active"] += 1
                temp = attrs.get("current_temperature") or attrs.get("temperature")
                mode_desc = f"{state} ({temp}°C)" if temp else state
                if state == "off":
                    mode_desc = f"待机 ({temp}°C)" if temp else "待机"
                area_data[aid]["climates"].append(mode_desc)
            elif dom in ("sensor", "binary_sensor"):
                dev_class = attrs.get("device_class")
                unit = attrs.get("unit_of_measurement")
                if dev_class == "temperature" or unit in ("°C", "℃"):
                    try:
                        v = float(state)
                        if 0 <= v <= 60:
                            area_data[aid]["temps"].append(v)
                            all_temps.append(v)
                    except Exception:
                        pass
                elif dev_class == "humidity" or unit == "%":
                    try:
                        v = float(state)
                        if 0 <= v <= 100:
                            area_data[aid]["humidity"].append(v)
                            all_humids.append(v)
                    except Exception:
                        pass
                elif dev_class in ("motion", "occupancy", "presence") and state == "on":
                    area_data[aid]["sensors_active"].append(f"有人移动({name})")
                elif dev_class in ("door", "window", "opening") and state == "on":
                    area_data[aid]["sensors_active"].append(f"打开({name})")

        if all_temps:
            whole_home["avg_temp"] = round(sum(all_temps) / len(all_temps), 1)
        if all_humids:
            whole_home["avg_humidity"] = int(sum(all_humids) / len(all_humids))

        return {
            "whole_home": whole_home,
            "areas": area_data
        }

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates total devices and active devices count."""
        st = self.get_all_areas_status()
        wh = st["whole_home"]
        return {
            "total": wh["total_devices"],
            "total_on": wh["lights_on"] + wh["switches_on"] + wh["climates_active"],
            "lights_on": wh["lights_on"],
            "lights_total": wh["lights_total"],
            "switches_on": wh["switches_on"],
            "switches_total": wh["switches_total"],
            "climates_active": wh["climates_active"],
            "climates_total": wh["climates_total"],
            "avg_temp": wh["avg_temp"],
            "avg_humidity": wh["avg_humidity"]
        }

    def match_entity_from_text(self, text: str) -> Optional[Tuple[str, str]]:
        """Matches entity_id and action (turn_on/turn_off) from natural text in <0.5ms."""
        clean = text.replace(" ", "").lower()
        action = "turn_on"
        if any(w in clean for w in ["关", "闭", "灭", "停"]):
            action = "turn_off"

        # Check exact lookup
        for name, eid in self.entity_lookup.items():
            if name in clean:
                return eid, action

        # Fuzzy check: area + device type (e.g. 客厅灯)
        for a in self.areas:
            aname = a["name"]
            if aname in clean:
                for eid, edata in self.entities.items():
                    if edata.get("area_id") == a["id"] or edata.get("area_name") == aname:
                        ename = edata.get("name", "").lower()
                        domain = edata.get("domain", "")
                        if "灯" in clean and (domain == "light" or "灯" in ename):
                            return eid, action
                        if "空调" in clean and (domain == "climate" or "空调" in ename):
                            return eid, action
                        if "开关" in clean and (domain == "switch" or "开关" in ename):
                            return eid, action

        return None


ha_client = HaClient()
