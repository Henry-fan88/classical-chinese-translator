"""实时进度监控面板（只读，可与翻译同时运行）。

显示：阶段状态、完成度进度条、字数、实时速度、预计剩余时间(ETA)、
      token 用量与估算花费、最近失败、最新译文样例。
默认每 3 秒刷新一次。  运行： python monitor.py
"""
import sys
import time

import config
import store


def fmt_dur(sec: float) -> str:
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}小时{m}分"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def bar(frac: float, width: int = 40) -> str:
    frac = max(0.0, min(1.0, frac))
    fill = int(frac * width)
    return "█" * fill + "░" * (width - fill)


def main():
    interval = 3.0
    if "--interval" in sys.argv:
        interval = float(sys.argv[sys.argv.index("--interval") + 1])

    prev = None  # (t, done_chars)
    try:
        while True:
            try:
                conn = store.connect(readonly=True)
            except Exception:
                print("等待状态库创建…（先运行 extract.py）")
                time.sleep(interval)
                continue
            st = store.stats(conn)
            run_state = store.get_meta(conn, "run_state", "未启动")
            last_active = float(store.get_meta(conn, "last_active", 0) or 0)
            started = float(store.get_meta(conn, "started_at", 0) or 0)
            tok_in = float(store.get_meta(conn, "tok_in", 0) or 0)
            tok_out = float(store.get_meta(conn, "tok_out", 0) or 0)
            tok_hit = float(store.get_meta(conn, "tok_hit", 0) or 0)

            # 实时速度（基于本监控两次采样的字数差）
            now = time.time()
            rate_cps = 0.0
            if prev and now > prev[0]:
                rate_cps = (st["done_c"] - prev[1]) / (now - prev[0])
            prev = (now, st["done_c"])

            remaining_c = st["pending_c"] + st["error_c"]
            eta = remaining_c / rate_cps if rate_cps > 0.5 else 0

            cost = (tok_in / 1e6 * config.PRICE_INPUT_PER_M
                    + tok_out / 1e6 * config.PRICE_OUTPUT_PER_M)
            frac = st["done_n"] / max(st["total_n"], 1)

            # 最新一条译文样例 & 失败样例
            sample = conn.execute(
                "SELECT juan_no,source,translated FROM segments WHERE status='done' "
                "AND translated IS NOT NULL ORDER BY updated_at DESC LIMIT 1").fetchone()
            errs = conn.execute(
                "SELECT juan_no,seq,error FROM segments WHERE status='error' "
                "ORDER BY updated_at DESC LIMIT 3").fetchall()
            conn.close()

            idle = now - last_active if last_active else 0
            live = run_state == "running" and idle < 30

            print("\033[2J\033[H", end="")   # 清屏
            print("╔══════════ 宗镜录 · 翻译进度监控 ══════════╗")
            state_txt = {"running": "运行中", "stopped": "已停止",
                         "idle": "已完成/空闲"}.get(run_state, run_state)
            dot = "🟢" if live else ("🟡" if run_state == "running" else "⚪")
            print(f" 状态 : {dot} {state_txt}"
                  + (f"（{fmt_dur(idle)}无活动）" if run_state == 'running' and not live else ""))
            print(f" 进度 : [{bar(frac)}] {frac*100:5.1f}%")
            print(f"        {st['done_n']}/{st['total_n']} 段   "
                  f"{st['done_c']:,}/{st['total_c']:,} 字   失败 {st['error_n']}")
            print(f" 速度 : {rate_cps*60:,.0f} 字/分"
                  + (f"   预计剩余 {fmt_dur(eta)}" if eta else "   预计剩余 —"))
            if started:
                print(f" 已运行: {fmt_dur(now - started)}")
            print(f" 用量 : 输入 {tok_in/1e6:.2f}M  输出 {tok_out/1e6:.2f}M  "
                  f"缓存命中 {tok_hit/1e6:.2f}M  ≈ ¥{cost:.1f}")
            if sample:
                src = sample["source"][:34].replace("\n", " ")
                tr = (sample["translated"] or "")[:34].replace("\n", " ")
                print("─ 最新译例 (卷%d) ─" % sample["juan_no"])
                print(f"   原: {src}…")
                print(f"   译: {tr}…")
            if errs:
                print("─ 最近失败 ─")
                for e in errs:
                    print(f"   卷{e['juan_no']} seq{e['seq']}: {(e['error'] or '')[:40]}")
            print("╚════════════════════════════════════════╝")
            print(f"(每 {interval:g}s 刷新，Ctrl+C 退出监控；不影响后台翻译)")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已退出监控。后台翻译仍在继续。")


if __name__ == "__main__":
    main()
