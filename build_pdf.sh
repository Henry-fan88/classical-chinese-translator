#!/usr/bin/env bash
# 阶段四：用 XeLaTeX 把 output/zongjinglu.tex 编译成 PDF。
# 中文需要 xelatex + ctex；若未安装，先跑 setup_tex.sh。
set -e
cd "$(dirname "$0")/output"

# 把 TinyTeX 加进 PATH（如果用 setup_tex.sh 装的）
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$HOME/.TinyTeX/bin/universal-darwin:$PATH"

if ! command -v xelatex >/dev/null 2>&1; then
  echo "❌ 找不到 xelatex。请先运行：bash setup_tex.sh"
  echo "   或把生成的 output/zongjinglu.tex 上传到 https://www.overleaf.com 直接编译（零安装）。"
  exit 1
fi

echo "▶ 第 1/2 次编译（生成目录）…"
xelatex -interaction=nonstopmode -halt-on-error zongjinglu.tex >/dev/null || {
  echo "编译出错，详见 output/zongjinglu.log"; exit 1; }
echo "▶ 第 2/2 次编译（更新目录页码）…"
xelatex -interaction=nonstopmode -halt-on-error zongjinglu.tex >/dev/null
echo "✅ 完成：output/zongjinglu.pdf"
