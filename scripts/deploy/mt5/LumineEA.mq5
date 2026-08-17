//+------------------------------------------------------------------+
//| LumineEA.mq5 — HTTP bridge agent untuk Lumine Hedge Fund (v4)    |
//| Transport: HTTP polling (bypass demo account socket block)       |
//| Redis HTTP Proxy: GET /commands?timeout=1 → BRPOP mt5:commands   |
//|                   POST /results   → PUBLISH mt5:results          |
//|                   POST /ticks     → LPUSH mt5:ticks              |
//|                   POST /seed/bars → LPUSH mt5:seed              |
//|                                                                   |
//| v4 FEATURES:
//|  - UI panel di chart (version, seed phase, ticks, spread, session H/L,
//|    equity, margin, leverage, net P&L) — klik tombol SEED/RESEED/STATUS
//|  - Command handler baru: SEED_NOW, RESEED, STATUS, PANEL_TOGGLE
//|  - Seed WAJIB ON (InpForceSeed=true default; hapus GV seed-done)
//|  - Status push tiap 5s: version, build, ticks, spread, session H/L,
//|    account metrics (equity, balance, margin, free, leverage, net P&L)
//| v3 STABILITY:                                                     |
//|  - Result queue + retry (order result TIDAK PERNAH hilang)        |
//|  - Exponential backoff saat proxy down (1→2→4→...→60s),          |
//|    instant recovery, log hanya saat state berubah                |
//|  - Tick skip saat bid/ask = 0 (market closed)                    |
//|  - Filling-mode fallback FOK→IOC→RETURN (retcode 10030 fix)      |
//|  - Volume normalization (step/min/max)                           |
//|  - Seed non-blocking: 1 chunk per OnTimer, multi-TF, paginated   |
//|    (M1,M5,M15,H1,H4,D1 — chart 5m/15m/4H lengkap)                |
//|  - State persist via GlobalVariables (survive re-init reason 3)  |
//|  - Self-heal: tidak pernah ExpertRemove, selalu retry            |
//+------------------------------------------------------------------+
#property copyright "Lumine"
#property version   "4.10"
#property strict

input string  InpProxyURL    = "http://lumine.biz.id/mt5-proxy"; // Redis HTTP proxy URL (via Caddy)
input bool    InpSeedHistory = true;    // Seed history bars multi-TF saat start
input int     InpSeedChunks  = 1000;    // Bar per chunk seed (100-1000)
input int     InpMaxBackoff  = 60;      // Detik backoff maksimum saat proxy down
input int     InpPositionsInterval = 10;  // Detik antar snapshot positions (B1 sync)
input int     InpDealsInterval    = 30;  // Detik antar snapshot deals/history
input bool    InpShowPanel   = true;    // Tampilkan panel UI di chart
input bool    InpForceSeed   = true;    // WAJIB ON: paksa seed ulang tiap start
input int     InpStatusInterval = 5;    // Detik antar push status ke Redis
input int     InpPollMs      = 1000;    // Interval siklus OnTimer (ms): 250-5000.
                                         // <1000 memakai EventSetMillisecondTimer;
                                         // default 1000 = 1 detik (hemat CPU).
                                         // 250 = polling 4x/detik (paling responsif).

// ── Global State ──────────────────────────────────────────────────────────
string   g_proxyURL;
string   g_orderId;                 // order_id command aktif (result sync)
datetime g_lastTickSent   = 0;      // terakhir tick BERHASIL dikirim
datetime g_lastCmdPoll    = 0;
datetime g_lastPositionsSent = 0;   // B1: terakhir snapshot positions dikirim
datetime g_lastDealsSent      = 0;   // B1: terakhir snapshot deals dikirim
int      g_failCount      = 0;      // consecutive proxy failure
bool     g_proxyDown      = false;  // log state-change saja
int      g_maxBackoff;

// ── Result queue (persist: order result harus sampai ke backend) ──────────
#define RESULT_QUEUE_MAX 128
string   g_resultQueue[RESULT_QUEUE_MAX];
int      g_resultCount = 0;

// ── Seed state machine (non-blocking) ────────────────────────────────────
bool     g_seedEnabled;
int      g_seedChunkSize;
int      g_seedPhase     = 0;       // 0=idle 1=running 2=done
int      g_seedSymIdx    = 0;
int      g_seedTfIdx     = 0;
int      g_seedOffset    = 0;       // offset CopyRates pagination
int      g_seedTotal     = 0;
int      g_seedSent      = 0;

string   g_seedSymbols[] = {"XAUUSD"};
ENUM_TIMEFRAMES g_seedTfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
string   g_seedTfNames[] = {"1m", "5m", "15m", "1h", "4h", "1d"};

#define GV_SEED_DONE  "LUMINE_EA_SEED_DONE_V3"
#define GV_LAST_TICK  "LUMINE_EA_LAST_TICK"
#define GV_SEED_FORCED "LUMINE_EA_SEED_FORCED_V4"

// ── EA v4: panel UI + status ─────────────────────────────────────────
string   g_panelName      = "LUMINE_EA_PANEL";
bool     g_panelVisible   = true;
int      g_ticksSent      = 0;
datetime g_lastStatusSent = 0;
double   g_sessionHigh    = 0;
double   g_sessionLow     = 0;
datetime g_sessionDate    = 0;
double   g_netPnl         = 0;
double   g_marginLevel    = 0;
int      g_eaBuild        = 0;

// ── Refresh bars M1 periodik (fix stale 5m/15m) ─────────────────────────
datetime  g_lastM1Refresh = 0;

// ── Function prototypes ────────────────────────────────────────────────────
// PITFALL: build MetaEditor ini TIDAK hoist function (commit 3834a9f) —
// setiap function WAJIB dideklarasikan sebelum dipakai.
string   DeinitReasonStr(const int reason);
int      CurrentBackoff();
void     MarkProxyOk();
void     MarkProxyFail(const string where, const int code);
int      HttpPostJson(const string path, const string json, const int timeoutMs);
void     QueueResult(const string json);
void     FlushOneResult(const datetime now);
void     SeedNextChunk();
void     SeedAdvanceTf();
void     PollCommands();
void     SendTick();
void     SendPositionsSnapshot();
void     SendDealsSnapshot();
string   NormalizeSymbol(const string raw);
void     SeedRecentM1();
void     ProcessCommand(const string json);
double   NormalizeVolume(const string symbol, double lots);
ENUM_ORDER_TYPE_FILLING GetFilling(const string symbol);
void     ExecuteOpen(const string id, const string symbol, const string side,
                     double lots, double sl, double tp);
