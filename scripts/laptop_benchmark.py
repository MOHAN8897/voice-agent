"""Quick laptop benchmark: CPU single/multi-core, memory bandwidth, disk speed."""
import os
import time
import tempfile
import multiprocessing


def cpu_task(n):
    """Mixed integer workload (trial-division prime count)."""
    count = 0
    for i in range(2, n):
        is_p = True
        j = 2
        while j * j <= i:
            if i % j == 0:
                is_p = False
                break
            j += 1
        if is_p:
            count += 1
    return count


def mem_task(size_mb):
    """Memory bandwidth: copy a large bytearray repeatedly."""
    src = bytearray(size_mb * 1024 * 1024)
    dst = bytearray(size_mb * 1024 * 1024)
    reps = 8
    t0 = time.perf_counter()
    for _ in range(reps):
        dst[:] = src
    dt = time.perf_counter() - t0
    return (size_mb * reps) / dt  # MB/s


def bench_disk(path_dir):
    """64 MiB temporary-file I/O; reads include OS caching, not raw SSD speed."""
    data = os.urandom(4 * 1024 * 1024)
    with tempfile.TemporaryFile(dir=path_dir) as f:
        t0 = time.perf_counter()
        for _ in range(16):
            f.write(data)
        f.flush()
        os.fsync(f.fileno())
        wt = time.perf_counter() - t0
        f.seek(0)
        t0 = time.perf_counter()
        total = 0
        while chunk := f.read(1024 * 1024):
            total += len(chunk)
        rt = time.perf_counter() - t0
        assert total == 64 * 1024 * 1024
    return 64 / wt, 64 / rt  # MiB/s


if __name__ == "__main__":
    print("=" * 60)
    print("LAPTOP BENCHMARK")
    print("=" * 60)

    t0 = time.perf_counter()
    cpu_task(20000)
    st = time.perf_counter() - t0
    print(f"\n[CPU] Single-core (primes < 20000): {st:.2f}s")

    procs = multiprocessing.cpu_count()
    t0 = time.perf_counter()
    with multiprocessing.Pool(procs) as pool:
        pool.map(cpu_task, [20000] * procs)
    mt = time.perf_counter() - t0
    print(f"[CPU] {procs} prime-count tasks / {procs} workers: {mt:.2f}s (includes process startup; not a scaling score)")

    bw = mem_task(32)
    print(f"[RAM] Python copy payload throughput: {bw:,.0f} MiB/s")

    tmpdir = tempfile.gettempdir()
    w, r = bench_disk(tmpdir)
    print(f"[DISK] Temp-file flushed write: {w:,.0f} MiB/s | Cached read: {r:,.0f} MiB/s (not raw SSD speed)")

    try:
        import psutil
        vm = psutil.virtual_memory()
        print(f"[RAM] Total: {vm.total/1e9:.1f} GB | Available: {vm.available/1e9:.1f} GB")
    except ImportError:
        print("[RAM] psutil not installed; skipped free-RAM check")

    print("\nDone.")