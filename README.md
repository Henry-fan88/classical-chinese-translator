# 文言 → 简体白话 翻译流水线

把一本 EPUB 里的文言文，用 **DeepSeek API** 逐段翻译成现代简体中文白话，
再排版成与原书分段一致的 **LaTeX / PDF**。以 CBETA《宗镜录》(T48 No.2016, 100 卷) 为示例。

支持：后台不间断运行、断点续跑、实时进度监控。

> **用途声明**：本工具仅用于翻译**公有领域**或**你依法拥有权利**的文本。
> 请勿用它处理或分发受版权保护的书籍文件。仓库本身不含任何书籍内容。
> 代码以 MIT 许可证开源（见 [LICENSE](LICENSE)）。

## 目录结构
```
translator/
├── config.py          参数（模型、并发、批次、单价…）
├── extract.py         阶段一：解析 EPUB 入库
├── translate.py       阶段二：调用 DeepSeek 翻译（核心，可续传）
├── monitor.py         实时进度面板
├── build_latex.py     阶段三：译文 → LaTeX
├── build_pdf.sh       阶段四：LaTeX → PDF (xelatex)
├── setup_tex.sh       一次性：装 TinyTeX + 中文宏包（免 sudo）
├── start_translate.sh 一键后台启动翻译
├── requirements.txt   Python 依赖（openai, beautifulsoup4）
├── venv/              Python 虚拟环境（首次 setup 后生成）
├── data/state.db      状态库（进度的唯一事实来源，运行时生成）
├── logs/              运行日志（运行时生成）
└── output/            your_book.tex / .pdf（运行时生成）
```

---

## 使用步骤

### 0. 环境准备（首次克隆后）
```bash
cd translator
python3 -m venv venv                 # 建虚拟环境
./venv/bin/pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-你的key    # 到 https://platform.deepseek.com 创建
```
> API Key 仅在当前终端有效；安全与持久化见下方「关于 API Key 与安全」。
> **不要**把 key 写进任何脚本或提交到 git。

### 1. 抽取 EPUB 入库
```bash
# 可用 EPUB_PATH 指定文件
EPUB_PATH=/path/to/book.epub ./venv/bin/python extract.py    # 重建加 --force
```
完成后会打印段数、总字数与预估 API 费用。

### 2. 先小样试译，确认质量（强烈建议）
```bash
./venv/bin/python translate.py --limit 20
./venv/bin/python build_latex.py    # 看 output/your_book.tex 里的译文
```
觉得风格/术语要调整，就改 `prompts.py` 里的 `SYSTEM_PROMPT`，再 `--limit` 重试。

### 3. 后台跑完整本
```bash
./start_translate.sh
```
关掉终端也会继续跑。中途想停：`kill $(cat logs/translate.pid)`；
重跑 `./start_translate.sh` 会自动从断点续传（已完成的段不会重译）。

### 4. 另开一个终端看实时进度
```bash
cd translator
./venv/bin/python monitor.py
```
显示：状态、进度条、字数、实时速度、预计剩余时间、token 用量与花费、最新译例。

### 5. 全部译完后，生成 PDF
```bash
bash setup_tex.sh      # 仅第一次：装 TinyTeX + 中文宏包（约几分钟，联网）

# 纯白话版
./venv/bin/python build_latex.py             # -> output/zongjinglu.tex
bash build_pdf.sh                             # -> output/zongjinglu.pdf

# 原文/译文对照版（灰色原文 + 黑色白话，独立文件，不覆盖纯白话版）
./venv/bin/python build_latex.py --bilingual # -> output/zongjinglu_bilingual.tex
bash build_pdf.sh zongjinglu_bilingual       # -> output/zongjinglu_bilingual.pdf
```
> **字号**：默认 14pt（基于 `extbook` 类，需 `tlmgr install extsizes`）。想更大/更小，
> 用环境变量覆盖再重跑 `build_latex.py`，可选 10/11/12/14/17/20pt：
> `TR_FONT_PT=17 ./venv/bin/python build_latex.py --bilingual`
> 不想装 LaTeX？把生成的 `.tex` 上传到 https://www.overleaf.com 直接编译即可（零安装，自带 ctex + extsizes）。

