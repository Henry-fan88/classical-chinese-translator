#!/usr/bin/env bash
# 在后台启动翻译，可关闭终端继续跑。重复运行会自动续传未完成的部分。
cd "$(dirname "$0")"

if [ -z "$DEEPSEEK_API_KEY" ]; then
  echo "❌ 未设置 API Key。请先执行： export DEEPSEEK_API_KEY=你的key"
  exit 1
fi

# 防止重复启动
if [ -f logs/translate.pid ] && kill -0 "$(cat logs/translate.pid)" 2>/dev/null; then
  echo "⚠️  已有翻译进程在跑 (PID $(cat logs/translate.pid))。先 kill 它再启动。"
  exit 1
fi

mkdir -p logs
nohup ./venv/bin/python translate.py >> logs/translate.log 2>&1 &
echo $! > logs/translate.pid
echo "✅ 后台翻译已启动 (PID $(cat logs/translate.pid))"
echo "   实时进度面板 : ./venv/bin/python monitor.py"
echo "   查看日志     : tail -f logs/translate.log"
echo "   安全停止     : kill $(cat logs/translate.pid)   （已完成进度不会丢，重跑可续传）"
