import asyncio
import time
from typing import List
from app.browser.manager import manager
from app.extractor.extractor import extractor
from app.compressor.compressor import compressor
from app.classifier.classifier import classifier
from app.cache.cache import semantic_cache
from app.metrics.metrics import metrics

# List of URLs to benchmark. Using stable public pages.
BENCHMARK_URLS = [
    "https://example.com",
    "https://www.google.com",
    "https://news.ycombinator.com",
]

async def run_benchmark():
    print("=" * 70)
    print("      BROWSER OPTIMIZER MCP — PERFORMANCE BENCHMARK SUITE")
    print("=" * 70)
    
    print("\nStarting browser session...")
    await manager.start()
    
    results = []
    
    try:
        for idx, url in enumerate(BENCHMARK_URLS, 1):
            print(f"\n[{idx}/{len(BENCHMARK_URLS)}] Benchmarking: {url}")
            
            # --- RUN 1: FRESH LOAD (CACHE MISS) ---
            start_time = time.time()
            page = await manager.navigate(url)
            load_latency = time.time() - start_time
            
            # Extract
            start_extract = time.time()
            extracted = await extractor.extract(page)
            extract_latency = time.time() - start_extract
            
            # Compress
            start_compress = time.time()
            compressed = compressor.compress(extracted)
            compress_latency = time.time() - start_compress
            
            # Classify
            classification = classifier.classify(compressed)
            
            # Store in cache
            html = await page.content()
            semantic_cache.store(url, html, compressed)
            
            raw_size = extracted["raw_html_length"]
            compressed_size = compressed["compressed_length"]
            ratio = compressed["compression_ratio"]
            
            # --- RUN 2: CACHED LOAD (CACHE HIT) ---
            start_cached = time.time()
            cached_context = semantic_cache.lookup(url, html)
            cached_latency = time.time() - start_cached
            
            results.append({
                "url": url,
                "raw_size": raw_size,
                "compressed_size": compressed_size,
                "ratio": ratio,
                "page_type": classification["page_type"],
                "load_time_ms": int(load_latency * 1000),
                "compress_time_ms": int(compress_latency * 1000),
                "cache_hit_time_ms": round(cached_latency * 1000, 3)
            })
            
            # Update metrics
            metrics.record_compression(raw_size, compressed_size)
            if cached_context:
                metrics.record_cache_hit()
            else:
                metrics.record_cache_miss()
                
            print(f" -> Raw Size: {raw_size:,} bytes")
            print(f" -> Compressed Size: {compressed_size:,} bytes")
            print(f" -> Reduction: {ratio}%")
            print(f" -> Page Type Classified: {classification['page_type'].upper()}")
            print(f" -> Fresh Load + Compress Latency: {int((load_latency + compress_latency) * 1000)}ms")
            print(f" -> Cache Lookup Latency: {round(cached_latency * 1000, 3)}ms")
            
    finally:
        print("\nStopping browser session...")
        await manager.stop()

    # --- PRINT FINAL BENCHMARK SUMMARY TABLE ---
    print("\n" + "=" * 90)
    print("                             BENCHMARK RESULTS SUMMARY")
    print("=" * 90)
    print(f"{'URL':<30} | {'Raw Size':<10} | {'Opt Size':<10} | {'Savings':<8} | {'Classified':<10} | {'Cache Hit (ms)':<14}")
    print("-" * 90)
    
    total_raw = 0
    total_opt = 0
    
    for r in results:
        total_raw += r["raw_size"]
        total_opt += r["compressed_size"]
        # Truncate long URLs for formatting
        url_disp = r["url"] if len(r["url"]) <= 30 else r["url"][:27] + "..."
        print(f"{url_disp:<30} | {r['raw_size']:<10,} | {r['compressed_size']:<10,} | {r['ratio']:<7}% | {r['page_type'].upper():<10} | {r['cache_hit_time_ms']:<14}")
        
    print("-" * 90)
    avg_ratio = round((1 - total_opt / total_raw) * 100, 1) if total_raw > 0 else 0
    print(f"{'TOTAL / AVERAGE':<30} | {total_raw:<10,} | {total_opt:<10,} | {avg_ratio:<7}% | {'N/A':<10} | {'N/A':<14}")
    print("=" * 90)
    print(f"Overall Context reduction: {avg_ratio}%")
    print(f"Total network bytes saved: {total_raw - total_opt:,} bytes")
    print("=" * 90)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
