#!/usr/bin/env python3
"""speedtest.py — замеряет скорость скачивания URL N последовательными запросами.

Использование:
    python3 speedtest.py <url> [--n 10] [--max-retries 5] [--delay 0.0]

Единицы: Mbit/s и MiB/s.
"""
import argparse
import random
import sys
import time
import urllib.error
import urllib.request

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

EXCESSIVE_RETRY_AFTER = 30.0   # порог «слишком долго просят ждать»
SHORT_WAIT = 10.0              # первая реакция на превышение
LONG_WAIT = 30.0               # последующие реакции

def _retry_after_seconds(err):
    """Retry-After в секундах, либо None, если заголовка нет / он невалиден.
    HTTP-date-формат не парсим — для наших целей это редкость."""
    try:
        val = err.headers.get("Retry-After")
    except Exception:
        return None
    if not val:
        return None
    try:
        return max(0.0, float(val))
    except ValueError:
        return None


def _fetch_once(url: str, headers: dict, timeout: float) -> tuple[float, int]:
    req = urllib.request.Request(url, headers=headers)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return time.perf_counter() - t0, len(body)


def _fetch_with_retry(url, headers, timeout, max_retries, base_delay=1.0):
    attempt = 0
    excessive_streak = 0  # сколько раз подряд сервер просил ждать > EXCESSIVE_RETRY_AFTER
    while True:
        try:
            return _fetch_once(url, headers, timeout)
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE_STATUS or attempt >= max_retries:
                raise
            attempt += 1
            ra = _retry_after_seconds(e)

            # сначала короткая пауза 10с, потом 30с, и так до исчерпания ретраев.
            if ra is not None and ra > EXCESSIVE_RETRY_AFTER:
                excessive_streak += 1
                if excessive_streak == 1:
                    wait = SHORT_WAIT
                    print(f"    ! HTTP {e.code}, Retry-After={ra:.0f} с > "
                          f"{EXCESSIVE_RETRY_AFTER:.0f} с — ждём {wait:.0f} с "
                          f"и пробуем снова (ретрай {attempt}/{max_retries})")
                else:
                    wait = LONG_WAIT
                    print(f"    ! HTTP {e.code}, Retry-After={ra:.0f} с — "
                          f"всё ещё много, пауза {wait:.0f} с "
                          f"(ретрай {attempt}/{max_retries})")
                wait += random.uniform(0, 0.5)
                time.sleep(wait)
                continue

            excessive_streak = 0
            if ra is not None:
                wait = ra
                src = f"Retry-After={ra:.0f} с"
            else:
                wait = base_delay * (2 ** (attempt - 1))
                src = "backoff"
            wait += random.uniform(0, 0.5)
            print(f"    ! HTTP {e.code}, ретрай {attempt}/{max_retries} "
                  f"через {wait:.1f} с ({src})")
            time.sleep(wait)
        except urllib.error.URLError as e:
            if attempt >= max_retries:
                raise
            attempt += 1
            excessive_streak = 0
            wait = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            print(f"    ! сетевая ошибка ({e.reason}), ретрай "
                  f"{attempt}/{max_retries} через {wait:.1f} с")
            time.sleep(wait)


def measure(url: str, n: int, max_retries: int, delay: float) -> dict:
    headers = {
        "User-Agent": "speedtest-script/1.0",
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
        "Accept-Encoding": "identity",
    }

    times, sizes = [], []
    print(f"URL: {url}")
    print(f"Запросов: {n} (последовательно), max-retries={max_retries}, delay={delay}s\n")

    for i in range(1, n + 1):
        dt, size = _fetch_with_retry(
            url, headers, timeout=60,
            max_retries=max_retries, base_delay=1.0,
        )
        times.append(dt)
        sizes.append(size)
        speed = size / dt / 1024 / 1024 if dt > 0 else 0
        print(f"  [{i:>2}/{n}] {size:>12,} B  за {dt:6.3f} с  ({speed:6.2f} MiB/s)")
        if delay > 0 and i < n:
            time.sleep(delay)

    total_bytes = sum(sizes)
    total_time = sum(times)
    sorted_t = sorted(times)
    mid = len(sorted_t) // 2
    median = sorted_t[mid] if len(sorted_t) % 2 else (sorted_t[mid - 1] + sorted_t[mid]) / 2

    return {
        "n": n,
        "total_bytes": total_bytes,
        "total_time": total_time,
        "mean_time": total_time / n,
        "median_time": median,
        "mean_speed_mbps": total_bytes * 8 / total_time / 1_000_000,
        "mean_speed_mibs": total_bytes / total_time / 1024 / 1024,
    }


def main():
    p = argparse.ArgumentParser(description="Замер скорости скачивания.")
    p.add_argument("url")
    p.add_argument("-n", "--n", type=int, default=10, help="число запросов (по умолчанию 10)")
    p.add_argument("--max-retries", type=int, default=5,
                   help="макс. ретраев на один запрос при 429/5xx/сетевых ошибках (по умолчанию 5)")
    p.add_argument("--delay", type=float, default=0.0,
                   help="пауза в секундах между успешными запросами (по умолчанию 0)")
    args = p.parse_args()

    try:
        r = measure(args.url, args.n, args.max_retries, args.delay)
    except urllib.error.HTTPError as e:
        print(f"HTTP-ошибка: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(2)
    except urllib.error.URLError as e:
        print(f"Сетевая ошибка: {e.reason}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
        sys.exit(130)

    print()
    print("=" * 46)
    print(f"Скачано всего:       {r['total_bytes']:,} байт "
          f"({r['total_bytes']/1024/1024:.2f} MiB)")
    print(f"Суммарное время:     {r['total_time']:.3f} с")
    print(f"Среднее время:       {r['mean_time']*1000:.1f} мс "
          f"(медиана {r['median_time']*1000:.1f} мс)")
    print(f"Скорость скачивания: {r['mean_speed_mbps']:.2f} Mbit/s "
          f"({r['mean_speed_mibs']:.2f} MiB/s)")
    print("=" * 46)


if __name__ == "__main__":
    main()