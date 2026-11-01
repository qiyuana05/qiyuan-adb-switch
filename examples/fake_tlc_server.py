#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fake_tlc_server.py —— 车机工程模式认证服务的本地模拟（教程示例）
=====================================================================

用途
----
在**你自己拥有**的车机上，复现"工程模式二级认证"的流程：
笔记本开热点，把认证域名指向本机，用自签证书起 HTTPS 服务，
对 sms / login / authQuery 三个接口返回成功，让车机 UI 允许切换 USB 模式。

背景原理见 ../docs/01-首次开启-工程模式与认证.md。

重要
----
- 只在你拥有或获明确授权的车辆上使用；
- 不要运行在公共网络、公司网络或他人热点上；
- 不要分发本工具给不确定风险的人；
- 本脚本不向车机下发任何内容，只返回固定 JSON。

用法
----
    python fake_tlc_server.py              # 默认：写 hosts + 起 443
    python fake_tlc_server.py --dns        # 额外起迷你 DNS（hosts 不生效时）
    python fake_tlc_server.py --test       # 本机自测三个接口
    python fake_tlc_server.py --cleanup    # 清理 hosts 后退出
    python fake_tlc_server.py --serve-only # 只起服务器，不动 hosts

前置
----
1. Windows + Python 3.8+（标准库即可）；
2. 以管理员身份运行（绑 443、写 hosts）；
3. 关闭 Clash / VPN 等占用 53 或接管 DNS 的软件；
4. 笔记本开热点，车机连接。

