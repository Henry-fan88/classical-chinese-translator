#!/usr/bin/env bash
# 阶段四：用 XeLaTeX 把 output/<name>.tex 编译成 PDF。
# 中文需要 xelatex + ctex；若未安装，先跑 setup_tex.sh。
#   bash build_pdf.sh                       # 编译 zongjinglu.tex（纯白话）
#   bash build_pdf.sh zongjinglu_bilingual  # 编译对照版
set -e
cd "$(dirname "$0")/output"

NAME="${1:-zongjinglu}"
NAME="${NAME%.tex}"   # 容忍带 .tex 后缀的参数

if [ ! -f "$NAME.tex" ]; then
  echo "❌ 找不到 output/$NAME.tex，请先运行 build_latex.py。"
  exit 1
fi

# 把 TinyTeX 加进 PATH（如果用 setup_tex.sh 装的）
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$HOME/.TinyTeX/bin/universal-darwin:$PATH"

if ! command -v xelatex >/dev/null 2>&1; then
  echo "❌ 找不到 xelatex。请先运行：bash setup_tex.sh"
  echo "   或把生成的 output/$NAME.tex 上传到 https://www.overleaf.com 直接编译（零安装）。"
  exit 1
fi

echo "▶ 第 1/2 次编译（生成目录）…"
xelatex -interaction=nonstopmode -halt-on-error "$NAME.tex" >/dev/null || {
  echo "编译出错，详见 output/$NAME.log"; exit 1; }
echo "▶ 第 2/2 次编译（更新目录页码）…"
xelatex -interaction=nonstopmode -halt-on-error "$NAME.tex" >/dev/null
echo "✅ 完成：output/$NAME.pdf"
