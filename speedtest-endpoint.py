#!/usr/bin/env python3
"""
Использование:
    python3 speedtest.py <url> [n]

Единицы: Mbit/s и MiB/s.
"""
import sys
import time
import urllib.request

def measure(url: str, n: int = 10) -> dict:
    headers = {
        "User-Agent": "speedtest-script/1.0",
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
        "Accept-Encoding": "identity",  # не даём серверу сжимать
    }

    times, sizes = [], []
    print(f"URL: {url}")
    print(f"Запросов: {n} (последовательно)\n")

    for i in range(1, n + 1):
        req = urllib.request.Request(url, headers=headers)
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read() 
        dt = time.perf_counter() - t0

        size = len(body)
        times.append(dt)
        sizes.append(size)
        speed = size / dt / 1024 / 1024 if dt > 0 else 0
        print(f"  [{i:>2}/{n}] {size:>12,} B  за {dt:6.3f} с  ({speed:6.2f} MiB/s)")

    total_bytes = sum(sizes)
    total_time = sum(times)
    sorted_t = sorted(times)
    median = sorted_t[len(sorted_t) // 2] if len(sorted_t) % 2 else \
             (sorted_t[len(sorted_t)//2 - 1] + sorted_t[len(sorted_t)//2]) / 2

    return {
        "n": n,
        "total_bytes": total_bytes,
        "total_time": total_time,
        "mean_time": total_time / n,
        "median_time": median,
        "mean_speed_mbps": total_bytes * 8 / total_time / 1_000_000,  # SI
        "mean_speed_mibs": total_bytes / total_time / 1024 / 1024,    # бинарные
    }

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <url> [n=10]", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    try:
        r = measure(url, n)
    except urllib.error.URLError as e:
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        sys.exit(2)

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