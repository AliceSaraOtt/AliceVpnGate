import os, sys, time, json, queue, threading, subprocess, urllib.request, urllib.parse, socket, base64, re, shlex, csv, hashlib, random
from typing import Any
from pathlib import Path
import concurrent.futures

from core.config import *
import core.state as state
import core.utils as utils
import core.node_fetcher as node_fetcher
import core.vpn_runner as vpn_runner
import core.node_tester as node_tester
import proxy_server
import vpn_utils

def fetch_api_text_via_proxy(url: str, ptype: str, phost: str, pport: int, use_ssl_verify: bool = True) -> str:
    import socket
    import ssl
    import urllib.parse

    parsed = urllib.parse.urlsplit(url)
    domain = parsed.hostname or "www.vpngate.net"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    is_https = parsed.scheme == "https"
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(12)
    try:
        s.connect((phost, pport))
        if ptype == "socks":
            # SOCKS5 Handshake
            s.sendall(b"\x05\x01\x00")
            resp = s.recv(2)
            if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
                raise RuntimeError("SOCKS5 authentication failed or unsupported")
            # SOCKS5 Connect
            domain_bytes = domain.encode('ascii')
            req = b"\x05\x01\x00\x03" + bytes([len(domain_bytes)]) + domain_bytes + port.to_bytes(2, 'big')
            s.sendall(req)
            resp = s.recv(10)
            if len(resp) < 4 or resp[1] != 0:
                raise RuntimeError("SOCKS5 connection request rejected")
            # If HTTPS, wrap socket with SSL
            if is_https:
                ctx = ssl.create_default_context() if use_ssl_verify else ssl._create_unverified_context()
                s = ctx.wrap_socket(s, server_hostname=domain)
        else: # http proxy
            if is_https:
                # HTTP CONNECT tunnel
                req_str = f"CONNECT {domain}:{port} HTTP/1.1\r\nHost: {domain}:{port}\r\nUser-Agent: Mozilla/5.0 vpngate-openvpn-manager/2.0\r\nProxy-Connection: Keep-Alive\r\n\r\n"
                s.sendall(req_str.encode('ascii'))
                resp = s.recv(4096)
                if not (b"200" in resp or b"established" in resp.lower() or b"ok" in resp.lower()):
                    raise RuntimeError(f"HTTP CONNECT tunnel failed: {resp.decode('utf-8', errors='replace')}")
                # Wrap socket with SSL
                ctx = ssl.create_default_context() if use_ssl_verify else ssl._create_unverified_context()
                s = ctx.wrap_socket(s, server_hostname=domain)
            else:
                # Direct HTTP request through proxy: request URI must be absolute
                pass

        # Send HTTP GET request
        if ptype == "http" and not is_https:
            request_uri = url
        else:
            request_uri = path
            
        req_headers = (
            f"GET {request_uri} HTTP/1.1\r\n"
            f"Host: {domain}\r\n"
            f"User-Agent: Mozilla/5.0 vpngate-openvpn-manager/2.0\r\n"
            f"Accept: text/plain,*/*\r\n"
            f"Connection: close\r\n\r\n"
        )
        s.sendall(req_headers.encode('utf-8'))

        # Read response
        response_data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if len(response_data) > 10 * 1024 * 1024: # max 10MB safety guard
                break
    finally:
        try:
            s.close()
        except Exception:
            pass

    # Parse HTTP response
    header_end = response_data.find(b"\r\n\r\n")
    if header_end == -1:
        raise RuntimeError("Invalid HTTP response format")
    
    headers_part = response_data[:header_end].decode('utf-8', errors='replace')
    body_part = response_data[header_end+4:]

    # Check for HTTP status code
    lines = headers_part.splitlines()
    if not lines:
        raise RuntimeError("Empty response headers")
    status_line = lines[0]
    status_parts = status_line.split()
    if len(status_parts) >= 2:
        try:
            status_code = int(status_parts[1])
            if status_code != 200:
                raise RuntimeError(f"HTTP Server returned status {status_code}: {status_line}")
        except ValueError:
            pass

    # Handle chunked transfer encoding
    is_chunked = False
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip().lower() == "transfer-encoding" and "chunked" in v.lower():
                is_chunked = True
                break

    if is_chunked:
        decoded = b""
        idx = 0
        while idx < len(body_part):
            c_end = body_part.find(b"\r\n", idx)
            if c_end == -1:
                break
            chunk_size_str = body_part[idx:c_end].split(b";")[0].strip()
            try:
                chunk_size = int(chunk_size_str, 16)
            except ValueError:
                break
            if chunk_size == 0:
                break
            idx = c_end + 2
            decoded += body_part[idx : idx + chunk_size]
            idx += chunk_size + 2
        body_part = decoded

    return body_part.decode('utf-8', errors='replace')

def fetch_api_text(url: str | None = None, use_ssl_verify: bool = True) -> str:
    if url is None:
        url = API_URL
    
    ptype, phost, pport = vpn_utils.get_upstream_proxy()
    if ptype and phost and pport:
        try:
            print(f"[fetch_api_text] 监测到上游代理 ({ptype}://{phost}:{pport})，尝试通过代理获取 API...", flush=True)
            return fetch_api_text_via_proxy(url, ptype, phost, pport, use_ssl_verify)
        except Exception as e:
            print(f"[fetch_api_text] 通过代理获取 API 失败: {e}，尝试使用直连/默认系统代理...", flush=True)
            log_to_json("WARNING", "Main", f"使用代理 {ptype}://{phost}:{pport} 获取 API 失败: {e}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 vpngate-openvpn-manager/2.0",
            "Accept": "text/plain,*/*",
        },
    )
    if url.startswith("https://") and not use_ssl_verify:
        import ssl
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=12, context=ctx) as response:
            return response.read().decode("utf-8", errors="replace")
    else:
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.read().decode("utf-8", errors="replace")

