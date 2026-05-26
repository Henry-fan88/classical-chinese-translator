#!/usr/bin/env bash
# 安装 TinyTeX（用户目录，免 sudo）+ 中文排版所需宏包。
# 只需在第一次编译 PDF 前运行一次。耗时约几分钟，需联网。
set -e

BIN="$HOME/Library/TinyTeX/bin/universal-darwin"
if [ ! -x "$BIN/xelatex" ] && [ ! -x "$HOME/.TinyTeX/bin/universal-darwin/xelatex" ]; then
  echo "▶ 安装 TinyTeX（约 100MB，装到 ~/Library/TinyTeX，无需 sudo）…"
  curl -sL "https://yihui.org/tinytex/install-bin-unix.sh" | sh
fi

# 定位 tlmgr
for p in "$HOME/Library/TinyTeX/bin/universal-darwin" "$HOME/.TinyTeX/bin/universal-darwin"; do
  [ -x "$p/tlmgr" ] && export PATH="$p:$PATH"
done

echo "▶ 安装中文排版宏包（ctex / xecjk / 等）…"
tlmgr install \
  ctex xecjk ctablestack \
  zhnumber fandol \
  l3kernel l3packages \
  geometry verse xcolor \
  latexmk \
  || echo "（部分包可能已存在，可忽略相应提示）"

echo "✅ TeX 环境就绪。现在可以运行： bash build_pdf.sh"
echo "   提示：本脚本用 macOS 系统中文字体（fontset=mac），无需另装字体。"