---

## 常见调整（config.py）
| 变量 | 含义 | 默认 |
|---|---|---|
| `CONCURRENCY` | 并发请求数（越大越快，注意账户限速） | 8 |
| `BATCH_CHARS` | 每次请求合并的原文字数 | 1400 |
| `MODEL` | DeepSeek 模型：`deepseek-v4-pro`(质量优) / `deepseek-v4-flash`(快且省)。旧名 `deepseek-chat` / `deepseek-reasoner` 仍可用但将废弃 | deepseek-v4-pro |
| `TEMPERATURE` | 翻译温度（注意：思考型模型会忽略此项） | 1.0 |

也可用环境变量临时覆盖，如 `TR_CONCURRENCY=16 ./venv/bin/python translate.py`，
或 `DEEPSEEK_MODEL=deepseek-v4-flash ./venv/bin/python translate.py --limit 20` 对比模型。

---

## 工作原理（架构）

整条流水线**以 SQLite 状态库 `data/state.db` 为唯一中心**，四个阶段彼此解耦：

```
 ① extract.py        ② translate.py             ③ build_latex.py        ④ build_pdf.sh
 EPUB ──解析──▶ state.db ──逐段填译文──▶ state.db ──读全库一次性拼装──▶ your_book.tex ──xelatex──▶ your_book.pdf
                (每段 = 一行)            (translated 列)
```

- **每个段落是数据库里的一行**，含 `source`(原文)、`translated`(译文)、`status`(pending/done/error)、
  `kind`(juan/heading/byline/para/verse) 等结构信息。
- **翻译阶段只写数据库，不生成任何 LaTeX**。`translate.py` 把每段译文写回对应行。
  所谓"翻译中间产物"不是 `.tex`，而是**不断被填满的 `state.db`**。
- **断点续跑**：`translate.py` 只挑 `status != 'done'` 的段处理，每个批次完成即提交。
  任何时候中断（Ctrl+C、kill、断电、关机）都不丢已完成进度；重跑自动续传，失败段自动重试。
- **LaTeX 是"最后一次性渲染"**：只有运行 `build_latex.py` 时，它才把整库按顺序读出、
  按结构映射成 LaTeX（卷→`\chapter`、序→`\section`、署名→`\byline`、正文→段落、偈颂→`verse`），
  转义特殊字符后**整本覆盖写出** `your_book.tex`。未译完的段会暂用原文占位以保证可编译。
- **翻译一次、渲染随意**：纯白话版、原文对照版(`--bilingual`)、改字体排版，都只需重跑 `build_latex.py`，
  无需重新翻译、不再花 API 费用。

### 翻译质量的关键
- 提示词在 `prompts.py` 的 `SYSTEM_PROMPT`，固定不变，因此 DeepSeek 会**自动命中上下文缓存**降本提速。
- 多段合并为一个请求（带 `【序号】` 标记），返回后按序号拆回；段数对不上或被截断时**自动降级为逐段重试**。
- 超长单段（默认 ≥1600 字）按句子切分后翻译再拼回，避免输出被 `max_tokens` 截断。

---

## 关于 API Key 与安全

- `export DEEPSEEK_API_KEY=...` 在**当前 shell 进程内存**里设一个环境变量，由它启动的子进程（python）继承；
  脚本通过 `os.environ` 读取。好处是 **key 不写进代码、不进 git**。
- **不会**泄露到：代码、git、网络（只随 API 请求发给 DeepSeek）。
  **会**留痕的一处：`export ...` 这行命令进入 **shell 历史**（`~/.zsh_history` 明文）。
  规避：命令前加空格（需 `setopt hist_ignore_space`），或用 `read -rs DEEPSEEK_API_KEY` 不回显输入。
