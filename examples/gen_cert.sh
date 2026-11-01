#!/usr/bin/env bash
# 生成示例用的自签证书（仅用于本地模拟认证服务）
set -euo pipefail

DOMAIN="${1:-spm.auto-pai.com}"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$OUT_DIR"

if [ -f server.crt ] || [ -f server.key ]; then
  echo "server.crt / server.key 已存在，跳过。"
  echo "如需重新生成，先删除这两个文件。"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "未找到 openssl。Windows 可在 Git Bash 中使用，或安装 OpenSSL。" >&2
  exit 1
fi

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout server.key -out server.crt -days 3650 \
  -subj "/CN=${DOMAIN}"

echo
echo "已生成："
echo "  $OUT_DIR/server.crt"
echo "  $OUT_DIR/server.key"
echo
echo "注意："
echo "  - 这是自签证书，只用于本项目的本地模拟；"
echo "  - 不要把 server.key 提交到任何仓库或发给别人；"
echo "  - .gitignore 已排除 *.key / *.crt。"