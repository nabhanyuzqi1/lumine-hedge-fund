/**
 * Frontend Performance Metrics Collector
 *
 * Collects Web Vitals, rendering performance, memory usage, and network health
 * using browser native APIs without blocking critical rendering path.
 */

// Thresholds matching performance budgets
export const METRIC_THRESHOLDS = {
  FPS_NORMAL: 55,
  FPS_WARN: 45,
  LCP_WARN: 2.5, // seconds
  MEMORY_WARN_MB: 80,
  LONG_TASK_MS: 50,
} as const;

export type MetricEntry = {
  timestamp: number;
  fcp?: number;
  lcp?: number;
  tti?: number;
  fps?: number;
  memoryUsedMB?: number;
  longTaskCount?: number;
  queryLatencyMs?: number;
};

export type VitalsSnapshot = {
  fcp: number | null;
  lcp: number | null;
  tti: number | null;
};

export type MemoryReport = {
  usedMB: number;
  estimatedTotalMB: number;
  pressureLevel: 'low' | 'medium' | 'high';
};

export type PerformanceStatus = 'normal' | 'warn' | 'critical';

class MetricsCollector {
  private entries: MetricEntry[] = [];
  private maxEntries = 300; // 5 minutes at 10 samples/sec
  private vitals: VitalsSnapshot = { fcp: null, lcp: null, tti: null };
  private memoryObserver?: PerformanceObserver;
  private longTaskObserver?: PerformanceObserver;
  private paintObserver?: PerformanceObserver;
  private lcpObserver?: PerformanceObserver;
  private memoryFallbackInterval?: number;

  public init(): void {
    this.initPaintObserver();
    this.initLcpObserver();
    this.initLongTaskObserver();
    this.initMemoryObserver();
    this.startFpsSampler();
  }