def parse_vpngate_rows(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line and not line.startswith("*")]
    if lines and lines[0].startswith("#"):
        lines[0] = lines[0][1:]
    return list(csv.DictReader(lines))

def decode_config(encoded: str) -> str:
    return base64.b64decode(encoded.encode("ascii"), validate=False).decode("utf-8", errors="replace")

def load_blacklist() -> dict[str, dict[str, Any]]:
    return {}

def mark_blacklisted(node: dict[str, Any], message: str) -> None:
    pass

def row_to_node(row: dict[str, str], config_text: str) -> dict[str, Any]:
    ip = row.get("IP", "")
    country_short = row.get("CountryShort", "")
    remote_host, remote_port, proto = vpn_utils.parse_remote(config_text, ip)
    node_id = safe_name("_".join([country_short or "XX", ip or remote_host, str(remote_port), proto]))
    config_path = CONFIG_DIR / f"{node_id}.ovpn"
    
    country_long = row.get("CountryLong", "")
    country_zh = vpn_utils.COUNTRY_TRANSLATIONS.get(country_long, vpn_utils.COUNTRY_TRANSLATIONS.get(country_long.strip(), country_long))
    return {
        "id": node_id,
        "country": country_zh,
        "country_short": country_short,
        "host_name": row.get("HostName", ""),
        "ip": ip,
        "score": parse_int(row.get("Score")),
        "ping": parse_int(row.get("Ping")),
        "speed": parse_int(row.get("Speed")),
        "sessions": parse_int(row.get("NumVpnSessions")),
        "owner": "",
        "asn": "",
        "as_name": "",
        "location": "",
        "ip_type": "",
        "quality": "",
        "latency_ms": 0,
        "config_file": str(config_path),
        "config_text": config_text,
        "proto": proto,
        "remote_host": remote_host,
        "remote_port": remote_port,
        "fetched_at": time.time(),
        "probe_status": "not_checked",
        "probe_message": "",
        "probed_at": 0,
    }

def fetch_candidates() -> list[dict[str, Any]]:
    blacklist = load_blacklist()
    candidates: list[dict[str, Any]] = []
    seen_ips = set()
    
    # 检查本地是否有节点缓存，以确定最大重试尝试次数
    has_cache = len(cached_nodes()) > 0
    max_attempts = 1 if has_cache else 2
    
    # 尝试 URLs 队列: 1. HTTPS(验证证书) 2. HTTPS(不验证证书) 3. HTTP
    attempts_targets = [
        (API_URL, True),
        (API_URL, False)
    ]
    if API_URL.startswith("https://"):
        attempts_targets.append((API_URL.replace("https://", "http://"), True))
        
    log_to_json("INFO", "Main", "开始拉取官方 API 节点列表...")
    
    last_err = None
    for url, verify_ssl in attempts_targets:
        for i in range(max_attempts):
            if i > 0:
                time.sleep(1.5)
            try:
                msg = f"尝试拉取 {url} (SSL验证: {verify_ssl}, 第 {i+1} 次尝试)..."
                print(f"[fetch_candidates] {msg}", flush=True)
                log_to_json("INFO", "Main", msg)
                api_text = fetch_api_text(url, verify_ssl)
                rows = parse_vpngate_rows(api_text)
                for row in rows[:MAX_SCAN_ROWS]:
                    ip = row.get("IP", "")
                    if not ip or ip in seen_ips:
                        continue
                    encoded = row.get("OpenVPN_ConfigData_Base64", "")
                    if not encoded:
                        continue
                    config_text = decode_config(encoded)
                    node = row_to_node(row, config_text)
                    candidates.append(node)
                    seen_ips.add(ip)
                if candidates:
                    break
            except Exception as e:
                last_err = e
                print(f"[fetch_candidates] 拉取失败 (URL: {url}, 验证: {verify_ssl}): {e}", flush=True)
                log_to_json("WARNING", "Main", f"拉取失败 (URL: {url}, 验证: {verify_ssl}): {e}")
        if candidates:
            break
            
    if not candidates:
        err_code, diag_msg = vpn_utils.diagnose_api_failure(API_URL)
        full_err_msg = f"获取官方 API 节点最终失败: {last_err} | 诊断结果: {diag_msg}"
        print(f"[错误代码 {err_code}] {full_err_msg}", flush=True)
        log_to_json("ERROR", "Main", f"[错误代码 {err_code}] {full_err_msg}")
        set_state(
            last_fetch_status="error",
            last_fetch_error_code=err_code,
            last_fetch_message=diag_msg
        )
        if last_err:
            raise RuntimeError(diag_msg) from last_err
        else:
            raise RuntimeError(diag_msg)
                
    set_state(
        last_fetch_at=time.time(),
        last_fetch_status="ok",
        last_fetch_message=f"Fetched {len(candidates)} unique candidates across multiple attempts.",
        blacklisted_nodes=len(blacklist),
    )
    log_to_json("INFO", "Main", f"成功获取官方 API 节点，共 {len(candidates)} 个候选节点")
    return candidates

def cached_nodes() -> list[dict[str, Any]]:
    return read_json(NODES_FILE, [])

_openvpn_version = None

