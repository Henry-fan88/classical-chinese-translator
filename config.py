"""全局配置。所有可调参数集中在此。

API Key 不写在这里，从环境变量 DEEPSEEK_API_KEY 读取。
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent              # translator/
PROJECT = ROOT.parent                               # wechat_book/

# ---- 路径 ----
EPUB_PATH = Path(os.environ.get("EPUB_PATH", ROOT / "万善同归集_T2017.epub"))
DB_PATH   = ROOT / "data" / "state.db"
OUT_DIR   = ROOT / "output"
LOG_DIR   = ROOT / "logs"
TEX_PATH  = OUT_DIR / "wanshantonggui.tex"

# ---- DeepSeek API ----
API_KEY_ENV = "DEEPSEEK_API_KEY"
BASE_URL    = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL       = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")   # V3 对话模型，适合翻译
TEMPERATURE = float(os.environ.get("DEEPSEEK_TEMPERATURE", "1.0"))
MAX_TOKENS  = int(os.environ.get("DEEPSEEK_MAX_TOKENS", "8192"))

# ---- 切块与并发 ----
CONCURRENCY      = int(os.environ.get("TR_CONCURRENCY", "8"))   # 并发请求数
BATCH_CHARS      = int(os.environ.get("TR_BATCH_CHARS", "1400"))# 每个请求合并的原文字数上限
MAX_SEGS_PER_BATCH = int(os.environ.get("TR_MAX_SEGS", "10"))   # 每个请求最多合并几段
OVERSIZE_CHARS   = int(os.environ.get("TR_OVERSIZE", "1600"))   # 超过此长度的单段，内部按句再切
SUBCHUNK_CHARS   = int(os.environ.get("TR_SUBCHUNK", "1000"))   # 超长段内部子块大小
MAX_RETRIES      = int(os.environ.get("TR_MAX_RETRIES", "5"))   # 单请求失败重试次数

# ---- 成本估算（按 token，仅供参考，请以官网最新价为准）----
# DeepSeek 大致按 1 个汉字 ≈ 0.6 token 计；下列单价单位：元 / 百万 token
PRICE_INPUT_PER_M  = float(os.environ.get("PRICE_INPUT", "2.0"))
PRICE_OUTPUT_PER_M = float(os.environ.get("PRICE_OUTPUT", "8.0"))
CHARS_PER_TOKEN    = 0.6     # 汉字→token 粗略系数
OUTPUT_RATIO       = 1.8     # 白话译文相对原文的长度倍数（估算用）


def api_key() -> str:
    k = os.environ.get(API_KEY_ENV, "").strip()
    if not k:
        raise SystemExit(
            f"未找到 API Key。请先设置环境变量：export {API_KEY_ENV}=你的key"
        )
    return k