  private initPaintObserver(): void {
    if (!('PerformanceObserver' in window)) return;

    try {
      this.paintObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name === 'first-contentful-paint') {
            this.vitals.fcp = entry.startTime / 1000; // Convert to seconds
            this.recordEntry();
          }
        }
      });
      this.paintObserver.observe({ type: 'paint', buffered: true });
    } catch {
      // Observer not supported or permission denied
    }
  }

  private initLcpObserver(): void {
    if (!('PerformanceObserver' in window)) return;

    try {
      this.lcpObserver = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const lastEntry = entries[entries.length - 1];
        this.vitals.lcp = lastEntry.startTime / 1000;
        this.vitals.tti = this.calculateTTI();
        this.recordEntry();
      });
      this.lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch {
      // Ignore
    }
  }

  private initLongTaskObserver(): void {
    if (!('PerformanceObserver' in window)) return;

    try {
      this.longTaskObserver = new PerformanceObserver((list) => {
        const entry = this.getOrCreateEntry();
        entry.longTaskCount = (entry.longTaskCount ?? 0) + list.getEntries().length;
      });
      this.longTaskObserver.observe({ type: 'longtask', buffered: true });
    } catch {
      // Ignore
    }
  }

  private initMemoryObserver(): void {
    if (!this.isMemoryApiAvailable()) return;

    try {
      this.memoryObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          const memory = (entry as { entryList?: Array<{ name?: string; value?: number }> }).entryList?.[0];
          if (memory?.name === 'js_heap_size_used') {
            const metricEntry = this.getOrCreateEntry();
            metricEntry.memoryUsedMB = Math.round((memory?.value ?? 0) / (1024 * 1024));
          }
        }
      });
      this.memoryObserver.observe({ type: 'resource', buffered: true });
    } catch {
      // Fallback to direct reading
      this.memoryFallbackInterval = setInterval(() => {
        const entry = this.getOrCreateEntry();
        entry.memoryUsedMB = Math.round((performance as any).memory?.usedJSHeapSize / (1024 * 1024));
      }, 1000) as unknown as number;
    }
  }

  private isMemoryApiAvailable(): boolean {
    return (
      'performance' in window &&
      'memory' in performance &&
      performance.memory !== undefined
    );
  }

  private calculateTTI(): number {
    // Simplified TTI: time when first long task ends + 500ms buffer
    const lastLongTask = this.entries.reduce((max, entry) => {
      const end = (entry.fcp ?? 0) + (entry.longTaskCount ?? 0) * 50;
      return end > (max ?? 0) ? end : max;
    }, 0);
    return Math.round((lastLongTask ?? 0) + 0.5) / 10;
  }

  private startFpsSampler(): void {
    if (typeof requestAnimationFrame === 'undefined') return;

    let lastTime = performance.now();
    let frameCount = 0;

    const measureFps = (currentTime: number) => {
      frameCount++;
      const delta = currentTime - lastTime;

      if (delta >= 1000) {
        const fps = Math.round((frameCount * 1000) / delta);
        this.getOrCreateEntry().fps = fps;
        frameCount = 0;
        lastTime = currentTime;
      }

      requestAnimationFrame(measureFps);
    };

    requestAnimationFrame(measureFps);
  }

  /**
   * Returns the most recent entry, creating one on demand so that
   * observers/samplers never write to a stale `undefined` entry before
   * the first paint event has arrived.
   */
  private getOrCreateEntry(): MetricEntry {
    if (this.entries.length === 0) {
      this.recordEntry();
    }
    return this.entries[this.entries.length - 1]!;
  }

  private recordEntry(): void {
    this.entries.push({
      timestamp: Date.now(),
      fcp: this.vitals.fcp ?? undefined,
      lcp: this.vitals.lcp ?? undefined,
      tti: this.vitals.tti ?? undefined,
      fps: undefined,
      memoryUsedMB: undefined,
      longTaskCount: undefined,
      queryLatencyMs: undefined,
    });

    if (this.entries.length > this.maxEntries) {
      this.entries.shift();
    }
  }

  public getVitalsSnapshot(): VitalsSnapshot {
    return { ...this.vitals };
  }

  public getMemoryReport(): MemoryReport {
    const usedBytes = (performance as any)?.memory?.usedJSHeapSize ?? 0;
    const usedMB = Math.round(usedBytes / (1024 * 1024));

    // Estimate total from device memory
    const deviceMem = (navigator as any).deviceMemory ?? 4;
    const estimatedTotalMB = deviceMem * 1024;

    let pressureLevel: 'low' | 'medium' | 'high' = 'low';
    const usagePercent = (usedMB / estimatedTotalMB) * 100;
    if (usagePercent > 70) pressureLevel = 'high';
    else if (usagePercent > 50) pressureLevel = 'medium';

    return { usedMB, estimatedTotalMB, pressureLevel };
  }

  public getRenderHealth(): { avgFps: number; longTaskCount: number; framesDropped: number } {
    const recent = this.entries.slice(-60); // Last ~1 minute
    const avgFps =
      recent.filter((e) => e.fps !== undefined).reduce((sum, e) => sum + (e.fps ?? 0), 0) /
      Math.max(recent.filter((e) => e.fps !== undefined).length, 1);

    const longTaskCount = recent.reduce((sum, e) => sum + (e.longTaskCount ?? 0), 0);
    const framesDropped = recent.filter((e) => (e.fps ?? 60) < 55).length;

    return { avgFps, longTaskCount, framesDropped };
  }

  public getLastEntry(): MetricEntry | null {
    return this.entries[this.entries.length - 1] ?? null;
  }

  public getAllEntries(): MetricEntry[] {
    return [...this.entries];
  }

  public clear(): void {
    this.entries = [];
    this.vitals = { fcp: null, lcp: null, tti: null };
  }

  public dispose(): void {
    this.paintObserver?.disconnect();
    this.lcpObserver?.disconnect();
    this.longTaskObserver?.disconnect();
    this.memoryObserver?.disconnect();
    if (this.memoryFallbackInterval !== undefined) {
      clearInterval(this.memoryFallbackInterval);
      this.memoryFallbackInterval = undefined;
    }
    this.clear();
  }
}

// Singleton instance
export const metricsCollector = new MetricsCollector();