void     ExecuteClose(const string id, ulong ticket);
void     ExecuteModify(const string id, ulong ticket, double sl, double tp);
string   BuildResultJson(const string id, const string status, long ticket,
                         const string error, double fillPrice, double fillVolume);
string   ExtractJsonString(const string json, const string key);
double   ExtractJsonDouble(const string json, const string key);
string   EscapeJson(const string s);
string   RetcodeStr(uint retcode);
void     CreatePanel();
void     UpdatePanel(const datetime now);
void     DestroyPanel();
void     PanelSetText(const string objName, const string txt, const int y);
void     PanelCreateButton(const string objName, const string label, const int x, const int y);
void     OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam);
void     SendStatus();
void     SendLog(const string line);
void     UpdateSessionHL();
void     ForceReseed();
double   NetOpenPnl();
long     AccountLeverage();

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_proxyURL    = InpProxyURL;
   // v4: seed WAJIB ON — tidak peduli input lama/GlobalVariable, selalu seed.
   g_seedEnabled = true;
   g_seedChunkSize = MathMax(100, MathMin(1000, InpSeedChunks));
   g_maxBackoff  = MathMax(5, InpMaxBackoff);
   g_panelVisible = InpShowPanel;
   g_eaBuild      = 400;   // EA v4.0 — build numeric sederhana

   Print("LumineEA v4 starting: proxy=", g_proxyURL,
         " seed=ON(forced) build=", __DATE__, " started=", TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS));

   // PITFALL v2: polling di OnTick bergantung feed tick MT5. Feed pause →
   // EA mati total. OnTimer = polling mandiri.
   // v4.1 (18 Aug): interval configurable. <1000ms pakai
   // EventSetMillisecondTimer (MQL5 minimum 1s untuk EventSetTimer).
   int pollMs = MathMax(250, MathMin(5000, InpPollMs));
   if(pollMs < 1000)
     {
      EventSetMillisecondTimer(pollMs);
      Print("LumineEA: timer = ", pollMs, "ms (millisecond timer)");
     }
   else
     {
      EventSetTimer(pollMs / 1000);
      Print("LumineEA: timer = ", pollMs / 1000, "s");
     }

   // Restore state (survive REASON_CHARTCHANGE/RECOMPILE/TEMPLATE)
   g_lastTickSent = (datetime)GlobalVariableGet(GV_LAST_TICK);

   // v4: InpForceSeed=true → hapus penanda seed-done dan seed ulang bersih.
   if(InpForceSeed)
     {
      GlobalVariableDel(GV_SEED_DONE);
      GlobalVariableSet(GV_SEED_FORCED, 1);
      g_seedPhase  = 1;
      g_seedOffset = 0;
      Print("LumineEA: FORCE SEED — seed ulang semua timeframe (bersih)");
     }
   else if(GlobalVariableCheck(GV_SEED_DONE) && GlobalVariableGet(GV_SEED_DONE) > 0)
     {
      g_seedPhase = 2;
      Print("LumineEA: seed sudah pernah selesai (GlobalVariable) — skip");
     }
   else if(g_seedEnabled)
     {
      g_seedPhase  = 1;
      g_seedOffset = 0;
      Print("LumineEA: seed multi-TF mulai (non-blocking, 1 chunk/detik)");
     }

   UpdateSessionHL();
   if(g_panelVisible)
      CreatePanel();

   Print("LumineEA v4 ready (HTTP polling, self-healing)");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//| reason 3 = REASON_CHARTCHANGE (ganti TF/symbol) → OnInit re-run,  |
//| state sudah dipersist via GlobalVariables → tidak ada yang hilang. |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   DestroyPanel();

   // Flush result queue best-effort sebelum mati (max 5 detik usaha)
   for(int i = 0; i < g_resultCount && i < 8; i++)
      FlushOneResult(0);

   GlobalVariableSet(GV_LAST_TICK, (double)g_lastTickSent);
   Print("LumineEA stopping: reason=", reason, " (", DeinitReasonStr(reason),
         ") pendingResults=", g_resultCount);
  }

string DeinitReasonStr(const int reason)
  {
   switch(reason)
     {
      case REASON_PROGRAM:     return "ExpertRemove called";
      case REASON_REMOVE:      return "EA removed from chart";
      case REASON_RECOMPILE:   return "recompiled";
      case REASON_CHARTCHANGE: return "chart TF/symbol changed";
      case REASON_CHARTCLOSE:  return "chart closed";
      case REASON_PARAMETERS:  return "input params changed";
      case REASON_ACCOUNT:     return "account changed";
      case REASON_TEMPLATE:    return "template applied";
      case REASON_INITFAILED:  return "OnInit failed";
      case REASON_CLOSE:       return "terminal closed";
      default:                 return "unknown";
     }
  }

//+------------------------------------------------------------------+
//| Expert timer — orkestrator utama (1s)                             |
//| Prioritas: result queue > poll command > tick > seed              |
//+------------------------------------------------------------------+
void OnTimer()
  {
   // v4.1 (18 Aug): guard ms-based — timer bisa <1 detik. Guard detik lama
   // (g_lastCmdPoll = now+1) menghalangi polling <1s.
   static ulong s_lastCycleMs = 0;
   ulong nowMs = GetTickCount();
   if(nowMs - s_lastCycleMs < (ulong)MathMax(250, MathMin(5000, InpPollMs)))
      return;  // belum waktunya siklus — OnTimer dipanggil lebih sering dari interval
   s_lastCycleMs = nowMs;

   datetime now = TimeLocal();

   // 1) Flush result queue (order result = uang, prioritas tertinggi)
   //    1 result per timer tick; retry sampai berhasil.
   if(g_resultCount > 0 && now >= g_lastCmdPoll)   // jangan delay poll
      FlushOneResult(now);

   // 2) Poll commands — ms-based murni (v4.1: polling <1 detik).
   //    g_lastCmdPoll TETAP now+1: dipakai seed guard baris ~320
   //    (`now < g_lastCmdPoll` = jalan di sisa detik antar poll).
   static ulong s_lastCmdMs = 0;
   if(nowMs - s_lastCmdMs >= (ulong)MathMax(250, MathMin(5000, InpPollMs)))
     {
      s_lastCmdMs = nowMs;
      g_lastCmdPoll = now + 1;
      PollCommands();
     }

   // 3) Send tick — ms-based murni (v4.1: tick <1 detik saat polling cepat).
   static ulong s_lastTickMs = 0;
   int backoff = CurrentBackoff();
   ulong tickIntervalMs = (ulong)MathMax(250, MathMin(5000, InpPollMs)) * (ulong)MathMax(1, backoff);
   if(nowMs - s_lastTickMs >= tickIntervalMs)
     {
      s_lastTickMs = nowMs;
      SendTick();
     }
   else if(g_seedPhase == 1)
      SeedNextChunk();   // proxy down → manfaatkan waktu untuk seed lokal

   // 3b) Snapshot positions (B1 sync: tiap InpPositionsInterval detik)
   if(now >= g_lastPositionsSent + InpPositionsInterval)
     {
      g_lastPositionsSent = now;
      SendPositionsSnapshot();
     }

   // 3c) Snapshot deals/history (B1 sync: tiap InpDealsInterval detik)
   if(now >= g_lastDealsSent + InpDealsInterval)
     {
      g_lastDealsSent = now;
      SendDealsSnapshot();
     }

   // 3d) Refresh bars M1 terbaru (fix stale 5m/15m) tiap 30 menit
   if(g_seedPhase == 2 && now >= g_lastM1Refresh + 1800)
     {
      g_lastM1Refresh = now;
      SeedRecentM1();
     }

   // 3e) Status push ke Redis (tiap InpStatusInterval detik) — EA monitor
   if(now >= g_lastStatusSent + InpStatusInterval)
     {
      g_lastStatusSent = now;
      SendStatus();
     }

   // 3f) Session H/L refresh tiap 30 detik
   if(now >= g_sessionDate + 30)
      UpdateSessionHL();

   // 4) Seed non-blocking (1 chunk per tick)
   if(g_seedPhase == 1 && now < g_lastCmdPoll)
      SeedNextChunk();

   // 5) Panel UI update (realtime)
   if(g_panelVisible)
      UpdatePanel(now);
  }

