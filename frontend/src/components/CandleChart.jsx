// CandleChart — candlestick + volume berbasis TradingView lightweight-charts.
// Bar historis DAN bar baru WAJIB berasal dari GET /candles (sumber kebenaran).
// Tick SSE hanya memperbarui high/low/close bar terakhir bila bucket tick sama
// dengan bucket bar terakhir; tick tidak pernah membuka bar baru (dulu muncul
// candle datar + gap saat bucket tick tidak cocok dengan ts bar server).
// Bar baru datang dari polling ringan /candles (limit kecil) tiap 20 detik.
// Aman untuk data kosong/error/loading: chart tetap ter-mount dan status
// ditampilkan sebagai overlay, bukan crash.
//
// Scrollback: geser chart ke kiri memicu fetch limit lebih besar (endpoint
// hanya mendukung limit), candle lama di-prepend, lalu viewport digeser
// sebesar jumlah bar baru supaya zoom/pilihan user tidak reset.
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
} from 'lightweight-charts'
import { buildOverlays, tradeMarkers } from '../lib/chartOrders'
import {
  DEFAULT_LIMIT,
  MAX_LIMIT,
  bucketStart,
  fetchCandles,
  mergeBars,
  tickMs,
} from '../lib/candles'
import { SYMBOLS } from '../lib/market'
import { useTick } from '../lib/useDesk'

const UP = '#10b981'
const DOWN = '#ef4444'
const GRID = '#18181b'
const SURFACE = '#111113'
const BORDER = 'rgba(39, 39, 42, 0.8)'
const TEXT = '#8b909e'
const UP_VOL = 'rgba(16, 185, 129, 0.45)'
const DOWN_VOL = 'rgba(239, 68, 68, 0.45)'
// Jumlah bar yang terlihat setelah load: 500 bar penuh membuat candle
// selebar rambut, jadi viewport awal sengaja di-zoom ke periode terakhir.
const VISIBLE_BARS = 140
// Ambang jarak (dalam bar) ke tepi kiri yang memicu fetch historis.
const SCROLL_EDGE = 12
// Polling ringan untuk bar baru (bukan tick): /candles limit kecil.
// 1 detik = bar M1 terlihat bergerak dalam <=1s. Penghematan: hanya saat tab
// terlihat (visibilitychange) DAN pasar OPEN; timernya setTimeout berantai
// (bukan setInterval) sehingga tidak ada request bertumpuk saat jaringan lambat.
const TAIL_REFRESH_MS = 1000

function volumeBar(bar) {
  return {
    time: bar.time,
    value: bar.volume || 0,
    color: bar.close >= bar.open ? UP_VOL : DOWN_VOL,
  }
}

