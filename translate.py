"""阶段二：调用 DeepSeek 逐段翻译。

特性：
  * 断点续跑 —— 只处理 status != 'done' 的段，随时可中断/重启。
  * 并发 —— 多线程并行请求；DB 写入集中在主线程，避免锁冲突。
  * 自适应批次 —— 多个短段合并一次请求；超长段内部按句再切后拼回，保证仍是一段。
  * 优雅停止 —— Ctrl+C 或 kill 后停止派发新任务，已完成的都已落库。
  * 用量统计 —— 累计 token 与缓存命中，供监控/成本核算。

运行：  python translate.py            # 翻译全部未完成段
        python translate.py --limit 20 # 只跑前 20 段（试跑/验质量）
"""
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import httpx
from openai import OpenAI

import config
import prompts
import store

STOP = threading.Event()


def _on_signal(signum, frame):
    if not STOP.is_set():
        print("\n[停止] 收到中断信号，正在完成手头任务后退出……已完成的进度已保存。",
              flush=True)
    STOP.set()


signal.signal(signal.SIGINT, _on_signal)
signal.signal(signal.SIGTERM, _on_signal)

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        # 连接 15s、读取 180s 超时；SDK 自身不重试（重试由 _attempt 统一处理）。
        # 连不上时十几秒内明确报错，不再长时间“假死”。
        _client = OpenAI(
            api_key=config.api_key(), base_url=config.BASE_URL,
            timeout=httpx.Timeout(180.0, connect=15.0), max_retries=0)
    return _client


# ---------------- 切分句子（仅用于超长单段） ----------------
def split_sentences(text: str):
    parts = re.split(r"(?<=[。！？；])", text)
    groups, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > config.SUBCHUNK_CHARS and cur:
            groups.append(cur)
            cur = p
        else:
            cur += p
    if cur.strip():
        groups.append(cur)
    return groups


# ---------------- 组批 ----------------
def make_batches(rows):
    """把待译段落组成批次。每个批次是 [(seg_id, kind, source), ...]。
    超长段单独成批（内部再切）。"""
    batches, cur, cur_chars = [], [], 0
    for r in rows:
        n = r["n_chars"]
        if n >= config.OVERSIZE_CHARS:
            if cur:
                batches.append(cur); cur, cur_chars = [], 0
            batches.append([(r["id"], r["kind"], r["source"])])
            continue
        if cur and (cur_chars + n > config.BATCH_CHARS
                    or len(cur) >= config.MAX_SEGS_PER_BATCH):
            batches.append(cur); cur, cur_chars = [], 0
        cur.append((r["id"], r["kind"], r["source"]))
        cur_chars += n
    if cur:
        batches.append(cur)
    return batches


# ---------------- 调用 API ----------------
def _chat(messages):
    resp = client().chat.completions.create(
        model=config.MODEL, messages=messages,
        temperature=config.TEMPERATURE, max_tokens=config.MAX_TOKENS, stream=False)
    usage = resp.usage
    return resp.choices[0].message.content, resp.choices[0].finish_reason, usage


def _translate_long(seg_id, kind, source):
    """超长单段：按句子分组翻译再拼回，仍作为一段。"""
    groups = split_sentences(source)
    out_parts, agg = [], {"in": 0, "out": 0, "hit": 0}
    for g in groups:
        msgs = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content":
                "把下面这段文言文翻译成现代简体中文白话，直接输出译文，不要加任何标号或说明：\n\n" + g},
        ]
        text, fr, usage = _chat(msgs)
        out_parts.append(text.strip())
        agg["in"] += usage.prompt_tokens
        agg["out"] += usage.completion_tokens
        agg["hit"] += getattr(usage, "prompt_cache_hit_tokens", 0) or 0
    return {seg_id: "".join(out_parts)}, agg


def translate_batch(batch):
    """返回 (results dict{seg_id: 译文}, usage dict)。线程内执行，不碰 DB。"""
    if len(batch) == 1 and len(batch[0][2]) >= config.OVERSIZE_CHARS:
        sid, kind, src = batch[0]
        return _translate_long(sid, kind, src)

    local = [(i + 1, kind, src) for i, (sid, kind, src) in enumerate(batch)]
    id_by_local = {i + 1: sid for i, (sid, _, _) in enumerate(batch)}
    expected = set(id_by_local)

    msgs = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {"role": "user", "content": prompts.build_user_message(local)},
    ]
    text, fr, usage = _chat(msgs)
    parsed = prompts.parse_numbered(text, expected)
    agg = {"in": usage.prompt_tokens, "out": usage.completion_tokens,
           "hit": getattr(usage, "prompt_cache_hit_tokens", 0) or 0}

    if not expected.issubset(parsed.keys()) or fr == "length":
        # 段数对不上或被截断 —— 拆成单段逐个重试（更稳）
        results, sub_agg = {}, {"in": 0, "out": 0, "hit": 0}
        for sid, kind, src in batch:
            one = [(1, kind, src)]
            m = [{"role": "system", "content": prompts.SYSTEM_PROMPT},
                 {"role": "user", "content": prompts.build_user_message(one)}]
            t, f, u = _chat(m)
            p = prompts.parse_numbered(t, {1})
            results[sid] = p.get(1, t.strip())
            sub_agg["in"] += u.prompt_tokens
            sub_agg["out"] += u.completion_tokens
            sub_agg["hit"] += getattr(u, "prompt_cache_hit_tokens", 0) or 0
        return results, sub_agg

    return {id_by_local[k]: v for k, v in parsed.items() if k in id_by_local}, agg


