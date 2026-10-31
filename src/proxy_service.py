import json
import os
import re
import socket
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote
import yaml


INVALID_NODE_PATTERNS = (
    "traffic:",
    "expire:",
    "剩余流量",
    "套餐到期",
    "距离下次",
    "官网",
    "重置",
    "direct",
    "reject",
    "compatible",
    "pass",
    "自动选择",
    "故障转移",
    "负载均衡",
)

COMMON_GROUP_NAMES = {
    "GLOBAL",
    "Proxies",
    "Proxy",
    "节点选择",
    "🔰 节点选择",
    "🚀 节点选择",
    "OpenAI",
    "ChatGPT",
    "AI",
    "Google",
    "YouTube",
    "Netflix",
    "Disney",
    "Bilibili",
    "Spotify",
    "Steam",
    "Telegram",
    "Microsoft",
    "PayPal",
    "Apple",
    "Final",
    "漏网之鱼",
    "HK",
    "JP",
    "SG",
    "TW",
    "US",
    "KR",
    "UK",
    "DE",
}


def is_valid_proxy_node_name(name: str, extra_group_names: set[str] | None = None) -> bool:
    if not name or not name.strip():
        return False
    s = name.strip()
    if s in COMMON_GROUP_NAMES:
        return False
    if extra_group_names and s in extra_group_names:
        return False
    low = s.lower()
    for pat in INVALID_NODE_PATTERNS:
        if pat in low:
            return False
    return True


def classify_node_region(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ("singapore", "新加坡", "狮城")) or "🇸🇬" in name or re.search(r"\bSG\b", name):
        return "🇸🇬 新加坡 (SG)"
    if any(k in low for k in ("united states", "america", "美国", "洛杉矶", "圣何塞", "西雅图", "硅谷")) or "🇺🇸" in name or re.search(r"\bUS\b", name):
        return "🇺🇸 美国 (US)"
    if any(k in low for k in ("japan", "日本", "东京", "大阪")) or "🇯🇵" in name or re.search(r"\bJP\b", name):
        return "🇯🇵 日本 (JP)"
    if any(k in low for k in ("taiwan", "台湾", "台北", "新北")) or "🇹🇼" in name or "🇨🇳" in name or re.search(r"\bTW\b", name):
        return "🇨🇳 台湾 (TW)"
    if any(k in low for k in ("hong kong", "hongkong", "香港")) or "🇭🇰" in name or re.search(r"\bHK\b", name):
        return "🇭🇰 香港 (HK)"
    if any(k in low for k in ("korea", "韩国", "首尔")) or "🇰🇷" in name or re.search(r"\bKR\b", name):
        return "🇰🇷 韩国 (KR)"
    return "🌍 其他地区"


