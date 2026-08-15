#!/usr/bin/env python3
"""
Stress testing tool for Affairs and Order.
Executes high-concurrency requests against local staging to gather latency and performance metrics.
"""

import os
import sys
import time
import argparse
import asyncio
import aiohttp
import json
from urllib.parse import urlparse
import bcrypt
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database import get_db_connection

def parse_args():
    parser = argparse.ArgumentParser(description="AnO Stress Testing Tool")
    parser.add_argument("--target", default="http://127.0.0.1:5050", help="Target URL of the staging server")
    parser.add_argument("--concurrency", type=int, default=20, help="Number of concurrent requests")
    parser.add_argument("--requests", type=int, default=200, help="Total number of requests to perform")
    return parser.parse_args()

def validate_target(target):
    allowed_hosts = ['127.0.0.1', 'localhost', '0.0.0.0', 'staging.local', '::1']
    parsed = urlparse(target)
    host = parsed.hostname or ''
    
    # Safety Check: Must be local staging target
    if host not in allowed_hosts and 'staging' not in target:
        print(f"[SAFETY VIOLATION] Execution aborted! Host '{host}' is not an authorized local staging target.")
        print(f"Allowed hosts: {allowed_hosts} or URLs containing 'staging'.")
        sys.exit(1)
        
    # Check forbidden pattern
    if 'affairsandorder.com' in target or 'prod' in target:
        print(f"[SAFETY VIOLATION] Execution aborted! Target URL '{target}' matches forbidden production pattern 'affairsandorder.com' or 'prod'.")
        sys.exit(1)

def setup_test_user():
    username = f"stress_{int(time.time())}"
    password = "stresspassword123"
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    print(f"Creating stress test user '{username}' in local DB...")
    with get_db_connection() as conn:
        with conn.cursor() as db:
            db.execute(
                "INSERT INTO users (username, email, hash, date, auth_type) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (username, f"{username}@example.com", hashed, "2026-01-01", "normal")
            )
            uid = db.fetchone()[0]
            
            db.execute(
                "INSERT INTO stats (id, gold, location) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (uid, 10000000, "T")
            )
            db.execute(
                "INSERT INTO resources (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (uid,)
            )
            db.execute(
                "INSERT INTO proInfra (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (uid,)
            )
            db.execute(
                "INSERT INTO provinces (id, userId, land, cityCount, productivity) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (uid, uid, 100, 1, 50)
            )
            conn.commit()
    print(f"User {username} (id: {uid}) successfully created.")
    return username, password, uid

def cleanup_test_user(uid):
    print(f"Cleaning up stress test user (id: {uid}) from DB...")
    with get_db_connection() as conn:
        with conn.cursor() as db:
            db.execute("DELETE FROM provinces WHERE userId=%s", (uid,))
            db.execute("DELETE FROM proInfra WHERE id=%s", (uid,))
            db.execute("DELETE FROM resources WHERE id=%s", (uid,))
            db.execute("DELETE FROM stats WHERE id=%s", (uid,))
            db.execute("DELETE FROM users WHERE id=%s", (uid,))
            conn.commit()
    print("Cleanup completed.")

async def perform_requests(target_url, username, password, concurrency, total_requests):
    from bs4 import BeautifulSoup
    paths = [
        "/",
        "/health",
        "/ready",
        "/rankings",
        "/country",
        "/provinces",
        "/upgrades",
        "/military",
        "/statistics",
        "/news"
    ]
    
    results = []
    
    # Use ClientSession with a cookie jar
    async with aiohttp.ClientSession() as session:
        # Retrieve CSRF token
        login_url = f"{target_url.rstrip('/')}/login"
        print(f"Retrieving CSRF token from {login_url}...")
        async with session.get(login_url) as get_resp:
            if get_resp.status != 200:
                print(f"Failed to GET login page: HTTP {get_resp.status}")
                return []
            html = await get_resp.text()
            soup = BeautifulSoup(html, 'html.parser')
            csrf_input = soup.find('input', {'name': 'csrf_token'})
            if not csrf_input:
                print("CSRF token input not found in login page.")
                return []
            csrf_token = csrf_input.get('value', '')
            print(f"CSRF token obtained: {csrf_token[:8]}...")

        # Perform login
        print(f"Logging in user '{username}' to {target_url}...")
        login_data = {
            "username": username,
            "password": password,
            "csrf_token": csrf_token
        }
        async with session.post(login_url, data=login_data, allow_redirects=True) as response:
            content = await response.read()
            if response.status != 200 or b"Wrong username or password" in content or b"Please provide" in content:
                print(f"Failed to log in: HTTP {response.status}. Content length: {len(content)}")
                return []
            print("Login successful. Starting concurrent requests...")

        # Queue of requests
        queue = asyncio.Queue()
        for i in range(total_requests):
            path = paths[i % len(paths)]
            await queue.put(path)
            
        async def worker():
            while not queue.empty():
                path = await queue.get()
                url = f"{target_url.rstrip('/')}{path}"
                start_time = time.time()
                try:
                    async with session.get(url, timeout=15) as resp:
                        content = await resp.read()
                        latency = time.time() - start_time
                        
                        has_error = (
                            b"Internal Server Error" in content or
                            b"Traceback" in content or
                            b"UndefinedError" in content or
                            b"An internal server error" in content
                        )
                        
                        results.append({
                            "path": path,
                            "status": resp.status,
                            "latency": latency,
                            "success": resp.status == 200 and not has_error
                        })
                except Exception as e:
                    latency = time.time() - start_time
                    results.append({
                        "path": path,
                        "status": 0,
                        "latency": latency,
                        "success": False,
                        "error": str(e)
                    })
                queue.task_done()
                
        # Start workers
        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        
    return results