//+------------------------------------------------------------------+
//| Backoff: 1,2,4,8,...,max detik. Reset saat sukses.                |
//+------------------------------------------------------------------+
int CurrentBackoff()
  {
   if(g_failCount <= 0) return 1;
   int b = 1;
   for(int i = 0; i < g_failCount && i < 20; i++) b *= 2;
   return MathMin(g_maxBackoff, b);
  }

void MarkProxyOk()
  {
   if(g_proxyDown)
     {
      Print("LumineEA: proxy RECOVERED (failures=", g_failCount, ")");
      g_proxyDown = false;
     }
   g_failCount = 0;
  }

void MarkProxyFail(const string where, const int code)
  {
   g_failCount++;
   if(!g_proxyDown)
     {
      g_proxyDown = true;
      Print("LumineEA: proxy UNREACHABLE at ", where, " code=", code,
            " — backoff mode (max ", g_maxBackoff, "s), will retry");
     }
  }

//+------------------------------------------------------------------+
//| HTTP POST JSON (WebRequest wrapper, tahan banting)                |
//+------------------------------------------------------------------+
int HttpPostJson(const string path, const string json, const int timeoutMs)
  {
   char data[];
   StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);  // buang null terminator

   char result[];
   string headers = "Content-Type: application/json\r\n";
   string url = g_proxyURL + path;

   int res = WebRequest("POST", url, headers, timeoutMs, data, result, headers);
   if(res == 200)
      MarkProxyOk();
   else if(res == -1)
     {
      int err = GetLastError();
      if(err != 0)
         MarkProxyFail(path, err);
     }
   return res;
  }

//+------------------------------------------------------------------+
//| Result queue — order result tidak boleh hilang                    |
//+------------------------------------------------------------------+
void QueueResult(const string json)
  {
   if(g_resultCount >= RESULT_QUEUE_MAX)
     {
      // Queue penuh: buang tertua (log — jarang terjadi, 128 slot)
      Print("LumineEA: result queue FULL, dropping oldest");
      for(int i = 1; i < RESULT_QUEUE_MAX; i++)
         g_resultQueue[i - 1] = g_resultQueue[i];
      g_resultCount = RESULT_QUEUE_MAX - 1;
     }
   g_resultQueue[g_resultCount] = json;
   g_resultCount++;
  }

void FlushOneResult(const datetime now)
  {
   if(g_resultCount <= 0) return;

   string json = g_resultQueue[0];
   int res = HttpPostJson("/results", json, 3000);

   if(res == 200)
     {
      // shift queue
      for(int i = 1; i < g_resultCount; i++)
         g_resultQueue[i - 1] = g_resultQueue[i];
      g_resultCount--;
      return;
     }
   // gagal → tetap di queue, ditry tick berikutnya (MarkProxyFail sudah dipanggil)
  }

//+------------------------------------------------------------------+
//| Seed history bars — non-blocking, multi-TF, paginated             |
//| 1 chunk per OnTimer. Progress: symbol×TF sekuensial, offset dari  |
//| bar tertua ke terbaru (COPY DATA LAMA dulu).                      |
//+------------------------------------------------------------------+
void SeedNextChunk()
  {
   if(g_seedPhase != 1) return;
   if(g_seedSymIdx >= ArraySize(g_seedSymbols))
     {
      g_seedPhase = 2;
      GlobalVariableSet(GV_SEED_DONE, 1);
      Print("LumineEA: SeedHistory SELESAI total bars=", g_seedSent);
      return;
     }

   string sym = g_seedSymbols[g_seedSymIdx];
   ENUM_TIMEFRAMES tf = g_seedTfs[g_seedTfIdx];
   string tfName = g_seedTfNames[g_seedTfIdx];

   if(g_seedOffset == 0)
     {
      g_seedTotal = iBars(sym, tf);
      if(g_seedTotal <= 0)
        {
         Print("LumineEA: seed ", sym, " ", tfName, " gagal iBars err=", GetLastError());
         SeedAdvanceTf();
         return;
        }
      Print("LumineEA: seed ", sym, " ", tfName, " total=", g_seedTotal, " bars");
     }

   // CopyRates: offset dari 0 = bar TERBARU. Kita jalan dari total→0
   // agar urutan kirim oldest-first (chunk terakhir = bar terbaru).
   int remaining = g_seedTotal - g_seedOffset;
   if(remaining <= 0)
     {
      SeedAdvanceTf();
      return;
     }

   int count = MathMin(g_seedChunkSize, remaining);
   // start = offset dari bar terbaru; chunk kita mulai dari sisi tertua
   int start = remaining - count;   // 0-based posisi bar tertua chunk ini

   MqlRates rates[];
   int got = CopyRates(sym, tf, start, count, rates);
   if(got <= 0)
     {
      int err = GetLastError();
      if(err == 4407 || err == 4401)   // HISTORY_NOT_FOUND / tidak ada data
        {
         Print("LumineEA: seed ", sym, " ", tfName, " tidak ada history (err=", err, ") — skip TF");
        }
      else
        {
         Print("LumineEA: seed CopyRates ", sym, " ", tfName, " err=", err, " — retry tick depan");
         // Jangan advance — retry chunk sama tick berikutnya (non-blocking)
         // tapi kalau err 4014 (function not allowed) skip saja
         if(err == 4014) SeedAdvanceTf();
         return;
        }
      SeedAdvanceTf();
      return;
     }

   ArraySetAsSeries(rates, false);
   string json = "{\"symbol\":\"" + sym + "\",\"timeframe\":\"" + tfName + "\",\"bars\":[";
   for(int i = 0; i < got; i++)
     {
      MqlRates r = rates[i];
      if(i > 0) json += ",";
      json += StringFormat("{\"ts\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f}",
                           (long)r.time, r.open, r.high, r.low, r.close, (double)r.tick_volume);
     }
   json += "]}";

   int res = HttpPostJson("/seed/bars", json, 5000);
   if(res == 200)
     {
      g_seedOffset += got;
      g_seedSent += got;
      if(g_seedOffset >= g_seedTotal)
         SeedAdvanceTf();
     }
   // res != 200 → chunk sama di-retry tick berikutnya (state tidak maju)
  }

