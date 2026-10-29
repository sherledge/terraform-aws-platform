import time
import argparse
import statistics
import concurrent.futures
import urllib.request
import urllib.error

def send_request(url, timeout=2.0):
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChaosLoadTest/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.getcode()
            duration = time.perf_counter() - start
            return status, duration
    except urllib.error.HTTPError as e:
        duration = time.perf_counter() - start
        return e.code, duration
    except Exception:
        duration = time.perf_counter() - start
        return 0, duration

def run_stress_test(url="http://localhost:8090/", total_requests=500, concurrency=10, timeout=2.0):
    print(f"=== Starting Stress Test ===")
    print(f"Target URL:     {url}")
    print(f"Total Requests: {total_requests}")
    print(f"Concurrency:    {concurrency}")
    print(f"Timeout:        {timeout}s")
    print("-" * 40)

    start_time = time.perf_counter()
    latencies = []
    status_counts = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(send_request, url, timeout) for _ in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            status, duration = f.result()
            latencies.append(duration)
            status_counts[status] = status_counts.get(status, 0) + 1

    total_time = time.perf_counter() - start_time
    successful_requests = status_counts.get(200, 0)
    failed_requests = total_requests - successful_requests
    availability = (successful_requests / total_requests) * 100
    rps = total_requests / total_time if total_time > 0 else 0

    sorted_latencies = sorted(latencies)
    p50 = statistics.median(sorted_latencies) * 1000
    p90 = sorted_latencies[int(len(sorted_latencies) * 0.90)] * 1000
    p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)] * 1000
    p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)] * 1000
    avg_latency = (sum(sorted_latencies) / len(sorted_latencies)) * 1000

    print("\n=== Stress Test Results ===")
    print(f"Total Time:      {total_time:.2f}s")
    print(f"Throughput:      {rps:.1f} req/s")
    print(f"Success Rate:    {availability:.2f}% ({successful_requests}/{total_requests})")
    print(f"HTTP Statuses:   {status_counts}")
    print(f"Avg Latency:     {avg_latency:.2f} ms")
    print(f"p50 Latency:     {p50:.2f} ms")
    print(f"p90 Latency:     {p90:.2f} ms")
    print(f"p95 Latency:     {p95:.2f} ms")
    print(f"p99 Latency:     {p99:.2f} ms")
    print("=" * 40)

    return {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "total_time": total_time,
        "rps": rps,
        "availability": availability,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "status_counts": status_counts
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress test load generator")
    parser.add_argument("--url", default="http://localhost:8090/", help="Target endpoint")
    parser.add_argument("--requests", type=int, default=500, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--timeout", type=float, default=2.0, help="Timeout in seconds")
    args = parser.parse_args()

    run_stress_test(args.url, args.requests, args.concurrency, args.timeout)
