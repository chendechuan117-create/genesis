#!/usr/bin/env python3
"""
aixj provider 多方面综合测试。
用法：python scripts/probe_aixj.py
"""
import asyncio
import sys
import time

sys.path.insert(0, "/home/chendechusn/Genesis/Genesis")
from dotenv import load_dotenv
load_dotenv()

from genesis.core.config import ConfigManager
from genesis.providers.cloud_providers import _build_aixj

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def log(name, ok, elapsed, detail=""):
    tag = PASS if ok else FAIL
    msg = f"{tag}  [{name}]  {elapsed:.2f}s"
    if detail:
        msg += f"  {detail}"
    print(msg)
    results.append((name, ok, elapsed, detail))


async def run_case(name, provider, messages, stream=False, extra_kwargs=None):
    extra_kwargs = extra_kwargs or {}
    t0 = time.time()
    try:
        if stream:
            tokens_seen = []

            def cb(ev, data):
                if ev == "token" and data:
                    tokens_seen.append(data)

            resp = await provider.chat(messages, stream=True, stream_callback=cb, **extra_kwargs)
            elapsed = time.time() - t0
            content = "".join(tokens_seen) or getattr(resp, "content", "")
            tok = getattr(resp, "total_tokens", len(tokens_seen))
            log(name, bool(content), elapsed, f"tokens≈{tok}  preview={content[:80].replace(chr(10),' ')!r}")
        else:
            resp = await provider.chat(messages, stream=False, **extra_kwargs)
            elapsed = time.time() - t0
            content = getattr(resp, "content", "")
            fallback_detail = ""
            if not content:
                reasoning = getattr(resp, "reasoning_content", "")
                if reasoning:
                    content = reasoning
                    fallback_detail = "  (used reasoning_content)"
            if not content:
                content = str(resp)
            tok = getattr(resp, "total_tokens", "?")
            log(name, bool(content), elapsed,
                f"tokens={tok}  preview={content[:80].replace(chr(10),' ')!r}{fallback_detail}")
    except Exception as e:
        elapsed = time.time() - t0
        log(name, False, elapsed, f"{type(e).__name__}: {str(e)[:120]}")


async def main():
    config = ConfigManager().config
    provider = _build_aixj(config)
    if provider is None:
        print("ABORT: 无法构建 aixj provider（未配置 AIXJ_API_KEY/AIXJ_API_KEYS？）")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  aixj 综合探针")
    print(f"  URL:   {provider.base_url}")
    print(f"  Model: {provider.default_model}")
    print(f"{'='*60}\n")

    # ── 1. 非流式基础 ──
    await run_case(
        "1_basic_nonstream",
        provider,
        [{"role": "user", "content": "Reply with exactly: PONG"}],
    )

    # ── 2. 流式基础 ──
    await run_case(
        "2_basic_stream",
        provider,
        [{"role": "user", "content": "Reply with exactly: PONG"}],
        stream=True,
    )

    # ── 3. 中文输入/输出 ──
    await run_case(
        "3_chinese",
        provider,
        [{"role": "user", "content": "用一句话介绍你自己（中文回答）。"}],
        stream=True,
    )

    # ── 4. 代码生成 ──
    await run_case(
        "4_code_gen",
        provider,
        [{"role": "user", "content": "Write a Python one-liner that returns the sum of 1..100. Code only, no explanation."}],
        stream=False,
    )

    # ── 5. 多轮对话 ──
    multi_turn = [
        {"role": "user",      "content": "My secret number is 42."},
        {"role": "assistant", "content": "Got it, I'll remember 42."},
        {"role": "user",      "content": "What is my secret number? Reply with the number only."},
    ]
    await run_case("5_multi_turn", provider, multi_turn, stream=False)

    # ── 6. 长消息（~1500 chars system prompt） ──
    long_system = "You are a helpful assistant. " * 50
    await run_case(
        "6_long_context",
        provider,
        [
            {"role": "system", "content": long_system},
            {"role": "user",   "content": "Say OK."},
        ],
        stream=False,
    )

    # ── 7. 工具调用 schema（function calling） ──
    tool_schema = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"]
            }
        }
    }]
    t0 = time.time()
    try:
        resp = await provider.chat(
            [{"role": "user", "content": "What's the weather in Beijing?"}],
            tools=tool_schema,
            stream=False,
        )
        elapsed = time.time() - t0
        tc = getattr(resp, "tool_calls", None)
        has_call = bool(tc)
        detail = f"tool_calls={tc[0].name if tc else 'none'}  content={getattr(resp,'content','')[:60]!r}"
        log("7_tool_calling", True, elapsed, detail)
    except Exception as e:
        elapsed = time.time() - t0
        log("7_tool_calling", False, elapsed, f"{type(e).__name__}: {str(e)[:120]}")

    # ── 8. 并发 5 请求 ──
    t0 = time.time()
    try:
        tasks = [
            provider.chat(
                [{"role": "user", "content": f"Return the number {i} only."}],
                stream=False,
            )
            for i in range(5)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - t0
        ok_count = sum(1 for r in responses if not isinstance(r, Exception))
        fail_count = 5 - ok_count
        log("8_concurrency_5", fail_count == 0, elapsed,
            f"{ok_count}/5 succeeded" + (f"  errors={[str(r)[:60] for r in responses if isinstance(r, Exception)]}" if fail_count else ""))
    except Exception as e:
        elapsed = time.time() - t0
        log("8_concurrency_5", False, elapsed, f"{type(e).__name__}: {str(e)[:120]}")

    # ── 9. 延迟一致性（3次串行，测抖动） ──
    # 说明：前 8 个子探针已消耗 12 次 API 调用，aixj 默认限流 15 req/min
    #       在并发测试后立即继续请求容易撞 429，因此这里先等待一小段时间
    await asyncio.sleep(5)
    latencies = []
    jitter_ok = True
    jitter_errors = []
    for idx in range(3):
        t0 = time.time()
        try:
            await provider.chat(
                [{"role": "user", "content": "PING"}],
                stream=False,
            )
            elapsed = time.time() - t0
            latencies.append(elapsed)
            jitter_errors.append(None)
        except Exception as e:
            latencies.append(None)
            jitter_ok = False
            jitter_errors.append(f"{type(e).__name__}: {str(e)[:120]}")
    valid = [l for l in latencies if l is not None]
    if valid:
        avg = sum(valid) / len(valid)
        spread = max(valid) - min(valid)
        raw = [f"{l:.2f}" if l is not None else "ERR" for l in latencies]
        extra_err = f"  errors={[err for err in jitter_errors if err]}" if any(jitter_errors) else ""
        log("9_latency_jitter", jitter_ok, avg,
            f"avg={avg:.2f}s  spread={spread:.2f}s  raw={raw}{extra_err}")
    else:
        log("9_latency_jitter", False, 0,
            "all failed" + (f"  errors={jitter_errors}" if jitter_errors else ""))

    # ── Summary ──
    print(f"\n{'='*60}")
    passed = sum(1 for _, ok, _, _ in results if ok)
    total  = len(results)
    print(f"  结果: {passed}/{total} 通过")
    if passed < total:
        print("  失败项:")
        for name, ok, _, detail in results:
            if not ok:
                print(f"    - {name}: {detail}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