def get_system_proxy() -> dict:
    """Detect system proxy across Windows, macOS, and environment variables."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                srv = str(server or "").strip()
                # Handle "http=127.0.0.1:7890;https=127.0.0.1:7890" format
                if "=" in srv:
                    for part in srv.split(";"):
                        if part.startswith("http="):
                            srv = part.split("=", 1)[1]
                            break
                    else:
                        srv = srv.split("=", 1)[-1].split(";")[0]
                return {"enabled": bool(enabled), "server": srv}
        except Exception:
            pass

    for env_key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            cleaned = re.sub(r"^[a-zA-Z0-9]+://", "", val).strip("/")
            return {"enabled": True, "server": cleaned}

    return {"enabled": False, "server": ""}


# Keep backward-compatible alias
get_windows_system_proxy = get_system_proxy


def _is_local_port_open(port: int, timeout: float = 0.08) -> bool:
    if not (1 <= int(port) <= 65535):
        return False
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def find_clash_config_files() -> list[tuple[str, Path]]:
    """Discover Clash / Mihomo config files across mainstream clients on Windows, macOS, and Linux."""
    appdata = Path(os.environ.get("APPDATA", "")) if os.environ.get("APPDATA") else Path.home()
    localappdata = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else Path.home()
    home = Path.home()

    candidates: list[tuple[str, Path]] = [
        # Clash Verge Rev / Clash Verge
        ("Clash Verge Rev", appdata / "io.github.clash-verge-rev.clash-verge-rev" / "clash-verge.yaml"),
        ("Clash Verge Rev", appdata / "io.github.clash-verge-rev.clash-verge-rev" / "config.yaml"),
        ("Clash Verge", appdata / "clash-verge" / "clash-verge.yaml"),
        ("Clash Verge", home / ".config" / "clash-verge" / "clash-verge.yaml"),
        ("Clash Verge Rev", home / "Library" / "Application Support" / "io.github.clash-verge-rev.clash-verge-rev" / "clash-verge.yaml"),
        # Mihomo Party / Clash Party
        ("Mihomo Party", appdata / "mihomo-party" / "work" / "config.yaml"),
        ("Mihomo Party", home / ".config" / "mihomo-party" / "work" / "config.yaml"),
        ("Mihomo Party", home / "Library" / "Application Support" / "mihomo-party" / "work" / "config.yaml"),
        # Clash Nyanpasu
        ("Clash Nyanpasu", appdata / "clash-nyanpasu" / "clash-config.yaml"),
        ("Clash Nyanpasu", home / ".config" / "clash-nyanpasu" / "clash-config.yaml"),
        # FlClash
        ("FlClash", appdata / "com.follow" / "FlClash" / "config.yaml"),
        ("FlClash", localappdata / "FlClash" / "config.yaml"),
        # Clash for Windows / Classic Clash / Mihomo
        ("Clash / Mihomo", home / ".config" / "clash" / "config.yaml"),
        ("Clash / Mihomo", home / ".config" / "mihomo" / "config.yaml"),
        ("Clash Meta", home / ".config" / "clash.meta" / "config.yaml"),
    ]
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for client_name, path in candidates:
        try:
            if path.exists() and path.is_file():
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    found.append((client_name, path))
        except Exception:
            continue
    return found


def find_clash_verge_yaml() -> Path | None:
    found = find_clash_config_files()
    return found[0][1] if found else None


def parse_clash_yaml_summary(yaml_path: str | Path) -> dict:
    p = Path(yaml_path)
    if not p.exists():
        return {"mixed_port": 0, "secret": "", "external_controller": "", "ports": [], "nodes": []}

    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    mixed_port = int(data.get("mixed-port") or data.get("port") or 0)
    socks_port = int(data.get("socks-port") or 0)
    secret = str(data.get("secret") or "")
    ext_ctrl = str(data.get("external-controller") or "").strip()

    ports = []
    if mixed_port:
        ports.append(
            {
                "port": mixed_port,
                "url": f"http://127.0.0.1:{mixed_port}",
                "label": f"127.0.0.1:{mixed_port} (主混合端口 · 支持全节点切换)",
                "bound_group": "",
            }
        )
    elif socks_port:
        ports.append(
            {
                "port": socks_port,
                "url": f"socks5://127.0.0.1:{socks_port}",
                "label": f"socks5://127.0.0.1:{socks_port} (SOCKS5 代理端口)",
                "bound_group": "",
            }
        )

    for lst in data.get("listeners") or []:
        if not isinstance(lst, dict):
            continue
        lport = lst.get("port")
        lname = lst.get("name") or "listener"
        lproxy = lst.get("proxy") or ""
        ltype = str(lst.get("type") or "mixed").lower()
        if lport:
            scheme = "socks5" if "socks" in ltype else "http"
            ports.append(
                {
                    "port": int(lport),
                    "url": f"{scheme}://127.0.0.1:{int(lport)}",
                    "label": f"127.0.0.1:{int(lport)} ({lname} · 绑定 {lproxy or '默认'} 组)",
                    "bound_group": lproxy,
                }
            )

    group_names_in_yaml = {
        str(g.get("name") or "").strip()
        for g in (data.get("proxy-groups") or [])
        if isinstance(g, dict) and g.get("name")
    }

    nodes = []
    seen = set()
    for px in data.get("proxies") or []:
        if not isinstance(px, dict):
            continue
        nname = str(px.get("name") or "").strip()
        if not is_valid_proxy_node_name(nname, group_names_in_yaml) or nname in seen:
            continue
        seen.add(nname)
        nodes.append(
            {
                "name": nname,
                "type": str(px.get("type") or ""),
                "region": classify_node_region(nname),
                "delay": None,
            }
        )

    return {
        "mixed_port": mixed_port,
        "secret": secret,
        "external_controller": ext_ctrl,
        "ports": ports,
        "nodes": nodes,
    }


def find_active_mihomo_pipe() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        pipes = [
            f"\\\\.\\pipe\\{name}"
            for name in os.listdir(r"\\.\pipe")
            if any(k in name.lower() for k in ("verge-mihomo", "mihomo", "clash"))
        ]
        return pipes[0] if pipes else None
    except Exception:
        return None


def _request_mihomo_pipe(
    pipe_path: str,
    method: str,
    path: str,
    secret: str = "",
    body_dict: dict | None = None,
) -> tuple[int, dict | None]:
    body_bytes = json.dumps(body_dict, ensure_ascii=False).encode("utf-8") if body_dict is not None else b""
    headers = [
        f"{method} {path} HTTP/1.1",
        "Host: localhost",
        f"Authorization: Bearer {secret}",
        "Content-Type: application/json",
        f"Content-Length: {len(body_bytes)}",
        "Connection: close",
        "",
        "",
    ]
    req_bytes = "\r\n".join(headers).encode("utf-8") + body_bytes

    with open(pipe_path, "r+b", buffering=0) as f:
        f.write(req_bytes)
        raw_resp = f.read()

    header_b, _, resp_body_b = raw_resp.partition(b"\r\n\r\n")
    header_str = header_b.decode("utf-8", errors="ignore")
    first_line = header_str.splitlines()[0] if header_str else ""
    m_code = re.search(r"HTTP/\d\.\d\s+(\d+)", first_line)
    status_code = int(m_code.group(1)) if m_code else 0

    if not resp_body_b or status_code == 204:
        return status_code, {}

    if "transfer-encoding: chunked" in header_str.lower():
        pos = 0
        out = bytearray()
        while pos < len(resp_body_b):
            line_end = resp_body_b.find(b"\r\n", pos)
            if line_end == -1:
                break
            size_str = resp_body_b[pos:line_end].strip()
            if not size_str:
                pos = line_end + 2
                continue
            size = int(size_str, 16)
            if size == 0:
                break
            start = line_end + 2
            out.extend(resp_body_b[start : start + size])
            pos = start + size + 2
        json_str = out.decode("utf-8", errors="ignore")
    else:
        json_str = resp_body_b.decode("utf-8", errors="ignore")

    try:
        return status_code, json.loads(json_str)
    except Exception:
        return status_code, None


def _request_http_controller(
    base_url: str,
    method: str,
    path: str,
    secret: str = "",
    body_dict: dict | None = None,
) -> tuple[int, dict | None]:
    url = base_url.rstrip("/") + path
    body_bytes = json.dumps(body_dict, ensure_ascii=False).encode("utf-8") if body_dict is not None else None
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    if body_bytes is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw or status == 204:
                return status, {}
            return status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def _discover_controller(summary: dict) -> tuple[str, str, str]:
    """Return (mode, endpoint, secret) where mode is 'pipe', 'http', or ''."""
    secret = summary.get("secret", "")
    pipe_path = find_active_mihomo_pipe()
    if pipe_path:
        return ("pipe", pipe_path, secret)

    ext_ctrl = summary.get("external_controller", "")
    http_candidates = []
    if ext_ctrl:
        host_port = ext_ctrl if ":" in ext_ctrl else f"127.0.0.1:{ext_ctrl}"
        if host_port.startswith(":"):
            host_port = "127.0.0.1" + host_port
        if host_port.startswith("0.0.0.0:"):
            host_port = "127.0.0.1:" + host_port.split(":", 1)[1]
        http_candidates.append(f"http://{host_port}")

    for default_port in (9090, 9097, 19090, 6170):
        u = f"http://127.0.0.1:{default_port}"
        if u not in http_candidates and _is_local_port_open(default_port):
            http_candidates.append(u)

    for base_url in http_candidates:
        code, data = _request_http_controller(base_url, "GET", "/proxies", secret=secret)
        if code == 200 and isinstance(data, dict) and "proxies" in data:
            return ("http", base_url, secret)

    return ("", "", secret)


def _call_controller(
    mode: str,
    endpoint: str,
    secret: str,
    method: str,
    path: str,
    body_dict: dict | None = None,
) -> tuple[int, dict | None]:
    if mode == "pipe":
        return _request_mihomo_pipe(endpoint, method, path, secret=secret, body_dict=body_dict)
    if mode == "http":
        return _request_http_controller(endpoint, method, path, secret=secret, body_dict=body_dict)
    return 0, None


def detect_proxy_environment() -> dict:
    sys_proxy = get_system_proxy()
    configs = find_clash_config_files()
    client_label = configs[0][0] if configs else ""
    yaml_path = configs[0][1] if configs else None
    summary = (
        parse_clash_yaml_summary(yaml_path)
        if yaml_path
        else {"mixed_port": 0, "secret": "", "external_controller": "", "ports": [], "nodes": []}
    )

    # Ensure system proxy port is in the ports list if not already present
    if sys_proxy["server"]:
        srv = sys_proxy["server"]
        srv_url = srv if "://" in srv else f"http://{srv}"
        if not any(p["url"] == srv_url for p in summary["ports"]):
            summary["ports"].insert(
                0,
                {
                    "port": 0,
                    "url": srv_url,
                    "label": f"{srv} (系统当前代理端口)",
                    "bound_group": "",
                },
            )

    # Probe common local proxy ports (v2rayN, Clash, Sing-box, Shadowsocks, Nekoray) if ports list is still empty
    if not summary["ports"]:
        common_local_ports = [
            (7890, "http", "Clash / Mihomo 默认混合端口"),
            (7897, "http", "Clash Verge / Meta 默认端口"),
            (17898, "http", "Clash Verge 混合端口"),
            (10809, "http", "v2rayN 默认 HTTP 端口"),
            (10808, "socks5", "v2rayN 默认 SOCKS5 端口"),
            (2080, "http", "Nekoray / Sing-box 默认端口"),
            (1080, "socks5", "Shadowsocks 默认 SOCKS5 端口"),
        ]
        for pt, scheme, desc in common_local_ports:
            if _is_local_port_open(pt):
                summary["ports"].append(
                    {
                        "port": pt,
                        "url": f"{scheme}://127.0.0.1:{pt}",
                        "label": f"127.0.0.1:{pt} ({desc})",
                        "bound_group": "",
                    }
                )

    mode, endpoint, secret = _discover_controller(summary)
    controller_online = bool(mode)
    current_groups = {}

    if controller_online:
        try:
            code, data = _call_controller(mode, endpoint, secret, "GET", "/proxies")
            if code == 200 and data and "proxies" in data:
                px_map = data["proxies"]
                all_group_names = {
                    k for k, v in px_map.items() if isinstance(v, dict) and isinstance(v.get("all"), list)
                }

                # Record current selected node for all Selector groups dynamically
                for gname, gobj in px_map.items():
                    if isinstance(gobj, dict) and gobj.get("type") in ("Selector", "Fallback", "URLTest"):
                        if gobj.get("now"):
                            current_groups[gname] = gobj["now"]

                # If YAML didn't list individual nodes (e.g. subscription loaded via provider/profile),
                # dynamically extract real proxy nodes from the controller's /proxies API!
                existing_names = {n["name"] for n in summary["nodes"]}
                leaf_types = {
                    "ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2",
                    "tuic", "wireguard", "snell", "http", "socks5", "anytls", "ssh",
                }
                for pname, pobj in px_map.items():
                    if not isinstance(pobj, dict):
                        continue
                    ptype = str(pobj.get("type") or "")
                    if ptype.lower() in leaf_types and is_valid_proxy_node_name(pname, all_group_names):
                        if pname not in existing_names:
                            existing_names.add(pname)
                            summary["nodes"].append(
                                {
                                    "name": pname,
                                    "type": ptype,
                                    "region": classify_node_region(pname),
                                    "delay": None,
                                }
                            )

                # Attach live latency (delay ms) to nodes
                for node in summary["nodes"]:
                    live_node = px_map.get(node["name"])
                    if isinstance(live_node, dict) and live_node.get("history"):
                        last_hist = live_node["history"][-1]
                        delay = last_hist.get("delay")
                        if delay and delay > 0:
                            node["delay"] = delay
        except Exception:
            pass

    if not client_label:
        if controller_online:
            client_label = "Clash / Mihomo 内核"
        elif sys_proxy["server"]:
            client_label = f"系统代理 ({sys_proxy['server']})"
        elif summary["ports"]:
            client_label = "本地代理端口"
        else:
            client_label = "未检测到代理客户端 (可手动输入代理地址)"

    return {
        "client_name": client_label,
        "controller_online": controller_online,
        "system_proxy": sys_proxy,
        "ports": summary["ports"],
        "nodes": summary["nodes"],
        "current_groups": current_groups,
    }


def activate_proxy_node(account_type: str, proxy_url: str, node_name: str) -> dict:
    if not node_name or not node_name.strip():
        return {"ok": True, "switched": False}

    configs = find_clash_config_files()
    yaml_path = configs[0][1] if configs else None
    summary = parse_clash_yaml_summary(yaml_path) if yaml_path else {"secret": "", "external_controller": "", "ports": []}
    mode, endpoint, secret = _discover_controller(summary)
    if not mode:
        return {"ok": False, "switched": False, "error": "未检测到 Clash / Mihomo 控制接口，将仅使用代理端口连接"}

    try:
        code, data = _call_controller(mode, endpoint, secret, "GET", "/proxies")
        px_map = (data or {}).get("proxies") or {}

        # Find all Selector groups that directly contain `node_name` in their `all` list
        switched_groups: list[str] = []
        containing_groups: list[str] = []
        for gname, gobj in px_map.items():
            if not isinstance(gobj, dict):
                continue
            if gobj.get("type") == "Selector" and isinstance(gobj.get("all"), list):
                if node_name in gobj["all"]:
                    containing_groups.append(gname)

        # Check if the chosen proxy_url corresponds to a specific listener bound_group
        bound_group = ""
        for p in summary.get("ports") or []:
            if p.get("url") == proxy_url and p.get("bound_group"):
                bound_group = p["bound_group"]
                break

        is_google = (account_type or "").lower() == "google"
        svc_keywords = ("google", "gemini", "youtube") if is_google else ("openai", "chatgpt", "gpt", "ai", "claude")
        main_keywords = ("proxies", "proxy", "节点选择", "选择节点", "global", "默认")

        # 1. Switch any containing regional or main Selector group to `node_name`
        for gname in containing_groups:
            st, _ = _call_controller(
                mode,
                endpoint,
                secret,
                "PUT",
                f"/proxies/{quote(gname)}",
                body_dict={"name": node_name},
            )
            if st in (200, 204):
                switched_groups.append(gname)

        # 2. If there is a service-specific Selector group (e.g. OpenAI / ChatGPT / AI / Google)
        # that doesn't directly list `node_name` (or does list a regional group we just switched),
        # point that service group to `node_name` or to the containing regional group!
        for gname, gobj in px_map.items():
            if not isinstance(gobj, dict) or gobj.get("type") != "Selector":
                continue
            glow = gname.lower()
            if any(k in glow for k in svc_keywords) or (bound_group and gname == bound_group):
                options = gobj.get("all") or []
                target_opt = None
                if node_name in options:
                    target_opt = node_name
                else:
                    for cg in containing_groups:
                        if cg in options and not any(m in cg.lower() for m in main_keywords):
                            target_opt = cg
                            break
                    if not target_opt:
                        for cg in containing_groups:
                            if cg in options:
                                target_opt = cg
                                break
                if target_opt:
                    st, _ = _call_controller(
                        mode,
                        endpoint,
                        secret,
                        "PUT",
                        f"/proxies/{quote(gname)}",
                        body_dict={"name": target_opt},
                    )
                    if st in (200, 204) and gname not in switched_groups:
                        switched_groups.append(gname)

        # Fallback if /proxies didn't return group metadata: try standard group names
        if not switched_groups:
            for fallback_group in ("Proxies", "Proxy", "节点选择", "🔰 节点选择", "🚀 节点选择", "GLOBAL"):
                st, _ = _call_controller(
                    mode,
                    endpoint,
                    secret,
                    "PUT",
                    f"/proxies/{quote(fallback_group)}",
                    body_dict={"name": node_name},
                )
                if st in (200, 204):
                    switched_groups.append(fallback_group)
                    break

        return {
            "ok": True,
            "switched": len(switched_groups) > 0,
            "node": node_name,
            "groups": switched_groups,
        }
    except Exception as e:
        return {"ok": False, "switched": False, "error": str(e)}
