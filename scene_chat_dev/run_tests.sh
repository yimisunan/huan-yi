#!/usr/bin/env bash
# 维护测试入口：一次跑完 Python 单元测试与 Node 桥接测试。
#   bash scene_chat_dev/run_tests.sh          # 在当前项目目录跑
#   bash scene_chat_dev/run_tests.sh --fast   # 先 rsync 到 /tmp（tmpfs）再跑，约快 20%
# 退出码 = 失败项数量（0 表示全绿）。
set -u

cd "$(dirname "$0")/.." || exit 1

if [ "${1:-}" = "--fast" ]; then
  SHADOW=/tmp/proj-shadow
  rsync -a --delete \
    --exclude .git --exclude .into-backup --exclude .operit \
    --exclude 'scene_chat_dev/artifacts' --exclude 'txt文件/image' \
    ./ "$SHADOW"/ || exit 1
  cd "$SHADOW" || exit 1
fi

# 多个测试用 scene_chat_dev/tmp 做临时目录，被 gitignore，需要保证存在。
mkdir -p scene_chat_dev/tmp

py_ok=0; py_fail=0; js_ok=0; js_fail=0; failed=""

for f in scene_chat_dev/tests/test_*.py; do
  out=$(python -B "$f" 2>&1); rc=$?
  name=$(basename "$f")
  if [ $rc -eq 0 ]; then
    py_ok=$((py_ok + 1)); echo "OK   $name"
  else
    py_fail=$((py_fail + 1)); failed="$failed $name"; echo "FAIL $name"
    echo "$out" | grep -E '^(FAIL|ERROR):' | sed 's/^/       /' | head -8
  fi
done

for f in scene_chat_dev/tests/bridge_*.js; do
  name=$(basename "$f")
  if node "$f" >/dev/null 2>&1; then
    js_ok=$((js_ok + 1)); echo "OK   $name"
  else
    js_fail=$((js_fail + 1)); failed="$failed $name"; echo "FAIL $name"
    node "$f" 2>&1 | tail -4 | sed 's/^/       /'
  fi
done

echo "----"
echo "python: ok=$py_ok fail=$py_fail | node: ok=$js_ok fail=$js_fail"
if [ -n "${failed# }" ]; then
  echo "failed:${failed}"
fi
exit $((py_fail + js_fail))