void SeedAdvanceTf()
  {
   g_seedTfIdx++;
   g_seedOffset = 0;
   g_seedTotal = 0;
   if(g_seedTfIdx >= ArraySize(g_seedTfs))
     {
      g_seedTfIdx = 0;
      g_seedSymIdx++;
     }
  }

//+------------------------------------------------------------------+
//| Expert tick — feed MT5 (polling utama ada di OnTimer)             |
//+------------------------------------------------------------------+
void OnTick()
  {
  }

//+------------------------------------------------------------------+
//| Poll Redis for commands via HTTP                                  |
//+------------------------------------------------------------------+
void PollCommands()
  {
   string url = g_proxyURL + "/commands?timeout=1";
   char   data[];
   char   result[];
   string headers = "Content-Type: application/json\r\n";

   int res = WebRequest("GET", url, headers, 2000, data, result, headers);

   if(res == 200)
     {
      MarkProxyOk();
      string json = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
      if(StringLen(json) > 2)
         ProcessCommand(json);
     }
   else if(res == 204 || res == 408)
     {
      MarkProxyOk();   // no command / timeout — normal
     }
   else if(res == -1)
     {
      int err = GetLastError();
      if(err != 0)
         MarkProxyFail("PollCommands", err);
     }
   else
     {
      MarkProxyFail("PollCommands-http", res);
     }
  }

//+------------------------------------------------------------------+
//| Send tick + account snapshot ke Redis via HTTP                    |
//| SKIP saat bid/ask = 0 (market closed / no quote) — tidak kirim    |
//| data sampah. Payload diperkaya equity/balance untuk P&L real.     |
//+------------------------------------------------------------------+
void SendTick()
  {
   string symbol = NormalizeSymbol(Symbol());
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

   if(bid <= 0 && ask <= 0)
      return;   // market closed — tidak kirim tick kosong

   datetime timestamp = TimeCurrent();
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double margin  = AccountInfoDouble(ACCOUNT_MARGIN);

   string json = StringFormat(
      "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"timestamp\":%I64d,"
      "\"equity\":%.2f,\"balance\":%.2f,\"margin\":%.2f}",
      symbol, bid, ask, (long)timestamp, equity, balance, margin);

   int res = HttpPostJson("/ticks", json, 2000);
   if(res == 200)
      g_lastTickSent = TimeLocal();
   else if(res != -1 && !g_proxyDown)
      Print("LumineEA: SendTick failed http=", res, " (queued-retry via backoff)");
   // -1 sudah ditangani MarkProxyFail di HttpPostJson path (200-only marks ok;
   // non-200 → biarkan backoff, log state-change saja)
  }

//+------------------------------------------------------------------+
//| Refresh bars M1 terbaru (120 bar) tiap 30 menit — bars_1m/5m/15m |
//| tetap FRESH walau seed awal sudah selesai (fix stale 5m/15m).     |
//+------------------------------------------------------------------+
void SeedRecentM1()
  {
   string sym = NormalizeSymbol(g_seedSymbols[0]);
   MqlRates rates[];
   int got = CopyRates(sym, PERIOD_M1, 0, 120, rates);
   if(got <= 0)
     {
      Print("LumineEA: SeedRecentM1 CopyRates err=", GetLastError());
      return;
     }
   // JSON: [{ts, open, high, low, close, volume}...] oldest-first
   string bars = "[";
   for(int i = got - 1; i >= 0; i--)
     {
      if(i != got - 1) bars += ",";
      bars += StringFormat("{\"ts\":%d,\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s,\"volume\":%s}",
         (long)rates[i].time,
         DoubleToString(rates[i].open, 2), DoubleToString(rates[i].high, 2),
         DoubleToString(rates[i].low, 2), DoubleToString(rates[i].close, 2),
         DoubleToString(rates[i].tick_volume, 0));
     }
   bars += "]";
   string json = "{\"symbol\":\"" + sym + "\",\"timeframe\":\"1m\",\"bars\":" + bars + "}";
   int res = HttpPostJson("/seed/bars", json, 3000);
   if(res != 200 && res != -1 && !g_proxyDown)
      Print("LumineEA: SeedRecentM1 failed http=", res);
  }

//+------------------------------------------------------------------+
//| Normalize broker symbol → base (B9 multicurrency prefix)          |
//| XAUUSDc (cent) → XAUUSD; XAUUSD.stp / XAUUSD.m / XAUUSDx → XAUUSD |
//+------------------------------------------------------------------+
string NormalizeSymbol(const string raw)
  {
   string s = raw;
   // hapus bagian setelah '.' (XAUUSD.stp → XAUUSD)
   int dot = StringFind(s, ".");
   if(dot > 0) s = StringSubstr(s, 0, dot);
   // hapus suffix lowercase 1-char di akhir (XAUUSDc → XAUUSD)
   int len = StringLen(s);
   if(len > 4)
     {
      string last = StringSubstr(s, len - 1);
      if(last == "c" || last == "m" || last == "x" || last == "i" || last == "z")
         s = StringSubstr(s, 0, len - 1);
     }
   StringToUpper(s);
   return s;
  }