def _attempt(batch):
    """带退避重试地翻译一个批次。"""
    delay = 2.0
    for attempt in range(1, config.MAX_RETRIES + 1):
        if STOP.is_set():
            raise RuntimeError("stopped")
        try:
            return translate_batch(batch)
        except Exception as e:
            if attempt == config.MAX_RETRIES:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 30)


# ---------------- 主循环 ----------------
def main():
    store.init()
    conn = store.connect()
    if not store.get_meta(conn, "started_at"):
        store.set_meta(conn, "started_at", time.time())
    store.set_meta(conn, "run_pid", __import__("os").getpid())
    store.set_meta(conn, "run_state", "running")
    conn.commit()

    q = ("SELECT id,juan_no,seq,kind,source,n_chars FROM segments "
         "WHERE status!='done' ORDER BY seq")
    rows = conn.execute(q).fetchall()
    if "--limit" in sys.argv:
        n = int(sys.argv[sys.argv.index("--limit") + 1])
        rows = rows[:n]
    if not rows:
        print("没有待翻译的段落，全部已完成 ✅")
        store.set_meta(conn, "run_state", "idle"); conn.commit(); conn.close()
        return

    batches = make_batches(rows)
    print(f"待翻译 {len(rows)} 段，组成 {len(batches)} 个批次，并发 {config.CONCURRENCY}。"
          f"  (Ctrl+C 可随时安全中断)")

    def write_result(results, agg):
        now = time.time()
        for sid, tr in results.items():
            conn.execute(
                "UPDATE segments SET translated=?,status='done',attempts=attempts+1,"
                "error=NULL,updated_at=? WHERE id=?", (tr, now, sid))
        store.add_meta_number(conn, "tok_in", agg["in"])
        store.add_meta_number(conn, "tok_out", agg["out"])
        store.add_meta_number(conn, "tok_hit", agg["hit"])
        store.set_meta(conn, "last_active", now)
        conn.commit()

    def write_error(batch, err):
        now = time.time()
        for sid, _, _ in batch:
            conn.execute(
                "UPDATE segments SET status='error',attempts=attempts+1,error=?,"
                "updated_at=? WHERE id=?", (str(err)[:500], now, sid))
        conn.commit()

    it = iter(batches)
    inflight = {}
    done_batches = 0
    with ThreadPoolExecutor(max_workers=config.CONCURRENCY) as ex:
        while True:
            while len(inflight) < config.CONCURRENCY and not STOP.is_set():
                try:
                    b = next(it)
                except StopIteration:
                    break
                inflight[ex.submit(_attempt, b)] = b
            if not inflight:
                break
            done, _ = wait(inflight, return_when=FIRST_COMPLETED)
            for fut in done:
                batch = inflight.pop(fut)
                try:
                    results, agg = fut.result()
                    write_result(results, agg)
                except Exception as e:
                    if str(e) != "stopped":
                        write_error(batch, e)
                done_batches += 1
            if done_batches % 5 == 0 or STOP.is_set():
                st = store.stats(conn)
                print(f"  进度 {st['done_n']}/{st['total_n']} 段 "
                      f"({st['done_n']/max(st['total_n'],1)*100:.1f}%)  "
                      f"批次 {done_batches}/{len(batches)}", flush=True)
            if STOP.is_set() and not inflight:
                break

    st = store.stats(conn)
    store.set_meta(conn, "run_state", "stopped" if STOP.is_set() else "idle")
    conn.commit()
    print(f"\n本轮结束：已完成 {st['done_n']}/{st['total_n']} 段，"
          f"失败 {st['error_n']} 段。" +
          ("（被中断，重跑本脚本即可续传）" if STOP.is_set() else ""))
    if st["error_n"]:
        print("有失败段落，重跑本脚本会自动重试它们。")
    conn.close()


if __name__ == "__main__":
    main()