证书
----
本目录不附带任何证书。先运行 `bash gen_cert.sh` 生成 server.crt / server.key。
"""

import argparse
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, "fake_tlc_server.log")

DEFAULT_DOMAIN = "spm.auto-pai.com"
DEFAULT_HOTSPOT = "192.168.137.1"

# 教学示例使用占位值。真实抓包里的 appid 不会随本仓库公开；
# 假服务器不校验该字段，填什么都行。
EXAMPLE_APPID = "YOUR_APPID"


def log(msg):
    line = "[{}] {}".format(time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def warn():
    print("=" * 66)
    print("  本工具仅用于作者/车主本人车辆的调试与学习。")
    print("  继续使用即表示你确认：车机归你所有或已获明确授权。")
    print("  不要用于他人车辆、公共网络或任何商业用途。")
    print("=" * 66)


def ok_resp(code="0000", data=""):
    body = {"code": code, "message": "success", "data": data}
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class TlcHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = ""
        if length:
            try:
                raw = self.rfile.read(length).decode("utf-8", "replace")
            except OSError:
                raw = ""

        path = self.path.split("?")[0]
        # 只记录手机号后四位，避免日志留存完整个人信息
        phone = extract_phone(raw)
        log(">>> {} {} 来自 {}（证书校验通过）".format(
            self.command, path, self.client_address[0]))
        if phone:
            log("    请求中的手机号: ***{}".format(phone[-4:]))

        if path.endswith("/tlc/auth/v1/sms"):
            resp = ok_resp(data=phone)
        elif path.endswith("/tlc/auth/v1/login"):
            resp = ok_resp(data=phone)
        elif path.endswith("/tlc/auth/v1/authQuery"):
            resp = ok_resp(data="")
        else:
            resp = ok_resp(code="E99999", data="unknown path")

        log("<<< 返回: {}".format(resp.decode("utf-8", "replace")[:200]))
        self._reply(resp)

    do_POST = _handle
    do_GET = _handle
    do_PUT = _handle

    def log_message(self, *args):
        pass


def extract_phone(body):
    """从 data(JSON 字符串) 里取 phone，仅用于日志展示后四位。"""
    try:
        outer = json.loads(body)
        inner = outer.get("data") or ""
        if isinstance(inner, str) and inner.strip():
            inner = json.loads(inner)
        if isinstance(inner, dict):
            return str(inner.get("phone") or "")
    except (ValueError, TypeError):
        pass
    return ""


# ---------------------------------------------------------------------------
# hosts 管理（仅 Windows）
# ---------------------------------------------------------------------------
def hosts_path():
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                        "System32", "drivers", "etc", "hosts")


def hosts_add(domain, ip):
    if os.name != "nt":
        log("非 Windows 环境，跳过 hosts；请自行处理域名解析")
        return False
    path = hosts_path()
    if not os.path.exists(path):
        log("找不到 hosts 文件: {}".format(path))
        return False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for line in lines:
        if line.strip().startswith("#"):
            continue
        if domain.lower() in line.lower():
            log("hosts 里已有 {}，跳过".format(domain))
            return True
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n{} {}   # fake_tlc_server (temporary)\n".format(ip, domain))
    log("已写入 hosts: {} {}".format(ip, domain))
    return True


def hosts_remove(domain):
    if os.name != "nt":
        return
    path = hosts_path()
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    kept = [ln for ln in lines
            if domain.lower() not in ln.lower() or ln.strip().startswith("#")]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(kept)
    log("已从 hosts 移除 {}".format(domain))


# ---------------------------------------------------------------------------
# 迷你 DNS（hosts 不生效时备用）
# ---------------------------------------------------------------------------
def build_dns_response(query, domain, ip):
    if len(query) < 12:
        return None
    if struct.unpack(">H", query[4:6])[0] != 1:
        return None
    off = 12
    labels = []
    while off < len(query) and query[off] != 0:
        size = query[off]
        if size & 0xC0:
            return None
        if off + 1 + size > len(query):
            return None
        labels.append(query[off + 1:off + 1 + size].decode("ascii", "replace"))
        off += 1 + size
    if off + 5 > len(query):
        return None
    qname = ".".join(labels).lower()
    qtype = struct.unpack(">H", query[off + 1:off + 3])[0]
    if qtype != 1 or not qname.endswith(domain.lower()):
        return None
    header = query[:2] + b"\x81\x80" + query[4:6] + b"\x00\x01\x00\x00\x00\x00"
    answer = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 300, 4) + socket.inet_aton(ip)
    return header + query[12:off + 5] + answer


def dns_server(domain, ip, port=53):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
    except OSError as exc:
        log("DNS :{} 绑定失败: {}（先退出 Clash/VPN，或只用 hosts）".format(port, exc))
        return

    upstream = ("223.5.5.5", 53)
    log("迷你 DNS 已启动 :{}（{} -> {}）".format(port, domain, ip))
    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except OSError:
            continue
        resp = build_dns_response(data, domain, ip)
        if resp:
            sock.sendto(resp, addr)
            log("DNS 劫持: {} -> {}".format(domain, ip))
            continue
        fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        fwd.settimeout(3)
        try:
            fwd.sendto(data, upstream)
            answer, _ = fwd.recvfrom(4096)
            sock.sendto(answer, addr)
        except OSError:
            pass
        finally:
            fwd.close()


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
def self_test(port):
    import urllib.request

    ctx = ssl._create_unverified_context()
    payload = json.dumps({
        "appid": EXAMPLE_APPID,
        "timestamp": str(int(time.time() * 1000)),
        "nonce": "abcdefghijklmnopqrstuvwxyz123456",
        "signVersion": "V2.0",
        "sdkVersion": "1023",
        "data": json.dumps({
            "phone": "13800000000",
            "captcha": "1234",
            "tuid": "TESTTUID0000000000000000000000",
            "vin": "TESTVIN0000000000",
        }),
        "sign": "DEADBEEF",
    }).encode("utf-8")

    ok = True
    for path in ("/tlc/auth/v1/sms", "/tlc/auth/v1/login", "/tlc/auth/v1/authQuery"):
        req = urllib.request.Request(
            "https://127.0.0.1:{}{}".format(port, path),
            data=payload, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
                body = resp.read().decode("utf-8", "replace")
                print(path, "->", body)
                ok = ok and '"code": "0000"' in body
        except Exception as exc:  # noqa: BLE001 - 自测需要打印所有异常
            print(path, "FAILED:", exc)
            ok = False
    print("自测{}".format("通过 ✓" if ok else "失败 ✗"))


def main():
    parser = argparse.ArgumentParser(description="本地模拟车机认证服务（教程示例）")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--cert", default=os.path.join(BASE, "server.crt"))
    parser.add_argument("--key", default=os.path.join(BASE, "server.key"))
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--hotspot", default=DEFAULT_HOTSPOT)
    parser.add_argument("--no-hosts", action="store_true")
    parser.add_argument("--serve-only", action="store_true")
    parser.add_argument("--dns", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    if args.cleanup:
        hosts_remove(args.domain)
        return
    if args.test:
        self_test(args.port)
        return

    warn()

    if not os.path.exists(args.cert) or not os.path.exists(args.key):
        log("找不到证书: {} / {}".format(args.cert, args.key))
        log("请先运行: bash gen_cert.sh")
        sys.exit(1)

    if not args.serve_only and not args.no_hosts:
        hosts_add(args.domain, args.hotspot)

    if args.dns:
        threading.Thread(target=dns_server,
                         args=(args.domain, args.hotspot), daemon=True).start()

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(args.cert, args.key)

    try:
        server = ThreadingHTTPServer((args.bind, args.port), TlcHandler)
    except OSError as exc:
        log("绑定 {}:{} 失败: {}（443 需要管理员权限）".format(args.bind, args.port, exc))
        sys.exit(1)

    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    log("=" * 60)
    log("  认证服务已启动: https://{}:{}".format(args.bind, args.port))
    log("  目标域名: {}".format(args.domain))
    log("  车机: 工程模式 -> 任意手机号/验证码 -> 登录 -> 切换为 ADB 模式")
    log("  Ctrl+C 停止（会自动清理 hosts）")
    log("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("已停止")
    finally:
        if not args.serve_only and not args.no_hosts:
            hosts_remove(args.domain)


if __name__ == "__main__":
    main()