//+------------------------------------------------------------------+
//| Send snapshot open positions (B1 sync → /positions → mt5:positions |
//| → PositionSyncWorker upsert DB). Tiap InpPositionsInterval detik.  |
//+------------------------------------------------------------------+
void SendPositionsSnapshot()
  {
   string json = "{\"snapshot_ts\":" + (string)(long)TimeCurrent() + ",\"positions\":[";

   int total = PositionsTotal();
   int count = 0;
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;

      string symbol = NormalizeSymbol(PositionGetString(POSITION_SYMBOL));
      long   type   = PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl     = PositionGetDouble(POSITION_SL);
      double tp     = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);
      datetime time  = (datetime)PositionGetInteger(POSITION_TIME);

      if(count > 0) json += ",";
      json += StringFormat(
         "{\"ticket\":%I64d,\"symbol\":\"%s\",\"type\":%I64d,\"volume\":%.4f,"
         "\"price_open\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"profit\":%.2f,\"time\":%I64d}",
         ticket, symbol, type, volume, open, sl, tp, profit, (long)time);
      count++;
     }
   json += "]}";

   if(count == 0)
     {
      // Tidak ada posisi open — kirim snapshot kosong agar backend bisa
      // menutup posisi yang sudah tidak ada di MT5.
      json = "{\"snapshot_ts\":" + (string)(long)TimeCurrent() + ",\"positions\":[]}";
     }

   int res = HttpPostJson("/positions", json, 3000);
   if(res != 200 && res != -1 && !g_proxyDown)
      Print("LumineEA: SendPositionsSnapshot failed http=", res);
   // skip saat market closed? TIDAK — posisi tetap harus sinkron walau libur.
  }

//+------------------------------------------------------------------+
//| Send history deals terbaru (B1 sync → /deals → mt5:deals →        |
//| backend trade journal/fills). Tiap InpDealsInterval detik.        |
//| HistorySelect(0, now) ambil semua deal dari awal hari.            |
//+------------------------------------------------------------------+
void SendDealsSnapshot()
  {
   datetime from = TimeCurrent() - 30 * 86400;   // 30 hari terakhir
   datetime to   = TimeCurrent();
   if(!HistorySelect(from, to))
     {
      Print("LumineEA: SendDealsSnapshot HistorySelect gagal err=", GetLastError());
      return;
     }

   int total = HistoryDealsTotal();
   string json = "{\"symbol\":\"" + NormalizeSymbol(Symbol()) + "\",\"deals\":[";

   int count = 0;
   // Kirim 50 deal terbaru saja per snapshot (batch; backend dedupe by ticket)
   int start = MathMax(0, total - 50);
   for(int i = start; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;

      string symbol   = HistoryDealGetString(ticket, DEAL_SYMBOL);
      long   type     = HistoryDealGetInteger(ticket, DEAL_TYPE);
      double volume   = HistoryDealGetDouble(ticket, DEAL_VOLUME);
      double price    = HistoryDealGetDouble(ticket, DEAL_PRICE);
      double profit   = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      long   order    = HistoryDealGetInteger(ticket, DEAL_ORDER);
      datetime time   = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      long   entry    = HistoryDealGetInteger(ticket, DEAL_ENTRY);

      if(count > 0) json += ",";
      json += StringFormat(
         "{\"ticket\":%I64d,\"order\":%I64d,\"symbol\":\"%s\",\"type\":%I64d,\"entry\":%I64d,"
         "\"volume\":%.4f,\"price\":%.5f,\"profit\":%.2f,\"commission\":%.2f,\"time\":%I64d}",
         ticket, order, symbol, type, entry, volume, price, profit, commission, (long)time);
      count++;
     }
   json += "]}";

   if(count == 0)
     {
      Print("LumineEA: SendDealsSnapshot no deals (total=", total, ")");
      return;   // tidak ada deal — tidak kirim payload kosong
     }

   int res = HttpPostJson("/deals", json, 3000);
   if(res == 200)
      Print("LumineEA: deals sent count=", count, " total=", total);
   else if(res != -1 && !g_proxyDown)
      Print("LumineEA: SendDealsSnapshot failed http=", res);
  }

//+------------------------------------------------------------------+
//| Process command JSON dari Redis                                    |
//+------------------------------------------------------------------+
void ProcessCommand(const string json)
  {
   string id = ExtractJsonString(json, "command_id");
   if(StringLen(id) == 0) id = ExtractJsonString(json, "id");
   string action = ExtractJsonString(json, "action");

   g_orderId = ExtractJsonString(json, "order_id");
   if(StringLen(g_orderId) == 0) g_orderId = id;

   if(StringLen(id) == 0 || StringLen(action) == 0)
      return;   // empty command (queue timeout) — silent

   Print("Command received: id=", id, " action=", action);

   if(action == "OPEN")
     {
      string symbol = ExtractJsonString(json, "symbol");
      if(StringLen(symbol) == 0) symbol = Symbol();
      string side = ExtractJsonString(json, "order_type");
      if(StringLen(side) == 0) side = ExtractJsonString(json, "side");
      StringToUpper(side);
      double lots = ExtractJsonDouble(json, "volume");
      if(lots == 0) lots = ExtractJsonDouble(json, "lots");
      double sl = ExtractJsonDouble(json, "sl");
      double tp = ExtractJsonDouble(json, "tp");

      ExecuteOpen(id, symbol, side, lots, sl, tp);
     }
   else if(action == "CLOSE")
     {
      ulong ticket = (ulong)StringToInteger(ExtractJsonString(json, "ticket"));
      ExecuteClose(id, ticket);
     }
   else if(action == "MODIFY")
     {
      ulong ticket = (ulong)StringToInteger(ExtractJsonString(json, "ticket"));
      double sl = ExtractJsonDouble(json, "sl");
      double tp = ExtractJsonDouble(json, "tp");
      ExecuteModify(id, ticket, sl, tp);
     }
   else if(action == "SEED_NOW" || action == "RESEED")
     {
      // Seed ulang semua timeframe dari awal (hapus GV seed-done dulu)
      GlobalVariableDel(GV_SEED_DONE);
      g_seedPhase  = 1;
      g_seedOffset = 0;
      g_seedSymIdx = 0;
      g_seedTfIdx  = 0;
      Print("LumineEA: command ", action, " → seed ulang dimulai");
      SendLog("SEED_NOW executed");
      QueueResult(BuildResultJson(id, "SEEDING", 0, "seed restarted", 0, 0));
     }
   else if(action == "STATUS")
     {
      SendStatus();
      SendLog("STATUS requested");
      QueueResult(BuildResultJson(id, "STATUS_SENT", 0, "status pushed to redis", 0, 0));
     }
   else if(action == "PANEL_TOGGLE")
     {
      if(g_panelVisible)
        {
         g_panelVisible = false;
         DestroyPanel();
        }
      else
        {
         g_panelVisible = true;
         CreatePanel();
        }
      SendLog("PANEL_TOGGLE -> " + (g_panelVisible ? "show" : "hide"));
      QueueResult(BuildResultJson(id, "OK", 0, "panel " + (g_panelVisible ? "shown" : "hidden"), 0, 0));
     }
   else if(action == "PING")
     {
      SendLog("PING ok");
      QueueResult(BuildResultJson(id, "PONG", 0, "", 0, 0));
     }
   else
     {
      QueueResult(BuildResultJson(id, "ERROR", 0, "Unknown action: " + action, 0, 0));
     }
  }

