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


import threading
import subprocess
import time

lock = threading.RLock()
active_sessions = {}
active_openvpn_process = None
active_openvpn_node_id = ""
is_connecting = True
last_active_ping_time = 0.0
last_active_latency = 0

last_collector_heartbeat = 0.0
last_checker_heartbeat = 0.0
last_pinger_heartbeat = 0.0
server_start_time = time.time()
def set_state(**updates: Any) -> None:
    state = get_state()
    state.update(updates)
    write_json(STATE_FILE, state)

def get_state() -> dict[str, Any]:
        state = read_json(STATE_FILE, {})
    state["state.active_openvpn_node_id"] = state.active_openvpn_node_id
    state["state.is_connecting"] = state.is_connecting
    state.setdefault("api_url", API_URL)
    state.setdefault("target_valid_nodes", TARGET_VALID_NODES)
    state.setdefault("fetch_interval_seconds", FETCH_INTERVAL_SECONDS)
    state.setdefault("check_interval_seconds", CHECK_INTERVAL_SECONDS)
    _proxy_display = f"[{LOCAL_PROXY_HOST}]" if ":" in LOCAL_PROXY_HOST else LOCAL_PROXY_HOST
    state["local_proxy"] = f"http://{_proxy_display}:{LOCAL_PROXY_PORT}"
    state.setdefault("last_fetch_status", "not_started")
    state.setdefault("last_check_message", "")
    state.setdefault("blacklisted_nodes", 0)
    
    # Pre-populate settings inputs in UI
    ui_cfg = load_ui_config()
    state["username"] = ui_cfg.get("username", "admin")
    state["port"] = ui_cfg.get("port", 9898)
    state["secret_path"] = ui_cfg.get("secret_path", "EJsW2EeBo9lY")
    state["proxy_port"] = ui_cfg.get("proxy_port", 7998)
    state["routing_mode"] = ui_cfg.get("routing_mode", "auto")
    state["force_country"] = ui_cfg.get("force_country", "")
    
    return state