def calculate_percentile(data, percentile):
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c < len(sorted_data):
        return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)
    else:
        return sorted_data[f]

def generate_report(results, total_duration, concurrency, target_url):
    if not results:
        print("No results gathered.")
        return
        
    total_reqs = len(results)
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    
    latencies = [r["latency"] for r in results]
    success_latencies = [r["latency"] for r in successes]
    
    avg_latency = sum(latencies) / total_reqs if total_reqs > 0 else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    
    p50 = calculate_percentile(latencies, 50)
    p90 = calculate_percentile(latencies, 90)
    p95 = calculate_percentile(latencies, 95)
    p99 = calculate_percentile(latencies, 99)
    
    rps = total_reqs / total_duration if total_duration > 0 else 0
    
    # Path-level breakdown
    path_stats = {}
    for r in results:
        path = r["path"]
        if path not in path_stats:
            path_stats[path] = {"total": 0, "success": 0, "latencies": []}
        path_stats[path]["total"] += 1
        if r["success"]:
            path_stats[path]["success"] += 1
        path_stats[path]["latencies"].append(r["latency"])
        
    report_md = f"""# Stress Test Performance Report
Generated on: {datetime.now().isoformat()}
Target Host: {target_url}
Concurrency Level: {concurrency}

## Executive Summary
- **Total Requests**: {total_reqs}
- **Successful Requests**: {len(successes)} ({len(successes)/total_reqs*100:.2f}%)
- **Failed Requests**: {len(failures)} ({len(failures)/total_reqs*100:.2f}%)
- **Total Time Taken**: {total_duration:.3f} seconds
- **Requests Per Second (RPS)**: {rps:.2f}

## Latency Metrics
- **Minimum Latency**: {min_latency:.4f}s
- **Maximum Latency**: {max_latency:.4f}s
- **Average Latency**: {avg_latency:.4f}s
- **Median (50th percentile)**: {p50:.4f}s
- **90th percentile**: {p90:.4f}s
- **95th percentile**: {p95:.4f}s
- **99th percentile**: {p99:.4f}s

## Breakdown by Endpoint
| Endpoint | Requests | Success Rate | Avg Latency | Max Latency |
|----------|----------|--------------|-------------|-------------|
"""
    for path, stats in sorted(path_stats.items()):
        p_avg = sum(stats["latencies"]) / stats["total"] if stats["total"] > 0 else 0
        p_max = max(stats["latencies"]) if stats["latencies"] else 0
        p_success_rate = (stats["success"] / stats["total"]) * 100
        report_md += f"| {path} | {stats['total']} | {p_success_rate:.1f}% | {p_avg:.4f}s | {p_max:.4f}s |\n"

    # Save to scratch directory
    os.makedirs(os.path.join(ROOT, "scratch"), exist_ok=True)
    report_path = os.path.join(ROOT, "scratch", "stress_test_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
        
    results_json_path = os.path.join(ROOT, "scratch", "stress_test_results.json")
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "target": target_url,
            "concurrency": concurrency,
            "total_requests": total_reqs,
            "total_duration": total_duration,
            "rps": rps,
            "latencies": {
                "min": min_latency,
                "max": max_latency,
                "avg": avg_latency,
                "p50": p50,
                "p90": p90,
                "p95": p95,
                "p99": p99
            },
            "path_breakdown": {path: {"total": stats["total"], "success": stats["success"], "avg_latency": sum(stats["latencies"])/stats["total"]} for path, stats in path_stats.items()}
        }, f, indent=2)

    print("\n" + "="*40 + "\nSTRESS TEST COMPLETE\n" + "="*40)
    print(report_md)
    print(f"Saved markdown report to: {report_path}")
    print(f"Saved raw JSON results to: {results_json_path}")

def main():
    args = parse_args()
    validate_target(args.target)
    
    username, password, uid = setup_test_user()
    
    start_time = time.time()
    try:
        results = asyncio.run(perform_requests(
            target_url=args.target,
            username=username,
            password=password,
            concurrency=args.concurrency,
            total_requests=args.requests
        ))
        duration = time.time() - start_time
        generate_report(results, duration, args.concurrency, args.target)
    finally:
        cleanup_test_user(uid)

if __name__ == "__main__":
    main()