- **新终端要重设**：环境变量只活在设置它的那个 shell 进程里，不是系统全局；新终端是全新进程，不继承。
- 想持久化（按安全性排序）：
  - **A. 写进 `~/.zshrc`**：`echo 'export DEEPSEEK_API_KEY=sk-xxx' >> ~/.zshrc` —— 方便，但 key 明文落盘。
  - **B. 存 macOS 钥匙串（推荐）**：
    ```bash
    security add-generic-password -a "$USER" -s deepseek_api_key -w   # 存一次
    echo 'export DEEPSEEK_API_KEY=$(security find-generic-password -s deepseek_api_key -w)' >> ~/.zshrc
    ```
    rc 文件里没有 key 本身，只从加密钥匙串读取。
  - **C. 每次手动 export**：最朴素，关掉即清。

---

## 故障排查（FAQ）

### 翻译全部失败：`Connection error` / `Request timed out`
说明请求没连上 API 服务器（此时 Key 不会被计费）。代码已设连接超时，连不上会在十几秒内明确报错。
按以下顺序排查（先看错误：`monitor.py` 面板或 `data/state.db` 的 `error` 列）：

1. **代理环境变量残留**：`env | grep -i proxy`。若有 `HTTP_PROXY/HTTPS_PROXY` 指向已停的代理端口，
   `unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy`。
2. **VPN / Clash 的 TUN / fake-ip 仍在劫持**：典型症状是
   `nslookup api.deepseek.com` 返回 `198.18.x.x`（fake-ip 虚拟地址）。
   注意**关窗口 ≠ 退出**——核心进程和 `utun` 虚拟网卡可能仍在跑：
   ```bash
   ps aux | grep -iE "clash|mihomo" | grep -v grep   # 看核心是否还在
   ifconfig | grep 198.18                            # 看 TUN 网卡是否还在
   ```
   从托盘图标**彻底退出**（或关闭 TUN/增强模式），TUN 网卡消失后 DNS 才恢复。
3. **分清"整体断网"还是"只 API 不通"**：拿一个对照站点直连测试，
   `curl -m 8 https://www.baidu.com -o /dev/null -w "%{http_code}\n"`。
   若对照站点正常、只有 API 超时，多半是下一条。
4. **CDN 边缘节点不可达**（校园网/某些网络常见）：API 走 CDN，DNS 可能把你导到一组
   **从你这条网络不可达的边缘 IP**。换 DNS 找可达 IP，或把可达 IP 钉进 `/etc/hosts`：
   ```bash
   # 用其它公共 DNS 解析，逐个测哪个 IP 能连上（返回 401 = 通）
   for dns in 114.114.114.114 223.5.5.5 119.29.29.29; do nslookup api.deepseek.com $dns; done
   curl -m 8 --resolve api.deepseek.com:443:<候选IP> https://api.deepseek.com/ -o /dev/null -w "%{http_code}\n"
   # 钉死可达 IP（任务结束后可删除该行）
   echo "<可达IP> api.deepseek.com" | sudo tee -a /etc/hosts
   sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder   # macOS 刷新 DNS 缓存
   ```
   或最省事：**改用手机流量热点**，走运营商网络绕开上述问题。
5. **`nslookup` 正常但程序仍连旧 IP**：`nslookup` 直接问 DNS 服务器，而程序用系统解析缓存
   （macOS 的 mDNSResponder）。改完 DNS 记得刷新缓存（上面的 `dscacheutil` 命令），
   再用 `python -c "import socket; print(socket.getaddrinfo('api.deepseek.com',443))"` 看程序实际解析到什么。

### 后台任务会自动退出吗？
会。`translate.py` 跑完一轮所有待译段后打印总结并退出，不常驻。
若结束时 `失败` 不为 0，再执行一次 `./start_translate.sh` 即可（只重试失败段，已完成跳过）。

### 模型相关
- 模型名以官网为准；旧别名 `deepseek-chat` / `deepseek-reasoner` 将废弃。
- 思考型模型会**忽略 `temperature`**；其"思考过程"在单独字段，本脚本读取的是最终译文，不受影响。

---

## 说明
本仓库不含书籍内容。
机器译文仅供阅读参考，义理以原典为准。请仅对**你有权处理**的文本使用本工具。