export default function CandleChart({
  symbol = 'XAUUSD',
  timeframe = 'M5',
  initialLimit = DEFAULT_LIMIT,
  height = 460,
  className = '',
  onCrosshair,
  marketStatus = null,
  // Order & posisi nyata dari store desk: digambar sebagai garis harga
  // (entry/SL/TP, pending) dan marker eksekusi langsung di chart.
  positions = [],
  orders = [],
}) {
  const wrapRef = useRef(null)
  const chartRef = useRef(null)
  const candleRef = useRef(null)
  const volumeRef = useRef(null)
  const priceLineRef = useRef(null)
  const barsRef = useRef([])
  const activeTfRef = useRef(timeframe)
  const limitRef = useRef(DEFAULT_LIMIT)
  const exhaustedRef = useRef(false)
  const loadingMoreRef = useRef(false)
  const liveRef = useRef(null)
  const crosshairRef = useRef(onCrosshair)
  // IPriceLine milik order overlay dan plugin marker: disimpan supaya bisa
  // dihapus tepat saat simbol/posisi berubah (tidak menumpuk, tidak bocor).
  const tradeLinesRef = useRef([])
  const markersRef = useRef(null)
  // Fungsi gambar overlay disimpan di ref agar efek load data bisa memanggil
  // versi terbaru tanpa ikut menjadi dependency (tidak memicu refetch).
  const drawTradeRef = useRef(null)
  // true saat fetch awal berjalan: polling tail menunggu agar tidak menimpa
  // data penuh dengan potongan 3 bar.
  const initialLoadRef = useRef(false)
  // guard satu-request: tail polling 1s tidak boleh menumpuk.
  const tailInFlightRef = useRef(false)
  // Market tutup: tick tidak boleh menambah/menggeser bar sama sekali.
  const closedRef = useRef(marketStatus?.status === 'CLOSED')

  const [status, setStatus] = useState('loading')
  const [error, setError] = useState('')
  const [fallbackTf, setFallbackTf] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [barCount, setBarCount] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)

  const tick = useTick()

  useEffect(() => {
    closedRef.current = marketStatus?.status === 'CLOSED'
    // Label harga terakhir: "LIVE" hanya jujur saat pasar buka; saat pasar
    // tutup garis itu menandai harga penutupan terakhir.
    if (priceLineRef.current) {
      priceLineRef.current.applyOptions({ title: closedRef.current ? 'LAST' : 'LIVE' })
    }
  }, [marketStatus])

  // Callback halaman bisa berupa arrow inline; simpan di ref agar
  // subscription crosshair tidak dibuat ulang setiap render.
  useEffect(() => {
    crosshairRef.current = onCrosshair
  }, [onCrosshair])

  const setPriceLine = useCallback((price) => {
    const series = candleRef.current
    if (!series || !Number.isFinite(price)) return
    if (priceLineRef.current) {
      priceLineRef.current.applyOptions({ price })
      return
    }
    priceLineRef.current = series.createPriceLine({
      price,
      color: 'rgba(244, 245, 248, 0.55)',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: closedRef.current ? 'LAST' : 'LIVE',
    })
  }, [])

  const clearPriceLine = useCallback(() => {
    const series = candleRef.current
    if (series && priceLineRef.current) {
      try {
        series.removePriceLine(priceLineRef.current)
      } catch {
        // chart sudah dibuang; tidak ada yang perlu dirapikan
      }
    }
    priceLineRef.current = null
  }, [])

  // ── overlay order (entry/SL/TP, pending) + marker eksekusi ────────────────
  // Digambar ulang setiap posisi/order/simbol berubah: harga garis ikut
  // bergerak saat posisi dibuka/ditutup, dan tidak ada garis yang tertinggal
  // dari simbol sebelumnya.
  const drawTrade = useCallback(() => {
    const series = candleRef.current
    if (!series) return
    const digits = (SYMBOLS[symbol] && SYMBOLS[symbol].digits) || 2
    for (const line of tradeLinesRef.current) {
      try {
        series.removePriceLine(line)
      } catch {
        // chart sudah dibuang; tidak ada yang perlu dirapikan
      }
    }
    tradeLinesRef.current = []
    for (const o of buildOverlays({ positions, orders, symbol, digits })) {
      if (!Number.isFinite(o.price)) continue
      try {
        tradeLinesRef.current.push(series.createPriceLine({
          price: o.price,
          color: o.color,
          // entry = garis tegas (lineWidth 2), SL/TP/pending = putus-putus
          lineWidth: o.dashed ? 1 : 2,
          lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid,
          axisLabelVisible: true,
          title: o.title,
        }))
      } catch {
        // harga di luar rentang skala: lewati, chart tetap jalan
      }
    }
    if (markersRef.current) {
      markersRef.current.setMarkers(
        tradeMarkers({ orders, positions, bars: barsRef.current, symbol, digits }),
      )
    }
  }, [positions, orders, symbol])

  useEffect(() => {
    drawTradeRef.current = drawTrade
  }, [drawTrade])

  useEffect(() => {
    drawTrade()
  }, [drawTrade])

  // ── chart sekali per mount ────────────────────────────────────────────────
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return

    const chart = createChart(el, {
      autoSize: false,
      width: el.clientWidth || 600,
      height: el.clientHeight || height,
      layout: {
        background: { type: ColorType.Solid, color: SURFACE },
        textColor: TEXT,
        fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
        fontSize: 11,
        attributionLogo: false,
        panes: {
          separatorColor: BORDER,
          separatorHoverColor: 'rgba(16, 185, 129, 0.25)',
          enableResize: false,
        },
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      rightPriceScale: {
        borderColor: BORDER,
        scaleMargins: { top: 0.1, bottom: 0.08 },
        // harga selalu rata kanan dengan lebar digit stabil (tabular)
        entireTextOnly: true,
      },
      timeScale: {
        borderColor: BORDER,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 4,
        barSpacing: 6,
        lockVisibleTimeRangeOnResize: true,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: 'rgba(244, 245, 248, 0.28)',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#27272a',
        },
        horzLine: {
          color: 'rgba(244, 245, 248, 0.28)',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#27272a',
        },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
      // Label harga terakhir dipegang price line (dashed, bertanda LIVE)
      // supaya tidak ada dua label bertumpuk di price scale.
      priceLineVisible: false,
      lastValueVisible: false,
    })

    // Volume di pane terpisah di bawah harga (pane index 1).
    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    )

    // Pane volume ±22% tinggi chart; dibungkus try karena API pane bisa
    // berubah antar versi minor.
    try {
      const volumePane = chart.panes()[1]
      if (volumePane && typeof volumePane.setStretchFactor === 'function') {
        volumePane.setStretchFactor(0.28)
      }
    } catch {
      // tanpa stretch factor volume tetap tampil dengan tinggi bawaan
    }

    markersRef.current = createSeriesMarkers(candleSeries, [])

    chartRef.current = chart
    candleRef.current = candleSeries
    volumeRef.current = volumeSeries

    // Sinkronisasi ukuran chart ke container. Tiga jalur dipakai sekaligus
    // karena masing-masing bisa gagal: ResizeObserver (normal), window.resize
    // (rotasi/pembesaran jendela), dan interval 500ms sebagai jaring pengaman
    // untuk lingkungan yang tidak memicu keduanya (mis. emulasi viewport,
    // panel yang dibuka-tutup tanpa reflow event). applyOptions hanya dipanggil
    // saat ukuran benar-benar berubah, jadi biayanya dapat diabaikan.
    let lastW = 0
    let lastH = 0
    const resize = () => {
      const rect = el.getBoundingClientRect()
      const w = Math.floor(rect.width)
      const h = Math.floor(rect.height)
      if (w <= 0 || h <= 0 || (w === lastW && h === lastH)) return
      lastW = w
      lastH = h
      // v5: chart.resize() ikut menghitung ulang kanvas per pane. applyOptions
      // hanya mengubah elemen luar, kanvas di dalam tetap ukuran lama sehingga
      // chart terpotong (skala harga hilang di layar sempit).
      if (typeof chart.resize === 'function') chart.resize(w, h)
      else chart.applyOptions({ width: w, height: h })
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    window.addEventListener('resize', resize)
    const sizeTimer = setInterval(resize, 500)

    return () => {
      clearInterval(sizeTimer)
      window.removeEventListener('resize', resize)
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
      priceLineRef.current = null
      markersRef.current = null
      tradeLinesRef.current = []
    }
    // height hanya dipakai sebagai ukuran awal; perubahan ukuran nyata
    // ditangani ResizeObserver.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── load historis saat symbol/timeframe berubah ───────────────────────────
  useEffect(() => {
    const chart = chartRef.current
    const series = candleRef.current
    if (!chart || !series) return

    const ctrl = new AbortController()
    let cancelled = false
    const digits = (SYMBOLS[symbol] && SYMBOLS[symbol].digits) || 2
    series.applyOptions({
      priceFormat: { type: 'price', precision: digits, minMove: 1 / 10 ** digits },
    })

    // reset state chart untuk simbol/timeframe baru
    barsRef.current = []
    liveRef.current = null
    exhaustedRef.current = false
    activeTfRef.current = timeframe
    limitRef.current = Math.min(MAX_LIMIT, Math.max(VISIBLE_BARS, initialLimit))
    clearPriceLine()
    series.setData([])
    if (volumeRef.current) volumeRef.current.setData([])
    setStatus('loading')
    setError('')
    setFallbackTf(null)
    setBarCount(0)
    initialLoadRef.current = true

    fetchCandles({ symbol, timeframe, limit: limitRef.current, signal: ctrl.signal })
      .then((res) => {
        if (cancelled) return
        activeTfRef.current = res.tf
        setFallbackTf(res.fallback ? res.tf : null)
        if (!res.candles.length) {
          setStatus('empty')
          return
        }
        barsRef.current = res.candles
        series.setData(res.candles)
        if (volumeRef.current) volumeRef.current.setData(res.candles.map(volumeBar))
        exhaustedRef.current = res.exhausted
        // viewport awal: bar terakhir ± VISIBLE_BARS (bukan fitContent)
        const from = Math.max(0, res.candles.length - VISIBLE_BARS)
        chart.timeScale().setVisibleLogicalRange({ from, to: res.candles.length + 2 })
        setPriceLine(res.candles[res.candles.length - 1].close)
        setBarCount(res.candles.length)
        setStatus('ready')
        // Bar sudah terpasang: marker eksekusi boleh menempel ke candle-nya.
        drawTradeRef.current?.()
      })
      .catch((ex) => {
        if (cancelled || !ex || ex.code === 'ABORT') return
        setError(ex.message || 'Gagal memuat candle')
        setStatus('error')
      })
      .finally(() => {
        if (!cancelled) initialLoadRef.current = false
      })

    return () => {
      cancelled = true
      initialLoadRef.current = false
      ctrl.abort()
    }
  }, [symbol, timeframe, initialLimit, reloadKey, clearPriceLine, setPriceLine])

  // ── scrollback: geser ke kiri -> muat batch historis lebih lama ───────────
  const loadOlder = useCallback(async () => {
    const chart = chartRef.current
    const series = candleRef.current
    if (!chart || !series) return
    if (loadingMoreRef.current || exhaustedRef.current) return
    const curLimit = limitRef.current
    if (curLimit >= MAX_LIMIT) {
      exhaustedRef.current = true
      return
    }
    const nextLimit = Math.min(MAX_LIMIT, Math.max(curLimit + 250, curLimit * 2))
    const prevBars = barsRef.current
    const prevCount = prevBars.length
    if (!prevCount) return
    const range = chart.timeScale().getVisibleLogicalRange()

    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const res = await fetchCandles({ symbol, timeframe: activeTfRef.current, limit: nextLimit })
      limitRef.current = nextLimit
      exhaustedRef.current = res.exhausted
      const merged = mergeBars(prevBars, res.candles, liveRef.current)
      barsRef.current = merged
      series.setData(merged)
      if (volumeRef.current) volumeRef.current.setData(merged.map(volumeBar))
      const delta = merged.length - prevCount
      // Bar ditambahkan di kiri: geser viewport sebesar delta supaya user
      // tetap melihat candle yang sama (zoom tidak reset).
      if (range && delta > 0) {
        const span = range.to - range.from
        let from = range.from + delta
        let to = range.to + delta
        // Jangan melewati ujung kanan data: geser balik seperlunya dengan
        // lebar viewport tetap (zoom user tidak berubah).
        const maxTo = merged.length - 1 + 4
        if (to > maxTo) {
          to = maxTo
          from = to - span
        }
        chart.timeScale().setVisibleLogicalRange({ from, to })
      }
      setBarCount(merged.length)
    } catch {
      // Kegagalan scrollback tidak boleh mengosongkan chart yang sudah tampil;
      // chart berhenti memuat sampai user menggeser lagi.
    } finally {
      loadingMoreRef.current = false
      setLoadingMore(false)
    }
  }, [symbol])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const onRange = (range) => {
      if (!range) return
      // Dekat tepi kiri -> user butuh sejarah lebih lama.
      if (range.from <= SCROLL_EDGE) loadOlder()
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRange)
    return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange)
  }, [loadOlder])

  // ── crosshair -> halaman (readout O/H/L/C) ────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const onMove = (param) => {
      const cb = crosshairRef.current
      if (!cb) return
      const series = candleRef.current
      if (!param || param.time == null || !series) {
        cb(null)
        return
      }
      const bar = param.seriesData.get(series)
      if (!bar) {
        cb(null)
        return
      }
      cb({
        time: param.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })
    }
    chart.subscribeCrosshairMove(onMove)
    return () => chart.unsubscribeCrosshairMove(onMove)
  }, [])

  // ── bar baru: polling ringan /candles (bukan dari tick) ───────────────────
  // Menjaga time = detik awal bucket, urut naik, tanpa duplikat; volume selalu
  // nilai server. Tick hanya menyentuh high/low/close bar terakhir (lihat efek
  // di bawah), jadi tidak ada candle datar/gap buatan client.
  const refreshTail = useCallback(async () => {
    const series = candleRef.current
    if (!series || !symbol) return
    if (initialLoadRef.current) return
    // Satu request tail pada satu waktu: pada 1 detik, jaringan lambat tidak
    // boleh menumpuk antrean fetch (lonjakan request saat tab lama terbuka).
    if (tailInFlightRef.current) return
    tailInFlightRef.current = true
    const tf = activeTfRef.current
    try {
      const res = await fetchCandles({ symbol, timeframe: tf, limit: 2 })
      const incoming = res.candles
      if (!incoming.length) return
      const bars = barsRef.current
      if (!bars.length) {
        barsRef.current = incoming
        series.setData(incoming)
        if (volumeRef.current) volumeRef.current.setData(incoming.map(volumeBar))
        setPriceLine(incoming[incoming.length - 1].close)
        setBarCount(incoming.length)
        setStatus('ready')
        drawTradeRef.current?.()
        return
      }
      let changed = false
      for (const bar of incoming) {
        const last = bars[bars.length - 1]
        if (bar.time > last.time) {
          // bucket baru dari server: ini satu-satunya cara bar baru muncul
          bars.push(bar)
          series.update(bar)
          if (volumeRef.current) volumeRef.current.update(volumeBar(bar))
          changed = true
        } else if (bar.time === last.time) {
          // bucket sama: OHLC server menang, ekstrem lokal dipertahankan,
          // volume tetap nilai server (tidak diakumulasi ganda)
          const merged = {
            ...bar,
            high: Math.max(bar.high, last.high),
            low: Math.min(bar.low, last.low),
          }
          if (
            merged.open === last.open &&
            merged.high === last.high &&
            merged.low === last.low &&
            merged.close === last.close &&
            merged.volume === last.volume
          ) continue
          bars[bars.length - 1] = merged
          series.update(merged)
          if (volumeRef.current) volumeRef.current.update(volumeBar(merged))
          changed = true
        }
      }
      if (!changed) return
      liveRef.current = null
      setPriceLine(bars[bars.length - 1].close)
      setBarCount(bars.length)
      // Bar baru di kanan: marker yang jatuh di bar itu ikut tampil.
      drawTradeRef.current?.()
    } catch {
      // Diam: chart tetap menampilkan data terakhir yang sah.
    } finally {
      tailInFlightRef.current = false
    }
  }, [symbol, setPriceLine])

  useEffect(() => {
    if (!symbol) return undefined
    // Pasar tutup: tidak ada bar baru, jadi polling dihentikan total (badge
    // MARKET TUTUP tetap tampil dari halaman).
    if (marketStatus?.status === 'CLOSED') return undefined

    let timer = null
    let cancelled = false

    const stop = () => {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }

    // Interval TETAP 1 detik (bukan setTimeout berantai): request yang lambat
    // tidak memperpanjang jarak antar-poll. refreshTail() punya guard
    // in-flight, jadi tidak ada request bertumpuk saat jaringan lambat.
    function runOnce() {
      if (cancelled) return
      // Tab tersembunyi: jangan menyentuh jaringan (browser juga men-throttle
      // timer, tapi cek eksplisit membuat perilakunya pasti).
      if (document.visibilityState !== 'visible') return
      refreshTail()
    }

    // Kembali ke tab: satu refresh langsung, bukan menunggu tick berikutnya.
    const onVisibility = () => {
      if (document.visibilityState === 'visible') runOnce()
    }

    document.addEventListener('visibilitychange', onVisibility)
    timer = setInterval(runOnce, TAIL_REFRESH_MS)
    return () => {
      cancelled = true
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [symbol, refreshTail, marketStatus?.status])

  // ── realtime: tick terakhir hanya memperbarui bar terakhir (bucket sama) ──
  useEffect(() => {
    if (!tick || tick.symbol !== symbol) return
    const series = candleRef.current
    if (!series) return
    const price = Number(tick.price)
    if (!Number.isFinite(price)) return
    // Pasar tutup: tick beku / tidak ada tick berarti tidak ada perubahan bar.
    if (closedRef.current) return
    const bars = barsRef.current
    if (!bars.length) return

    const ms = tickMs(tick.ts)
    const time = Math.floor(bucketStart(ms == null ? Date.now() : ms, activeTfRef.current) / 1000)
    const last = bars[bars.length - 1]
    if (time !== last.time) {
      // Bucket beda: bar baru TIDAK dibuat dari tick (tunggu /candles). Harga
      // live tetap ditampilkan lewat price line supaya trader tidak buta.
      setPriceLine(price)
      return
    }
    const bar = {
      ...last,
      high: Math.max(last.high, price),
      low: Math.min(last.low, price),
      close: price,
    }
    bars[bars.length - 1] = bar

    liveRef.current = bar
    series.update(bar)
    if (volumeRef.current) volumeRef.current.update(volumeBar(bar))
    setPriceLine(price)
  }, [tick, symbol, setPriceLine])

  const stateLabel =
    status === 'loading'
      ? `Memuat candle ${symbol} ${timeframe}…`
      : status === 'empty'
        ? `Belum ada candle ${symbol} ${timeframe}.`
        : error

  return (
    <div
      className={`candlechart ${className}`.trim()}
      style={{ height }}
      aria-busy={status === 'loading'}
    >
      <div
        ref={wrapRef}
        className="candlechart-canvas"
        role="img"
        aria-label={`Chart candlestick ${symbol} ${timeframe}${barCount ? `, ${barCount} candle` : ''}`}
      />
      {status !== 'ready' && (
        <div className={`candlechart-state ${status === 'error' ? 'is-error' : ''}`} role="status">
          <span>{stateLabel}</span>
          {status === 'error' && (
            <button type="button" className="btn btn-ghost candlechart-retry" onClick={() => setReloadKey((k) => k + 1)}>
              Coba lagi
            </button>
          )}
        </div>
      )}
      {status === 'ready' && fallbackTf && (
        <div className="candlechart-note" role="status">
          TF {timeframe} belum tersedia di server; menampilkan {fallbackTf}.
        </div>
      )}
      {loadingMore && (
        <div className="candlechart-more" role="status">
          memuat riwayat…
        </div>
      )}
    </div>
  )
}