//+------------------------------------------------------------------+
//| Volume normalization — step/min/max symbol                        |
//+------------------------------------------------------------------+
double NormalizeVolume(const string symbol, double lots)
  {
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   if(vmin <= 0) vmin = 0.01;
   if(vmax <= 0) vmax = 100.0;
   lots = MathMax(vmin, MathMin(vmax, lots));
   lots = MathRound(lots / step) * step;
   // buang artefak floating point
   return NormalizeDouble(lots, 8);
  }

//+------------------------------------------------------------------+
//| Filling mode per symbol — FOK→IOC→RETURN fallback                 |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetFilling(const string symbol)
  {
   long filling = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((filling & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }

//+------------------------------------------------------------------+
//| Execute OPEN order (dengan retry filling + volume normalize)      |
//+------------------------------------------------------------------+
void ExecuteOpen(const string id, const string symbol, const string side,
                 double lots, double sl, double tp)
  {
   ENUM_ORDER_TYPE orderType = (side == "BUY" || side == "LONG") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   lots = NormalizeVolume(symbol, lots);

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};

   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = symbol;
   req.volume       = lots;
   req.type         = orderType;
   req.price        = (orderType == ORDER_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                                                    : SymbolInfoDouble(symbol, SYMBOL_BID);
   req.sl           = sl;
   req.tp           = tp;
   req.deviation    = 20;
   req.magic        = 20260814;
   req.comment      = "Lumine:" + id;
   req.type_filling = GetFilling(symbol);

   if(!OrderSend(req, res))
     {
      // Fallback filling: 10030 INVALID_FILL → coba mode lain
      if(res.retcode == 10030)
        {
         req.type_filling = (req.type_filling == ORDER_FILLING_FOK) ? ORDER_FILLING_IOC
                            : (req.type_filling == ORDER_FILLING_IOC) ? ORDER_FILLING_RETURN
                            : ORDER_FILLING_FOK;
         if(!OrderSend(req, res))
           {
            QueueResult(BuildResultJson(id, "ERROR", 0,
                         "OrderSend failed retcode=" + IntegerToString(res.retcode), 0, lots));
            return;
           }
        }
      else
        {
         QueueResult(BuildResultJson(id, "ERROR", 0,
                      "OrderSend failed retcode=" + IntegerToString(res.retcode), 0, lots));
         return;
        }
     }

   if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL)
      QueueResult(BuildResultJson(id, "FILLED", (long)res.order, "", res.price, lots));
   else if(res.retcode == TRADE_RETCODE_PLACED)
      QueueResult(BuildResultJson(id, "PLACED", (long)res.order, "", res.price, lots));
   else
      QueueResult(BuildResultJson(id, "REJECTED", 0, RetcodeStr(res.retcode), 0, lots));
  }

//+------------------------------------------------------------------+
//| Execute CLOSE order                                               |
//+------------------------------------------------------------------+
void ExecuteClose(const string id, ulong ticket)
  {
   if(!PositionSelectByTicket(ticket))
     {
      QueueResult(BuildResultJson(id, "ERROR", 0, "Position not found: " + IntegerToString(ticket), 0, 0));
      return;
     }

   string symbol = PositionGetString(POSITION_SYMBOL);
   double volume = PositionGetDouble(POSITION_VOLUME);

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};

   req.action       = TRADE_ACTION_DEAL;
   req.position     = ticket;
   req.symbol       = symbol;
   req.volume       = volume;
   req.type         = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.price        = (req.type == ORDER_TYPE_SELL) ? SymbolInfoDouble(symbol, SYMBOL_BID)
                                                    : SymbolInfoDouble(symbol, SYMBOL_ASK);
   req.deviation    = 20;
   req.magic        = 20260814;
   req.comment      = "Lumine:CLOSE:" + id;
   req.type_filling = GetFilling(symbol);

   if(!OrderSend(req, res))
     {
      if(res.retcode == 10030)
        {
         req.type_filling = (req.type_filling == ORDER_FILLING_FOK) ? ORDER_FILLING_IOC
                            : (req.type_filling == ORDER_FILLING_IOC) ? ORDER_FILLING_RETURN
                            : ORDER_FILLING_FOK;
         if(!OrderSend(req, res))
           {
            QueueResult(BuildResultJson(id, "ERROR", 0,
                         "OrderSend CLOSE failed retcode=" + IntegerToString(res.retcode), 0, volume));
            return;
           }
        }
      else
        {
         QueueResult(BuildResultJson(id, "ERROR", 0,
                      "OrderSend CLOSE failed retcode=" + IntegerToString(res.retcode), 0, volume));
         return;
        }
     }

   if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL)
      QueueResult(BuildResultJson(id, "CLOSED", (long)res.order, "", res.price, volume));
   else
      QueueResult(BuildResultJson(id, "REJECTED", 0, RetcodeStr(res.retcode), 0, volume));
  }

//+------------------------------------------------------------------+
//| Execute MODIFY order (SL/TP)                                      |
//+------------------------------------------------------------------+
void ExecuteModify(const string id, ulong ticket, double sl, double tp)
  {
   if(!PositionSelectByTicket(ticket))
     {
      QueueResult(BuildResultJson(id, "ERROR", 0, "Position not found: " + IntegerToString(ticket), 0, 0));
      return;
     }

   MqlTradeRequest req = {};
   MqlTradeResult  res = {};

   req.action   = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol   = PositionGetString(POSITION_SYMBOL);
   req.sl       = sl;
   req.tp       = tp;

   if(OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE)
      QueueResult(BuildResultJson(id, "MODIFIED", (long)ticket, "", 0, 0));
   else
      QueueResult(BuildResultJson(id, "REJECTED", 0, RetcodeStr(res.retcode), 0, 0));
  }

//+------------------------------------------------------------------+
//| Build result JSON (central — konsisten dengan bridge schema)      |
//+------------------------------------------------------------------+
string   BuildResultJson(const string id, const string status, long ticket,
                       const string error, double fillPrice, double fillVolume)
  {
   return StringFormat("{\"id\":\"%s\",\"order_id\":\"%s\",\"status\":\"%s\","
                       "\"ticket\":%I64d,\"error\":\"%s\",\"fill_price\":%.5f,\"fill_volume\":%.5f}",
                       id, g_orderId, status, ticket, EscapeJson(error), fillPrice, fillVolume);
  }

//+------------------------------------------------------------------+
//| Helper: Extract string dari JSON                                  |
//+------------------------------------------------------------------+
string ExtractJsonString(const string json, const string key)
  {
   string pattern = "\"" + key + "\":\"";
   int start = StringFind(json, pattern);
   if(start == -1) return "";
   start += StringLen(pattern);
   int end = StringFind(json, "\"", start);
   if(end == -1) return "";
   return StringSubstr(json, start, end - start);
  }

//+------------------------------------------------------------------+
//| Helper: Extract double dari JSON                                  |
//+------------------------------------------------------------------+
double ExtractJsonDouble(const string json, const string key)
  {
   string pattern = "\"" + key + "\":";
   int start = StringFind(json, pattern);
   if(start == -1) return 0;
   start += StringLen(pattern);
   int end = StringFind(json, ",", start);
   if(end == -1) end = StringFind(json, "}", start);
   if(end == -1) return 0;
   string value = StringSubstr(json, start, end - start);
   StringTrimLeft(value);
   StringTrimRight(value);
   return StringToDouble(value);
  }

//+------------------------------------------------------------------+
//| Helper: Escape JSON string                                        |
//+------------------------------------------------------------------+
string EscapeJson(const string s)
  {
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "\\\"");
   StringReplace(r, "\n", "\\n");
   StringReplace(r, "\r", "\\r");
   return r;
  }

//+------------------------------------------------------------------+
//| Helper: Retcode → string                                          |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| EA v4: Panel UI di chart                                          |
//| Menampilkan: version, build, seed phase, ticks, spread, bid/ask, |
//| session H/L, equity, margin, leverage, net P&L.                   |
//| Tombol: SEED (seed ulang), STATUS (push status), HIDE (sembunyi)  |
//+------------------------------------------------------------------+
void CreatePanel()
  {
   string bg = g_panelName + "_bg";
   ObjectCreate(0, bg, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, bg, OBJPROP_XDISTANCE, 10);
   ObjectSetInteger(0, bg, OBJPROP_YDISTANCE, 25);
   ObjectSetInteger(0, bg, OBJPROP_XSIZE, 260);
   ObjectSetInteger(0, bg, OBJPROP_YSIZE, 240);
   ObjectSetInteger(0, bg, OBJPROP_BGCOLOR, C'18,22,34');
   ObjectSetInteger(0, bg, OBJPROP_BORDER_COLOR, clrGray);
   ObjectSetInteger(0, bg, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, bg, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, bg, OBJPROP_BACK, false);
   ObjectSetInteger(0, bg, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, bg, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, bg, OBJPROP_ZORDER, 0);

   PanelSetText(g_panelName + "_title", "LUMINE EA v4", 30);
   PanelSetText(g_panelName + "_ver",   "build: " + __DATE__, 48);
   PanelSetText(g_panelName + "_seed",  "seed: ...", 66);
   PanelSetText(g_panelName + "_tick",  "ticks: 0", 84);
   PanelSetText(g_panelName + "_px",    "bid/ask/spread: --", 102);
   PanelSetText(g_panelName + "_sess",  "session H/L: --", 120);
   PanelSetText(g_panelName + "_eq",    "equity/margin: --", 138);
   PanelSetText(g_panelName + "_lev",   "leverage: --", 156);
   PanelSetText(g_panelName + "_pnl",   "net P&L: --", 174);

   PanelCreateButton(g_panelName + "_btn_seed",   "SEED",   10, 215);
   PanelCreateButton(g_panelName + "_btn_status", "STATUS", 70, 215);
   PanelCreateButton(g_panelName + "_btn_hide",   "HIDE",  130, 215);

   UpdatePanel(TimeLocal());
  }

void PanelSetText(const string objName, const string txt, const int y)
  {
   if(ObjectFind(0, objName) < 0)
     {
      ObjectCreate(0, objName, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, 16);
      ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(0, objName, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, objName, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, objName, OBJPROP_ZORDER, 1);
     }
   ObjectSetString(0, objName, OBJPROP_TEXT, txt);
  }

void PanelCreateButton(const string objName, const string label, const int x, const int y)
  {
   if(ObjectFind(0, objName) < 0)
     {
      ObjectCreate(0, objName, OBJ_BUTTON, 0, 0, 0);
      ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, objName, OBJPROP_XSIZE, 56);
      ObjectSetInteger(0, objName, OBJPROP_YSIZE, 22);
      ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_COLOR, clrWhite);
      ObjectSetInteger(0, objName, OBJPROP_BGCOLOR, C'40,60,90');
      ObjectSetInteger(0, objName, OBJPROP_BORDER_COLOR, C'80,100,130');
      ObjectSetInteger(0, objName, OBJPROP_FONTSIZE, 8);
      ObjectSetString(0, objName, OBJPROP_TEXT, label);
      ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, objName, OBJPROP_ZORDER, 1);
     }
  }

void UpdatePanel(const datetime now)
  {
   string sym = NormalizeSymbol(Symbol());
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double spread = (ask > bid && bid > 0) ? (ask - bid) / SymbolInfoDouble(sym, SYMBOL_POINT) : 0;
   string seedPhaseStr = g_seedPhase == 1 ? "RUNNING" : (g_seedPhase == 2 ? "DONE" : "IDLE");

   PanelSetText(g_panelName + "_title", "LUMINE EA v4", 30);
   PanelSetText(g_panelName + "_ver",   "build: " + __DATE__ + "  sym: " + sym, 48);
   PanelSetText(g_panelName + "_seed",  "seed: " + seedPhaseStr, 66);
   PanelSetText(g_panelName + "_tick",  "ticks sent: " + IntegerToString(g_ticksSent), 84);
   PanelSetText(g_panelName + "_px",    "bid: " + DoubleToString(bid, 2) + "  ask: " + DoubleToString(ask, 2)
                                        + "  spr: " + DoubleToString(spread, 1), 102);
   PanelSetText(g_panelName + "_sess",  "sess H/L: " + DoubleToString(g_sessionHigh, 2) + " / "
                                        + DoubleToString(g_sessionLow, 2), 120);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   PanelSetText(g_panelName + "_eq",    "eq: " + DoubleToString(equity, 2) + "  mg: " + DoubleToString(margin, 2), 138);
   PanelSetText(g_panelName + "_lev",   "lev: 1:" + IntegerToString((int)AccountLeverage()), 156);
   PanelSetText(g_panelName + "_pnl",   "net P&L: " + DoubleToString(g_netPnl, 2), 174);
   ChartRedraw(0);
  }

void DestroyPanel()
  {
   string objs[] = {"_bg", "_title", "_ver", "_seed", "_tick", "_px", "_sess",
                    "_eq", "_lev", "_pnl", "_btn_seed", "_btn_status", "_btn_hide"};
   for(int i = 0; i < ArraySize(objs); i++)
      ObjectDelete(0, g_panelName + objs[i]);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Chart events — klik tombol panel                                  |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;
   if(sparam == g_panelName + "_btn_seed")
     {
      GlobalVariableDel(GV_SEED_DONE);
      g_seedPhase  = 1;
      g_seedOffset = 0;
      g_seedSymIdx = 0;
      g_seedTfIdx  = 0;
      Print("LumineEA: [SEED] diklik — seed ulang");
      SendLog("SEED clicked on panel");
     }
   else if(sparam == g_panelName + "_btn_status")
     {
      SendStatus();
      SendLog("STATUS clicked on panel");
     }
   else if(sparam == g_panelName + "_btn_hide")
     {
      g_panelVisible = false;
      DestroyPanel();
      SendLog("Panel hidden");
     }
   ObjectSetInteger(0, sparam, OBJPROP_STATE, false);   // reset tombol
  }

//+------------------------------------------------------------------+
//| Push status lengkap ke Redis via HTTP (EA monitor)                |
//+------------------------------------------------------------------+
void SendStatus()
  {
   string sym = NormalizeSymbol(Symbol());
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double spread = (ask > bid && bid > 0) ? (ask - bid) / SymbolInfoDouble(sym, SYMBOL_POINT) : 0;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double margin  = AccountInfoDouble(ACCOUNT_MARGIN);
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   g_netPnl      = NetOpenPnl();
   g_marginLevel = (margin > 0 ? (equity / margin) * 100.0 : 0.0);

   string json = StringFormat(
      "{\"ea_version\":\"4.0\",\"ea_build\":%d,\"seed_phase\":%d,"
      "\"seed_done\":%d,\"ticks_sent\":%d,\"last_tick_ts\":%I64d,"
      "\"proxy_url\":\"%s\",\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,"
      "\"spread\":%.1f,\"session_high\":%.2f,\"session_low\":%.2f,"
      "\"equity\":%.2f,\"balance\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,"
      "\"margin_level\":%.2f,\"leverage\":%d,\"net_pnl\":%.2f}",
      g_eaBuild, g_seedPhase, (g_seedPhase == 2 ? 1 : 0), g_ticksSent,
      (long)g_lastTickSent, g_proxyURL, sym, bid, ask, spread,
      g_sessionHigh, g_sessionLow, equity, balance, margin, freeMargin,
      g_marginLevel, (int)AccountLeverage(), g_netPnl);

   int res = HttpPostJson("/status", json, 3000);
   if(res != 200 && res != -1 && !g_proxyDown)
      Print("LumineEA: SendStatus failed http=", res);
  }

//+------------------------------------------------------------------+
//| Push log line ke Redis (mt5:logs, superadmin EA logs panel)       |
//+------------------------------------------------------------------+
void SendLog(const string line)
  {
   string json = StringFormat("{\"ts\":%I64d,\"line\":\"%s\"}",
      (long)TimeCurrent(), EscapeJson(line));
   int res = HttpPostJson("/logs", json, 2000);
   if(res != 200 && res != -1 && !g_proxyDown)
      Print("LumineEA: SendLog failed http=", res);
  }

//+------------------------------------------------------------------+
//| Session High/Low — dari bar D1 hari ini (session current)         |
//+------------------------------------------------------------------+
void UpdateSessionHL()
  {
   datetime dayStart = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   g_sessionDate = dayStart;
   g_sessionHigh = iHigh(Symbol(), PERIOD_D1, 0);
   g_sessionLow  = iLow(Symbol(), PERIOD_D1, 0);
  }

//+------------------------------------------------------------------+
//| Net open P&L — sum semua posisi                                  |
//+------------------------------------------------------------------+
double NetOpenPnl()
  {
   double total = 0;
   int n = PositionsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      total += PositionGetDouble(POSITION_PROFIT);
     }
   return total;
  }

//+------------------------------------------------------------------+
//| Account leverage                                                  |
//+------------------------------------------------------------------+
long AccountLeverage()
  {
   return AccountInfoInteger(ACCOUNT_LEVERAGE);
  }

//+------------------------------------------------------------------+
//| Force reseed — command RESEED handler                             |
//+------------------------------------------------------------------+
void ForceReseed()
  {
   GlobalVariableDel(GV_SEED_DONE);
   g_seedPhase  = 1;
   g_seedOffset = 0;
   g_seedSymIdx = 0;
   g_seedTfIdx  = 0;
   Print("LumineEA: FORCE RESEED dimulai");
   SendLog("FORCE RESEED executed");
  }

string RetcodeStr(uint retcode)
  {
   switch(retcode)
     {
      case 10004: return "REQUOTE";
      case 10006: return "REJECT";
      case 10007: return "CANCEL";
      case 10008: return "PLACED";
      case 10009: return "DONE";
      case 10010: return "DONE_PARTIAL";
      case 10011: return "ERROR";
      case 10012: return "TIMEOUT";
      case 10013: return "INVALID";
      case 10014: return "INVALID_VOLUME";
      case 10015: return "INVALID_PRICE";
      case 10016: return "INVALID_STOPS";
      case 10017: return "TRADE_DISABLED";
      case 10018: return "MARKET_CLOSED";
      case 10019: return "NO_MONEY";
      case 10020: return "PRICE_CHANGED";
      case 10021: return "PRICE_OFF";
      case 10022: return "INVALID_EXPIRATION";
      case 10023: return "ORDER_CHANGED";
      case 10024: return "TOO_MANY_REQUESTS";
      case 10025: return "NO_CHANGES";
      case 10026: return "SERVER_DISABLES_AT";
      case 10027: return "CLIENT_DISABLES_AT";
      case 10028: return "LOCKED";
      case 10029: return "FROZEN";
      case 10030: return "INVALID_FILL";
      case 10031: return "CONNECTION";
      case 10032: return "ONLY_REAL";
      case 10033: return "LIMIT_ORDERS";
      case 10034: return "LIMIT_VOLUME";
      case 10035: return "INVALID_ORDER";
      case 10036: return "POSITION_CLOSED";
      case 10038: return "INVALID_CLOSE_VOLUME";
      case 10039: return "CLOSE_ORDER_EXIST";
      case 10040: return "LIMIT_POSITIONS";
      case 10041: return "REJECT_CANCEL";
      case 10042: return "LONG_ONLY";
      case 10043: return "SHORT_ONLY";
      case 10044: return "CLOSE_ONLY";
      case 10045: return "LIMIT_ORDERS_REAL";
      case 10046: return "LIMIT_POSITIONS_REAL";
      default:    return "RETCODE_" + IntegerToString(retcode);
     }
  }
//+------------------------------------------------------------------+
