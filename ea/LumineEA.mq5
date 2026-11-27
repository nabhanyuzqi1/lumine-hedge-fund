//+------------------------------------------------------------------+
//| LumineEA-Fund2.mq5 — bridge agent untuk Lumine Fund v2           |
//| EA v0 (P0 Fondasi & Pengukuran):                                 |
//|   - Heartbeat tiap 2 detik   -> POST /bridge/heartbeat           |
//|   - Tick batch tiap 250 ms   -> POST /bridge/tick                |
//|     (batch {ts(ms), bid, ask, spread}, spread = ask - bid)       |
//|   - Auth: HMAC-SHA256 per request (PRD v2.1 §7):               |
//|       X-Fund2-Timestamp : unix epoch detik (toleransi ±5 dtk)    |
//|       X-Fund2-Nonce     : hex acak, dipakai sekali               |
//|       X-Fund2-Signature : hex HMAC-SHA256(secret, string_to_sign)|
//|       string_to_sign = ts \n nonce \n METHOD \n path \n          |
//|                        sha256_hex(body)                          |
//|   - Secret TIDAK ada di repo: dibaca dari file di sandbox        |
//|     MQL5/Files (input InpSecretFile, default fund2_hmac.secret). |
//|     Secret gagal dimuat = EA fail-closed (tidak kirim apa pun).  |
//|   - Endpoint dummy (kartu P0): scripts/dummy_bridge.py,          |
//|     default http://127.0.0.1:3110/bridge (lokal, tanpa TLS).     |
//|                                                                   |
//| Contract dummy (v0):                                             |
//|   GET  /bridge/poll?timeout_s=0 → command | null                 |
//|   POST /bridge/result    → {command_id, status, ticket, ...}     |
//|   POST /bridge/heartbeat → {ts, symbol, bid, ask, spread, ea}    |
//|   POST /bridge/tick      → {symbol, ticks:[{ts,bid,ask,spread}], |
//|                             candles?}                            |
//|   POST /positions → snapshot posisi + deal 24 jam (PRD 5.8)      |
//|                                                                   |
//| Keputusan transport (FUND2-P1): MQL5 tidak punya klien WebSocket  |
//| native dan kontrak backend P1 long-poll, maka dipakai fast-poll  |
//| 100ms via EventSetMillisecondTimer di jalur lokal 127.0.0.1 —    |
//| latensi pickup command <200ms, setara push.                      |
//|                                                                   |
//| v5.10 (live bars + status market eksplisit):                     |
//|   - Heartbeat per slot simbol (bukan hanya chart) TETAP dikirim  |
//|     walau tidak ada tick (market tutup): field market_status     |
//|     (OPEN|CLOSED), market_close_reason (weekend|session|         |
//|     holiday|broker|no_data), trade_mode (SYMBOL_TRADE_MODE),     |
//|     symbol_time (SYMBOL_TIME), tick_age_s (TimeTradeServer -     |
//|     SYMBOL_TIME). Deteksi: sesi SymbolInfoSessionTrade + mode +  |
//|     umur tick (InpTickStaleSec).                                 |
//|   - Bar native per TF (M1/M5/M15/H1/H4/D1) dari CopyRates: saat  |
//|     iTime(0) berubah, kirim shift=1 (bar final) + shift=0 (bar   |
//|     berjalan) lewat /tick candles. Bar tanpa tick (volume 0)     |
//|     dilewati: tidak ada bar O=H=L=C karangan.                    |
//|   - OrderSend retcode 10018 (TRADE_RETCODE_MARKET_CLOSED): result|
//|     terstruktur (status FAILED, retcode, "market closed"), TANPA |
//|     retry, log sekali per kejadian + status CLOSED/broker di     |
//|     heartbeat selama InpMarketClosedHoldSec.                     |
//|                                                                   |
//| Result queue v5.02: transient retry backoff 1s..30s; permanen    |
//| (404/422/409) di-drop — anti poison-pill FIFO (head-of-line).     |
//| Seed v5.03: anti seed-loop — chunk gagal tidak lagi di-retry     |
//| buta tiap 1s (insiden 22 Nov: "total=5000 bars" tercetak 20.078x |
//| dalam sehari). Transient (5xx/-1/401/403): backoff 1s..30s + log |
//| tiap gagal. Permanen (4xx payload ditolak): drop TF + log.       |
//| "total=N bars" dicetak sekali per TF, bukan tiap retry.          |
//| Warisan v4.1 (tetap): filling fallback FOK→IOC→RETURN,           |
//| volume normalize, self-heal,                                     |
//| 4014 whitelist pesan jelas sekali + graceful retry.              |
//+------------------------------------------------------------------+
#property copyright "Lumine"
#property version   "5.10"
#property strict

input string  InpBridgeURL   = "http://127.0.0.1:3110/bridge"; // Base URL bridge fund2 (lokal, tanpa TLS)
input string  InpSecretFile  = "fund2_hmac.secret";          // File secret HMAC di MQL5/Files (bukan repo)
input int     InpPollMs     = 100;    // Interval timer fast-poll (ms, min 50)
input int     InpPollSec    = 5;      // Interval polling command (dtk; server long-poll floor 5s)
input int     InpPollHttpMs = 6500;   // Timeout HTTP request poll (ms; HARUS > floor 5s server)
input int     InpHeartbeatSec = 2;      // Interval heartbeat (detik, PRD: 2 dtk)
input int     InpTickBatchMs = 250;     // Umur batch tick sebelum flush (ms, PRD: 250 ms)
input int     InpTickBatchMax = 100;    // Isi maksimum batch tick (flush paksa)
input bool    InpSeedHistory = false;   // Seed candle multi-TF (P1a; v0 dummy tidak menyimpan candle)
input int     InpSeedChunks  = 500;     // Bar per chunk seed (100-1000)
input int     InpSeedMaxBars = 5000;    // Max bar per TF (batasi payload)
input int     InpMaxBackoff  = 60;      // Detik backoff maksimum saat bridge down
input int     InpPositionsInterval = 5;   // Detik antar snapshot positions
input int     InpDealWindowHours  = 24;   // Jam deal history dalam snapshot (PRD 5.8)
input bool    InpLiveBars     = true;   // Kirim bar native per TF saat bar baru (v5.10)
input int     InpBarPollMs    = 1000;   // Interval cek bar baru per TF (ms, min 200)
input int     InpTickStaleSec = 300;    // Umur tick (dtk) yang dianggap market tutup/no_data
input int     InpClosedHoldSec = 300;   // Lama status CLOSED/'broker' dipertahankan setelah 10018
input int     InpHeartbeatLogSec = 60;  // Interval log ringkas heartbeat (dtk, 0 = hanya saat berubah)

// ── Global State ──────────────────────────────────────────────────────────
string   g_apiURL;
string   g_basePath;                // bagian path dari InpBridgeURL (utk canonical HMAC)
string   g_secret;                  // secret HMAC (dari file, BUKAN dari repo)
bool     g_hmacReady = false;       // false = fail-closed: tidak kirim apa pun
string   g_orderId;                 // order_id command aktif (result sync)
datetime g_lastHeartbeat = 0;       // heartbeat terakhir TERKIRIM
datetime g_lastHeartbeatTry = 0;    // heartbeat terakhir dicoba
datetime g_lastTickSent   = 0;      // terakhir tick BERHASIL dikirim
datetime g_lastPositionsSent = 0;   // terakhir snapshot positions dikirim
int      g_failCount      = 0;      // consecutive bridge failure
bool     g_bridgeDown     = false;  // log state-change saja
int      g_maxBackoff;
uint     g_lastPollMs     = 0;      // GetTickCount() poll terakhir (throttle burst)
uint     g_lastSeedMs     = 0;      // throttle seed 1 chunk/detik
uint     g_lastFlushMs    = 0;      // GetTickCount() flush batch terakhir
uint     g_lastSecretWarnMs = 0;    // throttle peringatan secret kosong
bool     g_whitelistWarned = false; // 4014 sudah dilog (log sekali per episode)
bool     g_authWarned      = false; // 401/403 sudah dilog
bool     g_seedDisabled    = false; // /tick menolak candles → matikan seed

// ── Tick batch buffer (PRD 5.1: batch 250 ms, per simbol) ────────────────
// Multi-simbol (v5.01): slot per simbol base (XAUUSD + BTCUSD). Slot 0 =
// simbol chart; simbol lain di-resolve ke nama broker (mis. BTCUSD → #BTCUSD).
#define TICK_BUF_MAX 512
#define MAX_EA_SYMBOLS 8
string   g_slotBase[MAX_EA_SYMBOLS];    // nama kanonik (API): XAUUSD / BTCUSD
string   g_slotBroker[MAX_EA_SYMBOLS];  // nama simbol sesungguhnya di broker
string   g_slotItems[MAX_EA_SYMBOLS][TICK_BUF_MAX]; // item: {"ts":<ms>,"bid":..,"ask":..,"spread":..}
int      g_slotCount[MAX_EA_SYMBOLS];
ulong    g_slotDropped[MAX_EA_SYMBOLS]; // diagnostic: tick dibuang saat buffer penuh
long     g_slotLastTsMs[MAX_EA_SYMBOLS]; // envelope monotonik ts per slot (t_74b1f18f)
int      g_nSlots = 0;
uint     g_lastSynthMs = 0;         // sampel sintetis terakhir (market idle)

// ── Nonce generator state ────────────────────────────────────────────────
uint     g_nonceCounter = 0;
char     g_pollResult[];             // response buffer GET terakhir (Http)

// ── Result queue (persist: order result harus sampai ke backend) ──────────
#define RESULT_QUEUE_MAX 128
string   g_resultQueue[RESULT_QUEUE_MAX];
int      g_resultCount = 0;
// Anti head-of-line blocking (insiden 22 Nov: satu result 404 di-retry
// permanen tanpa backoff dan menyumbat FIFO — order lain macet di SENT).
// Transient (5xx/-1/401/403): retry 1s,2s,4s,... max 30s, log tiap gagal.
// Permanen (404/422/409): drop + log, jangan retry selamanya.
#define RESULT_RETRY_BASE_MS 1000
#define RESULT_RETRY_MAX_MS  30000
uint     g_lastResultTryMs = 0;   // GetTickCount() attempt terakhir (apapun hasilnya)
int      g_resultRetryMs   = 0;   // jeda backoff saat ini (0 = boleh langsung coba)

// ── Seed state machine (non-blocking) ────────────────────────────────────
bool     g_seedEnabled;
int      g_seedChunkSize;
int      g_seedMaxBars;
int      g_seedPhase     = 0;       // 0=idle 1=running 2=done
int      g_seedSymIdx    = 0;
int      g_seedTfIdx     = 0;
int      g_seedOffset    = 0;       // offset CopyRates pagination
int      g_seedTotal     = 0;
int      g_seedSent      = 0;
// Anti seed-loop (insiden 22 Nov: chunk gagal di-retry buta tiap 1s dan
// "total=N bars" tercetak ulang tiap retry — 20.078x dalam sehari).
// Transient (5xx/-1/401/403): backoff 1s..30s, log tiap gagal.
// Permanen (4xx payload ditolak): drop TF + log, jangan retry selamanya.
#define SEED_RETRY_BASE_MS 1000
#define SEED_RETRY_MAX_MS  30000
uint     g_lastSeedTryMs    = 0;   // GetTickCount() attempt seed terakhir
int      g_seedRetryMs      = 0;   // jeda backoff seed saat ini (0 = boleh langsung)
bool     g_seedTotalPrinted = false; // "total=N bars" sekali per TF, bukan tiap retry

string   g_seedSymbols[] = {"XAUUSD","BTCUSD"};   // XAUUSD live (PRD); BTCUSD dev/test weekend
ENUM_TIMEFRAMES g_seedTfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
string   g_seedTfNames[] = {"1m", "5m", "15m", "1h", "4h", "1d"};

// ── Live bar native per TF + status market (v5.10) ───────────────────────
// Nama timeframe kanonik API (kontrak candles: M1|M5|M15|H1|H4|D1).
// Seed historis tetap memakai g_seedTfNames (lowercase, dinormalisasi API);
// jalur live memakai nama kanonik supaya UI/DB satu seri.
#define MAX_EA_TFS 6
ENUM_TIMEFRAMES g_liveTfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_H4, PERIOD_D1};
string   g_liveTfNames[] = {"M1", "M5", "M15", "H1", "H4", "D1"};
datetime g_barLast[MAX_EA_SYMBOLS][MAX_EA_TFS];  // open time bar terakhir yang sudah diproses
bool     g_barSeen[MAX_EA_SYMBOLS][MAX_EA_TFS];  // false = belum pernah dapat iTime
bool     g_liveBars     = true;   // InpLiveBars (di-copy OnInit)
int      g_tickStaleSec = 300;    // InpTickStaleSec
int      g_closedHoldSec = 300;   // InpClosedHoldSec
int      g_hbLogSec     = 60;     // InpHeartbeatLogSec
uint     g_lastBarPollMs = 0;     // throttle cek bar baru
uint     g_barRetryAtMs  = 0;     // GetTickCount() sebelum retry candle gagal
datetime g_lastLiveBarLog = 0;    // throttle log livebars sukses
datetime g_lastLiveBarFailLog = 0;// throttle log livebars gagal
datetime g_slotClosedAt[MAX_EA_SYMBOLS];   // TimeLocal() retcode 10018 terakhir per slot
datetime g_slotClosedLog[MAX_EA_SYMBOLS];  // dedup log 10018 per slot
int      g_slotSessCount[MAX_EA_SYMBOLS];  // jumlah sesi sepekan (cache)
datetime g_slotSessAt[MAX_EA_SYMBOLS];     // waktu cache sesi dihitung
datetime g_hbLogAt = 0;           // log ringkas heartbeat terakhir
string   g_hbLogState = "";       // state heartbeat terakhir yang dilog (log saat berubah)

#define GV_SEED_DONE  "FUND2_EA_SEED_DONE"
#define GV_LAST_TICK  "FUND2_EA_LAST_TICK"

// ── Refresh bars M1 periodik ─────────────────────────────────────────────
datetime  g_lastM1Refresh = 0;

// ── Konversi jam broker -> true UTC (Bug B t_fbdb7329) ────────────────────
// Sejak 23 Nov 2026 08:55 UTC jam server broker = UTC+2 (terukur: tick
// time_msc = real +2h persis; label CopyRates juga +2h). Kontrak API:
// EA v5 kirim epoch ms true UTC (TimeGMT-anchored) untuk tick, dan ts
// candle UTC eksplisit untuk seed. Offset diukur dari
// TimeTradeServer() - TimeGMT() (valid walau market tutup) dan
// di-refresh tiap siklus timer; di luar rentang wajar broker (-12..+14h)
// nilai lama dipertahankan (fail-closed: tick tetap ditolak API, tidak
// ada data tercemar).
long     g_brokerOffsetSec = 0;   // detik jam-server broker di depan GMT

// ── Function prototypes ────────────────────────────────────────────────────
// PITFALL: build MetaEditor ini TIDAK hoist function —
// setiap function WAJIB dideklarasikan sebelum dipakai.
string   DeinitReasonStr(const int reason);
int      CurrentBackoff();
void     MarkBridgeOk();
void     MarkBridgeFail(const string where, const int code);
void     WarnWhitelist();
void     WarnAuth(const int code);
bool     LoadSecret();
string   NewNonce();
string   Sha256Hex(const string s);
string   SignHeaders(const string method, const string pathWithQuery, const string body);
int      HttpPostJson(const string path, const string json, const int timeoutMs);
int      HttpGetJson(const string pathWithQuery, const int timeoutMs);
void     QueueResult(const string json);
void     FlushOneResult(const datetime now, const bool force);
void     ShiftResultQueue();
void     SeedNextChunk();
void     SeedAdvanceTf();
void     PollCommands();
void     SendHeartbeat();
void     CaptureTick();
void     FlushTickBatch();
string   BuildTickBody(const string symbol, const string ticksJson, const string candlesJson);
void     SendPositionsSnapshot();
string   NormalizeSymbol(const string raw);
string   ResolveBrokerSymbol(const string base);
string   BrokerSymbol(const string base);
int      SlotIndex(const string base);
bool     AddSlot(const string base, const string broker);
void     InitSymbolTable();
int      TotalPendingTicks();
int      MaxSlotPending();
void     SeedRecentM1();
string   UnwrapCommand(const string json);
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
long     RefreshBrokerOffset();
string   CandleTsUtc(const datetime brokerTime);
long     EnforceMonotonicTs(const int si, const long tsMs);
// v5.10: live bar native per TF + status market eksplisit
void     InitLiveBars();
void     CheckNewBars();
void     EmitBarsForSlot(const int si);
string   CandleItemJson(const string base, const string tfName, const MqlRates &r);
bool     BarSendable(const MqlRates &r);
int      SecOfDay(const datetime t);
int      CountSessions(const string broker, const ENUM_DAY_OF_WEEK dow);
int      WeekSessions(const int si);
bool     SessionOpenAt(const string broker, const int dow, const int nowSec);
string   TradeModeStr(const string broker);
long     SymbolTickAge(const string broker);
string   EvalMarketStatus(const string broker, const int si, const int dow,
                          const int nowSec, const long tickAge, string &reason);
string   MarketStatusFor(const int si, string &reason, long &tickAge);
void     MarketStatusSelfCheck();
void     SendPlainHeartbeat();
void     HandleOrderFail(const string id, const string symbol, const uint retcode,
                         const double volume, const string kind);
string   BuildClosedResultJson(const string id, const uint retcode, const double volume,
                               const string kind);

//+------------------------------------------------------------------+
//| Offset jam broker vs GMT (detik) — diukur dari TimeTradeServer()  |
//| (estimasi jam server SAAT INI, valid walau market tutup) dikurangi |
//| TimeGMT(). Return nilai valid terakhir bila server belum sync /    |
//| offset di luar rentang wajar broker (fail-closed).                 |
//| Dikuantisasi ke menit utuh (t_74b1f18f): estimasi TimeTradeServer  |
//| bergetar ±1 dtk antar siklus timer; tanpa kuantisasi, ts tick real |
//| ikut bergetar dan stream jadi tidak monoton (validator API         |
//| membuang ekor di bawah high-water mark). Offset broker praktis     |
//| selalu kelipatan menit, jadi kuantisasi tidak mengubah nilai asli. |
//+------------------------------------------------------------------+
long RefreshBrokerOffset()
  {
   datetime srv = TimeTradeServer();
   datetime gmt = TimeGMT();
   if(srv <= 0 || gmt <= 0)
      return g_brokerOffsetSec;      // terminal belum sync jam server
   long off = (long)srv - (long)gmt;
   if(off < -12 * 3600 || off > 14 * 3600)
      return g_brokerOffsetSec;      // di luar rentang offset broker wajar
   off = ((off + 30) / 60) * 60;     // kuantisasi ke menit utuh (stabil)
   // Log hanya saat pergeseran besar (>2 menit) — perubahan jam broker /
   // DST terlihat, jitter +-1 detik tidak membanjiri journal.
   if((off - g_brokerOffsetSec > 120) || (g_brokerOffsetSec - off > 120))
      Print("LumineEA-Fund2: broker offset berubah ", g_brokerOffsetSec / 3600.0,
            "h -> ", off / 3600.0, "h (server=", TimeToString(srv, TIME_DATE|TIME_SECONDS),
            " GMT=", TimeToString(gmt, TIME_DATE|TIME_SECONDS), ")");
   g_brokerOffsetSec = off;
   return off;
  }

//+------------------------------------------------------------------+
//| Format ts candle UTC eksplisit (ISO +00:00) dari waktu broker.     |
//| Offset eksplisit di string membuat kunci DB benar apa pun timezone |
//| sesi DB (Postgres meng-hormati offset di string).                  |
//+------------------------------------------------------------------+
string CandleTsUtc(const datetime brokerTime)
  {
   datetime utc = (datetime)((long)brokerTime - g_brokerOffsetSec);
   MqlDateTime st;
   TimeToStruct(utc, st);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d+00:00",
                       st.year, st.mon, st.day, st.hour, st.min, st.sec);
  }

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_apiURL    = InpBridgeURL;
   g_seedEnabled = InpSeedHistory;
   g_seedChunkSize = MathMax(100, MathMin(1000, InpSeedChunks));
   g_seedMaxBars  = MathMax(100, InpSeedMaxBars);
   g_maxBackoff  = MathMax(5, InpMaxBackoff);
   g_liveBars     = InpLiveBars;
   g_tickStaleSec = MathMax(30, InpTickStaleSec);
   g_closedHoldSec = MathMax(0, InpClosedHoldSec);
   g_hbLogSec     = MathMax(0, InpHeartbeatLogSec);

   // basePath utk canonical string HMAC: "http://127.0.0.1:3110/bridge" → "/bridge"
   int scheme = StringFind(g_apiURL, "://");
   int slash  = (scheme >= 0) ? StringFind(g_apiURL, "/", scheme + 3) : StringFind(g_apiURL, "/");
   g_basePath = (slash >= 0) ? StringSubstr(g_apiURL, slash) : "/";

   MathSrand((int)GetTickCount());

   RefreshBrokerOffset();
   Print("LumineEA-Fund2 v5.05: broker offset terukur = ", g_brokerOffsetSec / 3600.0,
         " jam (tick & candle dikonversi ke true UTC)");

   g_hmacReady = LoadSecret();
   if(!g_hmacReady)
      Print("LumineEA-Fund2 v5.0: SECRET HMAC GAGAL DIMUAT dari MQL5/Files/",
            InpSecretFile, " — EA FAIL-CLOSED: heartbeat/tick TIDAK dikirim.",
            " Salin secret (env FUND2_HMAC_SECRET server) ke file tsb, lalu reload EA.");

   Print("LumineEA-Fund2 v5.0 (EA v0 P0) starting: bridge=", g_apiURL,
         " hmac=", (g_hmacReady ? "READY" : "MISSING"),
         " heartbeat=", MathMax(1, InpHeartbeatSec), "s",
         " tickBatch=", MathMax(50, InpTickBatchMs), "ms/",
         MathMax(1, InpTickBatchMax),
         " pollMs=", InpPollMs,
         " seed=", g_seedEnabled ? "ON" : "OFF",
         " build=", __DATE__, " started=", TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS));

   // PITFALL v2: polling di OnTick bergantung feed tick MT5. Feed pause →
   // EA mati total. Timer millisecond = polling mandiri + pickup cepat.
   EventSetMillisecondTimer(MathMax(50, InpPollMs));

   // Restore state (survive REASON_CHARTCHANGE/RECOMPILE/TEMPLATE)
   if(GlobalVariableCheck(GV_SEED_DONE) && GlobalVariableGet(GV_SEED_DONE) > 0)
     {
      g_seedPhase = 2;
      Print("LumineEA-Fund2: seed sudah pernah selesai (GlobalVariable) — skip");
     }
   else if(g_seedEnabled)
     {
      g_seedPhase  = 1;
      g_seedOffset = 0;
      Print("LumineEA-Fund2: seed candle mulai (non-blocking, via /tick candles)");
     }

   InitSymbolTable();
   InitLiveBars();
   MarketStatusSelfCheck();
   Print("LumineEA-Fund2 v5.05 ready (multi-simbol chart=", Symbol(),
         ", seed=", ArraySize(g_seedSymbols), "; HTTP fast-poll lokal, self-healing)");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();

   // Flush best-effort sebelum mati: result dulu (uang), lalu batch tick terakhir
   for(int i = 0; i < g_resultCount && i < 8; i++)
      FlushOneResult(0, true);   // force: tanpa backoff gate (mati betul-betul)
   if(g_hmacReady)
      FlushTickBatch();

   GlobalVariableSet(GV_LAST_TICK, (double)g_lastTickSent);
   ulong droppedAll = 0;
   for(int si = 0; si < g_nSlots; si++) droppedAll += g_slotDropped[si];
   Print("LumineEA-Fund2 stopping: reason=", reason, " (", DeinitReasonStr(reason),
         ") pendingResults=", g_resultCount, " pendingTicks=", TotalPendingTicks(),
         " droppedTicks=", droppedAll);
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
//| Expert timer — orkestrator utama (default 100ms)                  |
//| Prioritas: result > heartbeat > poll > tick batch > positions >   |
//| seed. Heartbeat & tick batch hanya saat HMAC secret siap.         |
//+------------------------------------------------------------------+
void OnTimer()
  {
   uint    nowMs = GetTickCount();
   datetime now  = TimeLocal();

   // 0) Offset jam broker -> UTC (murah; terukur ulang tiap siklus agar
   //    perubahan jam server / DST tertangkap cepat, log anti-spam)
   RefreshBrokerOffset();

   // 1) Flush result queue (order result = uang, prioritas tertinggi)
   if(g_resultCount > 0)
      FlushOneResult(now, false);

   if(!g_hmacReady)
     {
      // Fail-closed: tanpa secret tidak ada request ditandatangani.
      // Cek ulang secret tiap 60 dtk (file bisa dipasang belakangan).
      if(nowMs - g_lastSecretWarnMs >= 60000)
        {
         g_lastSecretWarnMs = nowMs;
         if(LoadSecret())
           {
            g_hmacReady = true;
            Print("LumineEA-Fund2: secret HMAC dimuat — pengiriman diaktifkan");
           }
        }
      return;
     }

   // 2) Heartbeat (PRD 5.5: tiap 2 detik; 3x terlewat = OFFLINE di server)
   if(now >= g_lastHeartbeatTry + MathMax(1, InpHeartbeatSec))
     {
      g_lastHeartbeatTry = now;
      SendHeartbeat();
     }

   // 3) Poll command — throttle burst antrean timer (saat WebRequest lama,
   //    event timer mengantre dan bisa memicu beberapa OnTimer beruntun)
   if(nowMs - g_lastPollMs >= (uint)MathMax(50, InpPollMs) - 20)
     {
      g_lastPollMs = nowMs;
      PollCommands();
     }

   // 4a) Market idle (tidak ada OnTick): sampel quote terakhir 1x/detik
   //     agar liquidity_samples, parquet, dan candle M1 tetap mengalir
   //     (spread real-time tetap tercatat walau market tidak kirim tick).
   if(nowMs - g_lastSynthMs >= 1000)
     {
      g_lastSynthMs = nowMs;
      CaptureSyntheticTicks();
     }

   // 3b) Bar native per TF (v5.10): deteksi bar baru → kirim shift=1 + shift=0.
   //     Ditaruh di OnTimer supaya tetap jalan saat market tutup / tanpa tick.
   CheckNewBars();

   // 4) Flush tick batch: umur batch >= InpTickBatchMs ATAU slot penuh
   if(TotalPendingTicks() > 0 &&
      (nowMs - g_lastFlushMs >= (uint)MathMax(50, InpTickBatchMs) ||
       MaxSlotPending() >= MathMax(1, InpTickBatchMax)))
     {
      FlushTickBatch();
     }

   // 5) Snapshot positions (tiap InpPositionsInterval detik)
   if(now >= g_lastPositionsSent + InpPositionsInterval)
     {
      g_lastPositionsSent = now;
      SendPositionsSnapshot();
     }

   // 6) Refresh bars M1 terbaru tiap 30 menit
   if(g_seedPhase == 2 && now >= g_lastM1Refresh + 1800)
     {
      g_lastM1Refresh = now;
      SeedRecentM1();
     }

   // 7) Seed non-blocking — throttle 1 chunk per detik (timer 100ms)
   if(g_seedPhase == 1 && nowMs - g_lastSeedMs >= 1000)
     {
      g_lastSeedMs = nowMs;
      SeedNextChunk();
     }
  }

//+------------------------------------------------------------------+
//| Expert tick — tiap tick MT5 masuk batch (di-flush OnTimer).       |
//| Timestamp = tick.time_msc (jam server) dikonversi true UTC.       |
//+------------------------------------------------------------------+
void OnTick()
  {
   CaptureTick();
   // v5.10: cek bar baru juga di jalur tick (throttle InpBarPollMs di dalam).
   CheckNewBars();
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

void MarkBridgeOk()
  {
   if(g_bridgeDown)
     {
      Print("LumineEA-Fund2: bridge RECOVERED (failures=", g_failCount, ")");
      g_bridgeDown = false;
     }
   g_failCount = 0;
   g_whitelistWarned = false;
   g_authWarned = false;
  }

void MarkBridgeFail(const string where, const int code)
  {
   g_failCount++;
   if(!g_bridgeDown)
     {
      g_bridgeDown = true;
      Print("LumineEA-Fund2: bridge UNREACHABLE at ", where, " code=", code,
            " — backoff mode (max ", g_maxBackoff, "s), will retry");
     }
  }

//+------------------------------------------------------------------+
//| 4014 = URL belum di-whitelist WebRequest. Graceful: pesan jelas   |
//| sekali per episode, EA terus retry tanpa crash.                   |
//+------------------------------------------------------------------+
void WarnWhitelist()
  {
   if(g_whitelistWarned) return;
   g_whitelistWarned = true;
   Print("LumineEA-Fund2: WebRequest DITOLAK (err=4014) — URL ", g_apiURL,
         " belum di-whitelist. Buka MT5 Tools -> Options -> Expert Advisors,",
         " centang 'Allow WebRequest for listed URL' dan tambahkan",
         " http://127.0.0.1:3110. EA retry otomatis.");
  }

void WarnAuth(const int code)
  {
   if(g_authWarned) return;
   g_authWarned = true;
   Print("LumineEA-Fund2: bridge menolak auth (http=", code,
         ") — cek isi MQL5/Files/", InpSecretFile,
         " terhadap env FUND2_HMAC_SECRET server. EA retry otomatis.");
  }

//+------------------------------------------------------------------+
//| Secret HMAC — dibaca dari file di sandbox MQL5/Files.            |
//| Sengaja BUKAN dari repo/input: file diprovisioning out-of-band   |
//| (sama dengan env FUND2_HMAC_SECRET di server). Fail-closed.       |
//+------------------------------------------------------------------+
bool LoadSecret()
  {
   int h = FileOpen(InpSecretFile, FILE_READ|FILE_BIN);
   if(h == INVALID_HANDLE)
      return false;
   int size = (int)FileSize(h);
   if(size <= 0 || size > 4096)
     {
      FileClose(h);
      return false;
     }
   uchar buf[];
   FileReadArray(h, buf, 0, size);
   FileClose(h);
   // trim whitespace/newline
   int end = size;
   while(end > 0 && (buf[end-1] == '\n' || buf[end-1] == '\r' ||
                     buf[end-1] == ' '  || buf[end-1] == '\t'))
      end--;
   int start = 0;
   while(start < end && (buf[start] == ' ' || buf[start] == '\t'))
      start++;
   if(end - start < 16)
      return false;   // terlalu pendek = secret tidak valid
   g_secret = CharArrayToString(buf, start, end - start, CP_UTF8);
   return StringLen(g_secret) >= 16;
  }

//+------------------------------------------------------------------+
//| Nonce: hex acak-secukunya, unik per request (dipakai sekali).     |
//| GetTickCount + counter + 2x MathRand → 32 hex char.               |
//+------------------------------------------------------------------+
string NewNonce()
  {
   g_nonceCounter++;
   return StringFormat("%08x%08x%08x%08x",
                       (uint)GetTickCount(), g_nonceCounter,
                       (uint)MathRand(), (uint)MathRand());
  }

//+------------------------------------------------------------------+
//| SHA256 + HMAC-SHA256 (CryptEncode tidak punya HMAC native).       |
//| HMAC(K,m) = SHA256((K'^opad) || SHA256(K'^ipad || m)), block 64B. |
//+------------------------------------------------------------------+
void Sha256(const uchar &data[], uchar &out[])
  {
   // SHA256("") yang dikenal — CryptEncode menolak array data kosong (err 4006)
   if(ArraySize(data) == 0)
     {
      static const uchar emptySha[32] =
        {0xe3,0xb0,0xc4,0x42,0x98,0xfc,0x1c,0x14,0x9a,0xfb,0xf4,0xc8,0x99,0x6f,0xb9,0x24,
         0x27,0xae,0x41,0xe4,0x64,0x9b,0x93,0x4c,0xa4,0x95,0x99,0x1b,0x78,0x52,0xb8,0x55};
      ArrayCopy(out, emptySha, 0, 0, 32);
      return;
     }
   uchar key[1];              // dummy key: CryptEncode menolak array key kosong (err 4006)
   key[0] = 0;
   ArrayResize(out, 0);
   int r = CryptEncode(CRYPT_HASH_SHA256, data, key, out);
   if(r != 32)
      Print("LumineEA-Fund2: CryptEncode SHA256 gagal r=", r, " err=", GetLastError());
  }

void HmacSha256(const uchar &key[], const uchar &msg[], uchar &mac[])
  {
   uchar k[64];
   ArrayInitialize(k, 0);
   if(ArraySize(key) > 64)
     {
      uchar hk[];
      Sha256(key, hk);
      ArrayCopy(k, hk, 0, 0, 32);
     }
   else
      ArrayCopy(k, key, 0, 0, ArraySize(key));

   uchar ipad[64], opad[64];
   for(int i = 0; i < 64; i++)
     {
      ipad[i] = (uchar)(k[i] ^ 0x36);
      opad[i] = (uchar)(k[i] ^ 0x5c);
     }

   int m = ArraySize(msg);
   uchar inner[];
   ArrayResize(inner, 64 + m);
   ArrayCopy(inner, ipad, 0, 0, 64);
   ArrayCopy(inner, msg, 64, 0, m);
   uchar ih[];
   Sha256(inner, ih);

   uchar outer[];
   ArrayResize(outer, 64 + 32);
   ArrayCopy(outer, opad, 0, 0, 64);
   ArrayCopy(outer, ih, 64, 0, 32);
   Sha256(outer, mac);
  }

//+------------------------------------------------------------------+
//| Byte array → hex lowercase                                        |
//+------------------------------------------------------------------+
string ToHex(const uchar &arr[])
  {
   string hex = "0123456789abcdef";
   string s = "";
   for(int i = 0; i < ArraySize(arr); i++)
      s += StringSubstr(hex, (arr[i] >> 4) & 0x0F, 1) + StringSubstr(hex, arr[i] & 0x0F, 1);
   return s;
  }

//+------------------------------------------------------------------+
//| SHA256 hex dari string UTF-8 (untuk hash body)                    |
//+------------------------------------------------------------------+
string Sha256Hex(const string s)
  {
   uchar data[];
   StringToCharArray(s, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);  // buang null terminator
   uchar hash[];
   Sha256(data, hash);
   return ToHex(hash);
  }

//+------------------------------------------------------------------+
//| Header request bertanda tangan (PRD v2.1 §7):                     |
//|   string_to_sign = ts \n nonce \n METHOD \n path \n sha256(body)  |
//|   X-Fund2-Signature = hex HMAC-SHA256(secret, string_to_sign)     |
//| pathWithQuery = path LENGKAP yang dikirim, mis. "/bridge/tick"    |
//| atau "/bridge/poll?timeout_s=0" (harus persis seperti URL).       |
//+------------------------------------------------------------------+
string SignHeaders(const string method, const string pathWithQuery, const string body)
  {
   string ts    = IntegerToString((long)TimeGMT());
   string nonce = NewNonce();
   string sts   = ts + "\n" + nonce + "\n" + method + "\n" + pathWithQuery + "\n" + Sha256Hex(body);

   uchar key[], msg[], mac[];
   StringToCharArray(g_secret, key, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(key, ArraySize(key) - 1);
   StringToCharArray(sts, msg, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(msg, ArraySize(msg) - 1);
   HmacSha256(key, msg, mac);

   return "Content-Type: application/json\r\n" +
          "X-Fund2-Timestamp: " + ts + "\r\n" +
          "X-Fund2-Nonce: " + nonce + "\r\n" +
          "X-Fund2-Signature: " + ToHex(mac) + "\r\n";
  }

//+------------------------------------------------------------------+
//| HTTP POST JSON (WebRequest wrapper, tahan banting) + HMAC         |
//| `path` = path RELATIF terhadap base (".../bridge" + "/tick")      |
//+------------------------------------------------------------------+
int HttpPostJson(const string path, const string json, const int timeoutMs)
  {
   char data[];
   StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);  // buang null terminator

   char result[];
   string resultHeaders;
   string url = g_apiURL + path;

   int res = WebRequest("POST", url, SignHeaders("POST", g_basePath + path, json),
                        timeoutMs, data, result, resultHeaders);
   return res;
  }

//+------------------------------------------------------------------+
//| HTTP GET bertanda tangan (poll). Body kosong → sha256("").        |
//+------------------------------------------------------------------+
int HttpGetJson(const string pathWithQuery, const int timeoutMs)
  {
   char   data[];
   char   result[];          // buffer LOKAL: WebRequest mengisi array hasil sendiri
   string resultHeaders;
   string url = g_apiURL + pathWithQuery;

   ArrayResize(data, 0);
   ArrayResize(g_pollResult, 0);

   int res = WebRequest("GET", url, SignHeaders("GET", g_basePath + pathWithQuery, ""),
                        timeoutMs, data, result, resultHeaders);
   if(res == 200 && ArraySize(result) > 0)
     {
      ArrayResize(g_pollResult, ArraySize(result));
      ArrayCopy(g_pollResult, result);
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
      Print("LumineEA-Fund2: result queue FULL, dropping oldest");
      for(int i = 1; i < RESULT_QUEUE_MAX; i++)
         g_resultQueue[i - 1] = g_resultQueue[i];
      g_resultCount = RESULT_QUEUE_MAX - 1;
     }
   g_resultQueue[g_resultCount] = json;
   g_resultCount++;
  }

void FlushOneResult(const datetime now, const bool force)
  {
   if(g_resultCount <= 0) return;

   // Backoff gate: setelah gagal transient, tahan retry sesuai jeda saat ini
   // (1s..30s). force=true hanya untuk flush best-effort di OnDeinit.
   uint nowMs = GetTickCount();
   if(!force && g_resultRetryMs > 0 &&
      nowMs - g_lastResultTryMs < (uint)g_resultRetryMs)
      return;
   g_lastResultTryMs = nowMs;

   string json = g_resultQueue[0];
   int res = HttpPostJson("/result", json, 3000);

   if(res == 200)
     {
      ShiftResultQueue();
      g_resultRetryMs = 0;   // sukses: reset backoff
      Print("LumineEA-Fund2: result terkirim (sisa antrean=", g_resultCount, ")");
      return;
     }

   // Permanen: retry tidak akan pernah sukses → drop kepala antrean.
   //  404 = unknown command_id (command/order sudah tidak ada di DB),
   //  422 = payload ditolak validasi,
   //  409 = order sudah meninggalkan SENT/STUCK dan tidak akan kembali
   //        (state machine tidak punya transisi balik ke SENT/STUCK).
   // Tanpa drop, satu poison pill menyumbat FIFO: semua result di
   // belakangnya tak pernah terkirim (head-of-line blocking, insiden 22 Nov).
   if(res == 404 || res == 422 || res == 409)
     {
      string cid = ExtractJsonString(json, "command_id");
      Print("LumineEA-Fund2: result DROPPED http=", res, " command_id=", cid,
            " (permanen, tidak di-retry) — sisa antrean=", g_resultCount - 1);
      ShiftResultQueue();
      g_resultRetryMs = 0;   // kepala baru: boleh langsung dicoba
      return;
     }

   if(res == 401 || res == 403)
      WarnAuth(res);   // auth bisa pulang saat secret dipasang → tetap transient

   // Transient (5xx, -1 jaringan, auth, lainnya): retry dengan backoff
   // eksponensial 1s, 2s, 4s, ... max 30s. Log tiap gagal + isi antrean.
   g_resultRetryMs = (g_resultRetryMs <= 0)
                     ? RESULT_RETRY_BASE_MS
                     : MathMin(RESULT_RETRY_MAX_MS, g_resultRetryMs * 2);
   Print("LumineEA-Fund2: result gagal http=", res, " — retry dalam ",
         g_resultRetryMs, " ms (isi antrean=", g_resultCount, ")");
  }

//+------------------------------------------------------------------+
//| Buang kepala antrean result (FIFO shift)                          |
//+------------------------------------------------------------------+
void ShiftResultQueue()
  {
   for(int i = 1; i < g_resultCount; i++)
      g_resultQueue[i - 1] = g_resultQueue[i];
   g_resultCount--;
  }

//+------------------------------------------------------------------+
//| Seed candle — non-blocking, multi-TF, paginated                   |
//| 1 chunk per detik, dikirim via POST /tick body "candles".         |
//+------------------------------------------------------------------+
void SeedNextChunk()
  {
   if(g_seedPhase != 1) return;
   // Backoff gate: setelah gagal transient, tahan retry sesuai jeda saat ini
   // (1s..30s). Tanpa ini chunk yang sama di-retry buta tiap 1 detik.
   uint nowMs = GetTickCount();
   if(nowMs - g_lastSeedTryMs < (uint)g_seedRetryMs)
      return;
   g_lastSeedTryMs = nowMs;
   if(g_seedSymIdx >= ArraySize(g_seedSymbols))
     {
      g_seedPhase = 2;
      GlobalVariableSet(GV_SEED_DONE, 1);
      Print("LumineEA-Fund2: SeedCandle SELESAI total bars=", g_seedSent);
      return;
     }
   if(g_seedDisabled)
     {
      g_seedPhase = 2;
      return;
     }

   string baseSym = NormalizeSymbol(g_seedSymbols[g_seedSymIdx]);
   string sym = BrokerSymbol(baseSym);   // nama broker (mis. #BTCUSD) untuk CopyRates
   ENUM_TIMEFRAMES tf = g_seedTfs[g_seedTfIdx];
   string tfName = g_seedTfNames[g_seedTfIdx];

   if(g_seedOffset == 0)
     {
      g_seedTotal = MathMin(iBars(sym, tf), g_seedMaxBars);
      if(g_seedTotal <= 0)
        {
         Print("LumineEA-Fund2: seed ", baseSym, " ", tfName, " gagal iBars err=", GetLastError());
         SeedAdvanceTf();
         return;
        }
      if(!g_seedTotalPrinted)
        {
         Print("LumineEA-Fund2: seed ", baseSym, " ", tfName, " total=", g_seedTotal, " bars");
         g_seedTotalPrinted = true;
        }
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
         Print("LumineEA-Fund2: seed ", sym, " ", tfName, " tidak ada history (err=", err, ") — skip TF");
        }
      else
        {
         Print("LumineEA-Fund2: seed CopyRates ", sym, " ", tfName, " err=", err, " — retry tick depan");
         // Jangan advance — retry chunk sama dengan backoff (non-blocking)
         if(err == 4014)
            SeedAdvanceTf();
         else
            SeedBackoff();
         return;
        }
      SeedAdvanceTf();
      return;
     }

   ArraySetAsSeries(rates, false);
   string candles = "[";
   for(int i = 0; i < got; i++)
     {
      MqlRates r = rates[i];
      if(i > 0) candles += ",";
      candles += StringFormat("{\"symbol\":\"%s\",\"timeframe\":\"%s\",\"ts\":\"%s\",\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f}",
                              baseSym, tfName, CandleTsUtc(r.time),
                              r.open, r.high, r.low, r.close, (double)r.tick_volume);
     }
   candles += "]";

   int res = HttpPostJson("/tick", BuildTickBody(baseSym, "", candles), 5000);
   if(res == 200)
     {
      MarkBridgeOk();
      g_seedOffset += got;
      g_seedSent += got;
      SeedResetBackoff();   // sukses: reset backoff
      if(g_seedOffset >= g_seedTotal)
         SeedAdvanceTf();
     }
   else if(res == 401 || res == 403)
     {
      WarnAuth(res);        // auth bisa pulang saat secret dipasang → transient
      SeedBackoff();
     }
   else if(res >= 400 && res < 500)
     {
      // Permanen: payload chunk ditolak validasi API (413/422/4xx lain).
      // Retry buta tidak akan pernah maju — drop TF ini dan lanjut.
      Print("LumineEA-Fund2: seed chunk DITOLAK http=", res, " ", baseSym, " ",
            tfName, " offset=", g_seedOffset, " — skip TF (permanen, tidak di-retry)");
      SeedAdvanceTf();
      SeedResetBackoff();
     }
   else if(res == -1)
     {
      int err = GetLastError();
      if(err == 4014)
        {
         WarnWhitelist();
         SeedBackoff();
        }
      else if(err != 0)
        {
         MarkBridgeFail("SeedCandles", err);
         SeedBackoff();
        }
      else
        {
         // err==0: gagal tanpa kode dari WebRequest (terjadi saat API sakit,
         // insiden 22 Nov 04:55-07:44). Tetap di-backoff dan DILog agar
         // kegagalan tidak lagi senyap.
         Print("LumineEA-Fund2: seed chunk gagal http=-1 err=0 ", baseSym, " ",
               tfName, " offset=", g_seedOffset, " — retry dengan backoff");
         SeedBackoff();
        }
     }
   else
     {
      MarkBridgeFail("SeedCandles-http", res);   // 5xx & lainnya → transient
      SeedBackoff();
     }
   // res != 200 → chunk sama di-retry sesuai backoff (state tidak maju)
  }

//+------------------------------------------------------------------+
//| Backoff seed: 1,2,4,...,max 30s. Reset saat sukses.               |
//+------------------------------------------------------------------+
void SeedBackoff()
  {
   g_seedRetryMs = (g_seedRetryMs <= 0)
                   ? SEED_RETRY_BASE_MS
                   : MathMin(SEED_RETRY_MAX_MS, g_seedRetryMs * 2);
  }

void SeedResetBackoff()
  {
   g_seedRetryMs = 0;
  }

//+------------------------------------------------------------------+
//| Bangun body /tick (v0):                                           |
//| {symbol, ticks:[{ts,bid,ask,spread}...], candles?}                |
//| ticksJson/candlesJson = string JSON array siap pakai (boleh kosong)|
//+------------------------------------------------------------------+
string BuildTickBody(const string symbol, const string ticksJson, const string candlesJson)
  {
   string json = "{\"symbol\":\"" + symbol + "\",\"ticks\":";
   if(StringLen(ticksJson) > 0) json += ticksJson; else json += "[]";
   if(StringLen(candlesJson) > 0)
      json += ",\"candles\":" + candlesJson;
   json += "}";
   return json;
  }

void SeedAdvanceTf()
  {
   g_seedTfIdx++;
   g_seedOffset = 0;
   g_seedTotal = 0;
   g_seedTotalPrinted = false;   // TF baru: boleh cetak "total=N" lagi
   if(g_seedTfIdx >= ArraySize(g_seedTfs))
     {
      g_seedTfIdx = 0;
      g_seedSymIdx++;
     }
  }

//+------------------------------------------------------------------+
//| v5.10 — STATUS MARKET EKSPLISIT (per simbol, walau tidak ada tick) |
//| Sumber keputusan (urutan):                                        |
//|   1. SYMBOL_TRADE_MODE == DISABLED        -> CLOSED/'broker'       |
//|   2. retcode 10018 baru (< hold)          -> CLOSED/'broker'       |
//|   3. sesi SymbolInfoSessionTrade tutup    -> CLOSED/'weekend' |    |
//|      'holiday' (hari tanpa sesi) | 'session' (di luar jam sesi)    |
//|   4. umur tick > InpTickStaleSec / belum  -> CLOSED/'no_data'      |
//|      ada tick sama sekali                                          |
//|   5. selain itu                            -> OPEN                  |
//| Sesi yang tidak tersedia di broker (0 sesi sepekan) TIDAK dipakai  |
//| untuk menyimpulkan tutup: jatuh ke aturan umur tick (fail-open     |
//| untuk status, heartbeat tetap terkirim).                           |
//+------------------------------------------------------------------+
int SecOfDay(const datetime t)
  {
   MqlDateTime st;
   TimeToStruct(t, st);
   return st.hour * 3600 + st.min * 60 + st.sec;
  }

int CountSessions(const string broker, const ENUM_DAY_OF_WEEK dow)
  {
   datetime from, to;
   int n = 0;
   for(uint k = 0; k < 32; k++)   // batas aman: broker tidak punya 32 sesi/hari
     {
      if(!SymbolInfoSessionTrade(broker, dow, k, from, to))
         break;
      // Placeholder 00:00-00:00 = broker menandai hari itu tanpa sesi
      // (dipakai HFM untuk Sabtu/Minggu), bukan sesi 24 jam.
      if(SecOfDay(from) == 0 && SecOfDay(to) == 0)
         continue;
      n++;
     }
   return n;
  }

// Jumlah sesi sepekan (cache 1 jam): 0 = broker tidak menyediakan jadwal sesi.
int WeekSessions(const int si)
  {
   if(si < 0 || si >= g_nSlots)
      return 0;
   if(g_slotSessAt[si] != 0 && TimeLocal() - g_slotSessAt[si] < 3600)
      return g_slotSessCount[si];
   int total = 0;
   for(int d = 0; d < 7; d++)
      total += CountSessions(g_slotBroker[si], (ENUM_DAY_OF_WEEK)d);
   g_slotSessCount[si] = total;
   g_slotSessAt[si]    = TimeLocal();
   return total;
  }

// Sesi hari `dow` mencakup detik ke-nowSec? Termasuk sesi lintas tengah malam.
bool SessionOpenAt(const string broker, const int dow, const int nowSec)
  {
   datetime from, to;
   for(uint k = 0; k < 32; k++)
     {
      if(!SymbolInfoSessionTrade(broker, (ENUM_DAY_OF_WEEK)dow, k, from, to))
         break;
      int fs = SecOfDay(from);
      int ts = SecOfDay(to);
      if(fs == 0 && ts == 0)              // placeholder = tanpa sesi hari ini
         continue;
      if(fs <= ts)
        {
         if(nowSec >= fs && nowSec < ts) return true;
        }
      else if(nowSec >= fs)               // sesi lanjut ke besok
         return true;
     }
   // Sesi kemarin yang melewati tengah malam (mis. 23:00-01:00).
   int ydow = (dow + 6) % 7;
   for(uint k2 = 0; k2 < 32; k2++)
     {
      if(!SymbolInfoSessionTrade(broker, (ENUM_DAY_OF_WEEK)ydow, k2, from, to))
         break;
      int fs2 = SecOfDay(from);
      int ts2 = SecOfDay(to);
      if(fs2 > ts2 && nowSec < ts2)
         return true;
     }
   return false;
  }

string TradeModeStr(const string broker)
  {
   int m = (int)SymbolInfoInteger(broker, SYMBOL_TRADE_MODE);
   switch(m)
     {
      case SYMBOL_TRADE_MODE_DISABLED:  return "DISABLED";
      case SYMBOL_TRADE_MODE_LONGONLY:  return "LONGONLY";
      case SYMBOL_TRADE_MODE_SHORTONLY: return "SHORTONLY";
      case SYMBOL_TRADE_MODE_CLOSEONLY: return "CLOSEONLY";
      case SYMBOL_TRADE_MODE_FULL:      return "FULL";
     }
   return "UNKNOWN";
  }

// Umur tick server (detik): TimeTradeServer() - SYMBOL_TIME. -1 = tidak diketahui.
long SymbolTickAge(const string broker)
  {
   long t = (long)SymbolInfoInteger(broker, SYMBOL_TIME);
   if(t <= 0)
      return -1;
   long age = (long)TimeTradeServer() - t;
   if(age < 0)
      age = 0;   // jam server bergetar ±1 dtk
   return age;
  }

// Keputusan status (murni terhadap parameter waktu: dipakai juga self-check).
// Urutan: bukti tick segar menang atas jadwal (feed hidup = OPEN), lalu jadwal
// sesi untuk menyimpulkan CLOSED, lalu umur tick untuk 'no_data'.
string EvalMarketStatus(const string broker, const int si, const int dow,
                        const int nowSec, const long tickAge, string &reason)
  {
   reason = "";
   if(StringLen(broker) == 0)
     {
      reason = "no_data";
      return "CLOSED";
     }
   // 1. broker mematikan trading simbol ini
   if(SymbolInfoInteger(broker, SYMBOL_TRADE_MODE) == SYMBOL_TRADE_MODE_DISABLED)
     {
      reason = "broker";
      return "CLOSED";
     }
   // 2. broker baru saja menolak order: 10018 market closed
   if(si >= 0 && si < g_nSlots && g_slotClosedAt[si] > 0 &&
      g_closedHoldSec > 0 && TimeLocal() - g_slotClosedAt[si] <= g_closedHoldSec)
     {
      reason = "broker";
      return "CLOSED";
     }
   // 3. tick segar = bukti langsung market hidup (mengalahkan jadwal yang
   //    kadang tidak akurat di broker demo, mis. sesi 00:00-00:00 di hari libur)
   bool freshTick = (tickAge >= 0 && tickAge <= (long)g_tickStaleSec);
   if(freshTick)
      return "OPEN";

   // 4. jadwal sesi broker (hanya untuk menyimpulkan CLOSED)
   int weekSessions = (si >= 0) ? WeekSessions(si) : 0;
   if(weekSessions > 0 && !SessionOpenAt(broker, dow, nowSec))
     {
      if(dow == 0 || dow == 6)
         reason = "weekend";
      else if(CountSessions(broker, (ENUM_DAY_OF_WEEK)dow) == 0)
         reason = "holiday";      // hari kerja tanpa sesi = libur bursa
      else
         reason = "session";      // di luar jam sesi hari ini
      return "CLOSED";
     }
   // 5. tidak ada tick segar (feed putus / simbol tanpa data / market tutup
   //    walau jadwal bilang buka)
   reason = "no_data";
   return "CLOSED";
  }

string MarketStatusFor(const int si, string &reason, long &tickAge)
  {
   string broker = (si >= 0 && si < g_nSlots) ? g_slotBroker[si] : Symbol();
   tickAge = SymbolTickAge(broker);
   datetime srv = TimeTradeServer();
   MqlDateTime st;
   TimeToStruct(srv, st);
   return EvalMarketStatus(broker, si, st.day_of_week,
                           st.hour * 3600 + st.min * 60 + st.sec, tickAge, reason);
  }

//+------------------------------------------------------------------+
//| Self-check status market saat OnInit: jalankan FUNGSI YANG SAMA    |
//| dengan waktu injeksi (Sabtu/Minggu 12:00) supaya cabang CLOSED/    |
//| weekend benar-benar dieksekusi, bukan hanya dibaca.               |
//+------------------------------------------------------------------+
void MarketStatusSelfCheck()
  {
   if(g_nSlots <= 0)
      return;
   // Dump jadwal sesi broker sekali saat start: hari libur/placeholder
   // (00:00-00:00) tidak terlihat di UI MT5 dan selama ini jadi sumber
   // kesalahan "market tutup tapi status OPEN".
   static string dayName[7] = {"Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"};
   for(int si = 0; si < g_nSlots; si++)
     {
      string tbl = "";
      bool any = false;
      datetime from, to;
      for(int d = 0; d < 7; d++)
        {
         for(uint k = 0; k < 8; k++)
           {
            if(!SymbolInfoSessionTrade(g_slotBroker[si], (ENUM_DAY_OF_WEEK)d, k, from, to))
               break;
            if(SecOfDay(from) == 0 && SecOfDay(to) == 0)   // placeholder
               continue;
            any = true;
            tbl += (StringLen(tbl) > 0 ? " " : "") + dayName[d] + ":" +
                   TimeToString(from, TIME_MINUTES) + "-" + TimeToString(to, TIME_MINUTES);
           }
        }
      Print("LumineEA-Fund2: selfcheck sesi ", g_slotBase[si], " = ",
            (any ? tbl : "(tidak ada sesi terdefinisi)"));
     }
   // Cabang CLOSED diuji dengan fungsi yang sama: Sabtu/Minggu 12:00 dengan
   // umur tick 10 menit (lewat InpTickStaleSec) supaya jadwal sesi yang bicara.
   long staleAge = (long)g_tickStaleSec + 600;
   for(int d = 0; d < 7; d++)
     {
      if(d != 0 && d != 6)
         continue;                          // Sabtu (6) & Minggu (0) saja
      string r = "";
      string status = EvalMarketStatus(g_slotBroker[0], 0, d, 12 * 3600, staleAge, r);
      Print("LumineEA-Fund2: selfcheck status ", g_slotBase[0],
            (d == 6 ? " Sabtu 12:00" : " Minggu 12:00"), " -> ", status,
            "/", (StringLen(r) > 0 ? r : "-"),
            " (sesi sepekan=", WeekSessions(0), ")");
     }
  }

//+------------------------------------------------------------------+
//| LIVE BAR NATIVE PER TF (v5.10)                                     |
//| CopyRates langsung (bukan sampling tick/kelipatan 5 menit). Saat   |
//| iTime(sym,tf,0) berubah: kirim shift=1 (bar final) + shift=0 (bar  |
//| berjalan). Bar tanpa tick (tick_volume 0) DILEWATI — tidak ada     |
//| bar O=H=L=C karangan saat market tutup.                            |
//+------------------------------------------------------------------+
string CandleItemJson(const string base, const string tfName, const MqlRates &r)
  {
   return StringFormat("{\"symbol\":\"%s\",\"timeframe\":\"%s\",\"ts\":\"%s\","
                       "\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f}",
                       base, tfName, CandleTsUtc(r.time),
                       r.open, r.high, r.low, r.close, (double)r.tick_volume);
  }

// Bar layak dikirim? Semua bar berasal dari CopyRates (Bid-based, jam server).
// tick_volume == 0 berarti belum ada tick pada bar itu → data karangan, buang.
bool BarSendable(const MqlRates &r)
  {
   if(r.open <= 0 || r.high <= 0 || r.low <= 0 || r.close <= 0)
      return false;
   if(r.high < r.low || r.high < MathMax(r.open, r.close) ||
      r.low > MathMin(r.open, r.close))
      return false;
   if(r.tick_volume <= 0)
      return false;
   return true;
  }

void InitLiveBars()
  {
   for(int si = 0; si < g_nSlots; si++)
      for(int t = 0; t < MAX_EA_TFS; t++)
        {
         g_barLast[si][t] = (datetime)iTime(g_slotBroker[si], g_liveTfs[t], 0);
         g_barSeen[si][t] = (g_barLast[si][t] > 0);
        }
   g_lastBarPollMs = GetTickCount();
  }

void CheckNewBars()
  {
   if(!g_liveBars || g_nSlots <= 0)
      return;
   uint nowMs = GetTickCount();
   if((int)(nowMs - g_lastBarPollMs) < MathMax(200, InpBarPollMs))
      return;
   if((long)g_barRetryAtMs - (long)nowMs > 0)
      return;   // jeda retry candle gagal (≤ 1x/5 dtk, bukan loop ketat)
   g_lastBarPollMs = nowMs;
   for(int si = 0; si < g_nSlots; si++)
      EmitBarsForSlot(si);
  }

void EmitBarsForSlot(const int si)
  {
   string broker = g_slotBroker[si];
   string base   = g_slotBase[si];
   if(StringLen(broker) == 0 || StringLen(base) == 0)
      return;

   string reason = "";
   long   age    = 0;
   string status = MarketStatusFor(si, reason, age);

   string candles = "";
   string sentTfs = "";
   int    advTf[MAX_EA_TFS];
   datetime advTs[MAX_EA_TFS];
   int    advN = 0;

   for(int t = 0; t < MAX_EA_TFS; t++)
     {
      datetime bar0 = (datetime)iTime(broker, g_liveTfs[t], 0);
      if(bar0 <= 0)
         continue;                                   // belum ada history sama sekali
      bool firstSight = !g_barSeen[si][t];
      if(firstSight)
        {
         // Baseline pertama setelah EA start: kirim bar BERJALAN saja (shift=0)
         // supaya tiap TF langsung segar di DB, tanpa mengirim ulang riwayat.
         g_barSeen[si][t] = true;
         g_barLast[si][t] = bar0;
        }
      else if(bar0 == g_barLast[si][t])
         continue;                                   // bar belum berganti

      MqlRates closed[], running[];
      // shift=1: bar yang baru tutup, OHLCV final (tidak untuk baseline pertama)
      if(!firstSight && CopyRates(broker, g_liveTfs[t], 1, 1, closed) == 1 && BarSendable(closed[0]))
        {
         if(StringLen(candles) > 0) candles += ",";
         candles += CandleItemJson(base, g_liveTfNames[t], closed[0]);
         if(StringLen(sentTfs) > 0) sentTfs += ",";
         sentTfs += g_liveTfNames[t];
        }
      // shift=0: bar berjalan (hanya saat market OPEN — kalau tutup, tidak ada
      // tick baru dan bar berjalan tidak boleh dikirim)
      if(status == "OPEN" &&
         CopyRates(broker, g_liveTfs[t], 0, 1, running) == 1 && BarSendable(running[0]))
        {
         if(StringLen(candles) > 0) candles += ",";
         candles += CandleItemJson(base, g_liveTfNames[t], running[0]);
         if(StringLen(sentTfs) > 0) sentTfs += ",";
         sentTfs += g_liveTfNames[t] + "*";
        }
      advTf[advN] = t;
      advTs[advN] = bar0;
      advN++;
     }

   if(advN <= 0)
      return;                                        // tidak ada bar baru

   if(StringLen(candles) == 0)
     {
      // Market tutup / belum ada tick: tidak ada yang layak dikirim, tapi bar
      // tetap dianggap sudah diproses supaya tidak dievaluasi tiap siklus.
      for(int i = 0; i < advN; i++)
         g_barLast[si][advTf[i]] = advTs[i];
      return;
     }

   int res = HttpPostJson("/tick", BuildTickBody(base, "", "[" + candles + "]"), 3000);
   if(res == 200)
     {
      MarkBridgeOk();
      for(int j = 0; j < advN; j++)
         g_barLast[si][advTf[j]] = advTs[j];
      if(TimeLocal() - g_lastLiveBarLog >= 60)
        {
         g_lastLiveBarLog = TimeLocal();
         Print("LumineEA-Fund2: livebars ", base, " kirim ", sentTfs,
               " (status=", status, ", tick_age=", age, "s)");
        }
      return;
     }

   // Gagal: jangan majukan bar (bar yang sama dicoba lagi ≤ 1x/5 dtk).
   g_barRetryAtMs = GetTickCount() + 5000;
   if(res == -1)
     {
      int err = GetLastError();
      if(err == 4014)
         WarnWhitelist();
      else if(err != 0)
         MarkBridgeFail("LiveBars", err);
     }
   else if(res == 401 || res == 403)
      WarnAuth(res);
   else
      MarkBridgeFail("LiveBars-http", res);

   if(TimeLocal() - g_lastLiveBarFailLog >= 60)
     {
      g_lastLiveBarFailLog = TimeLocal();
      Print("LumineEA-Fund2: livebars ", base, " gagal http=", res,
            " — retry 5 dtk (bar belum dimajukan)");
     }
  }

//+------------------------------------------------------------------+
//| Heartbeat (PRD 5.5 + v5.10): POST /bridge/heartbeat tiap 2 detik. |
//| Satu heartbeat per SLOT simbol (bukan hanya chart) dan tetap       |
//| dikirim walau tidak ada tick (market tutup) — body:                |
//| {ts, symbol, bid, ask, spread, ea, market_status,                  |
//|  market_close_reason, trade_mode, trade_enabled, symbol_time,       |
//|  tick_age_s}                                                      |
//| symbol_time = SYMBOL_TIME (jam server, detik epoch, 0 = belum ada)  |
//| tick_age_s  = TimeTradeServer() - SYMBOL_TIME (-1 = tidak diketahui)|
//| market_close_reason = "" saat OPEN (string, bukan null, supaya      |
//| konsumen non-optional tetap valid).                                |
//+------------------------------------------------------------------+
void SendHeartbeat()
  {
   if(g_nSlots <= 0)
     {
      InitSymbolTable();          // jaga-jaga: tabel simbol belum terbentuk
      if(g_nSlots <= 0)
        {
         SendPlainHeartbeat();    // fail-safe: minimal tetap ada liveness
         return;
        }
     }

   int    okCount = 0;
   string logLine = "";
   string stateKey = "";

   for(int si = 0; si < g_nSlots; si++)
     {
      string symbol = g_slotBase[si];
      string broker = g_slotBroker[si];
      if(StringLen(symbol) == 0 || StringLen(broker) == 0)
         continue;

      double bid = SymbolInfoDouble(broker, SYMBOL_BID);
      double ask = SymbolInfoDouble(broker, SYMBOL_ASK);
      double spread = (bid > 0 && ask > 0 && ask >= bid) ? (ask - bid) : 0.0;

      string reason = "";
      long   age    = 0;
      string status = MarketStatusFor(si, reason, age);
      string mode   = TradeModeStr(broker);
      datetime symTime = (datetime)SymbolInfoInteger(broker, SYMBOL_TIME);

      string json = StringFormat("{\"ts\":%I64d,\"symbol\":\"%s\",\"bid\":%s,\"ask\":%s,"
                                 "\"spread\":%s,\"ea\":\"v5\","
                                 "\"market_status\":\"%s\",\"market_close_reason\":\"%s\","
                                 "\"trade_mode\":\"%s\",\"trade_enabled\":%s,"
                                 "\"symbol_time\":%I64d,\"tick_age_s\":%I64d}",
                                 (long)TimeGMT(), symbol,
                                 DoubleToString(bid, 5), DoubleToString(ask, 5),
                                 DoubleToString(spread, 5), status, EscapeJson(reason),
                                 mode,
                                 (mode == "FULL" || mode == "LONGONLY" ||
                                  mode == "SHORTONLY") ? "true" : "false",
                                 (long)symTime, age);

      int res = HttpPostJson("/heartbeat", json, 3000);
      if(res == 200)
        {
         MarkBridgeOk();
         g_lastHeartbeat = TimeLocal();
         okCount++;
        }
      else if(res == -1)
        {
         int err = GetLastError();
         if(err == 4014)
            WarnWhitelist();
         else if(err != 0)
            MarkBridgeFail("Heartbeat", err);
        }
      else if(res == 401 || res == 403)
         WarnAuth(res);
      else
         MarkBridgeFail("Heartbeat-http", res);

      if(si == 0 || StringLen(logLine) == 0)
        {
         logLine = StringFormat("%s status=%s reason=%s mode=%s sym_time=%s tick_age=%ds",
                                symbol, status, (StringLen(reason) > 0 ? reason : "-"),
                                mode,
                                TimeToString(symTime, TIME_DATE|TIME_SECONDS), (int)age);
         // Kunci perubahan TANPA jam/umur tick: keduanya berubah tiap detik dan
         // akan membuat log banjir 1 baris/dtk (insiden 22 Nov).
         stateKey = StringFormat("%s/%s/%s/%s", symbol, status,
                                 (StringLen(reason) > 0 ? reason : "-"), mode);
        }
     }

   // Log ringkas: saat status berubah ATAU tiap InpHeartbeatLogSec (bukti heartbeat
   // tetap jalan walau market tutup, tanpa membanjiri journal).
   if(StringLen(logLine) > 0 &&
      (stateKey != g_hbLogState || (g_hbLogSec > 0 && TimeLocal() - g_hbLogAt >= g_hbLogSec)))
     {
      g_hbLogState = stateKey;
      g_hbLogAt    = TimeLocal();
      Print("LumineEA-Fund2: heartbeat ", logLine, " (ok=", okCount, "/", g_nSlots, ")");
     }
  }

// Fail-safe lama (v5.03): heartbeat minimal satu simbol chart, tanpa status.
void SendPlainHeartbeat()
  {
   string symbol = NormalizeSymbol(Symbol());
   double bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);
   double ask = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
   double spread = (bid > 0 && ask > 0) ? (ask - bid) : 0.0;

   string json = StringFormat("{\"ts\":%I64d,\"symbol\":\"%s\",\"bid\":%s,\"ask\":%s,"
                              "\"spread\":%s,\"ea\":\"v5\"}",
                              (long)TimeGMT(), symbol,
                              DoubleToString(bid, 5), DoubleToString(ask, 5),
                              DoubleToString(spread, 5));
   int res = HttpPostJson("/heartbeat", json, 3000);
   if(res == 200)
     {
      MarkBridgeOk();
      g_lastHeartbeat = TimeLocal();
     }
   else if(res == -1)
     {
      int err = GetLastError();
      if(err == 4014)
         WarnWhitelist();
      else if(err != 0)
         MarkBridgeFail("Heartbeat", err);
     }
   else if(res == 401 || res == 403)
      WarnAuth(res);
   else
      MarkBridgeFail("Heartbeat-http", res);
  }

//+------------------------------------------------------------------+
//| Envelope monotonik ts per slot (t_74b1f18f): ts yang dikirim wajib |
//| strictly increasing. Sumber jam berbeda (tick real = time_msc -    |
//| offset terukur; sintetis = TimeGMT) bisa saling menyusul mundur    |
//| +-1 dtk; validator API menolak tick di bawah high-water mark.      |
//| Clamp ke last+1: harga tetap asli, label waktu hanya bergeser      |
//| <= beberapa ratus ms, urutan antar tick terjaga.                   |
//+------------------------------------------------------------------+
long EnforceMonotonicTs(const int si, const long tsMs)
  {
   if(tsMs > g_slotLastTsMs[si])
     {
      g_slotLastTsMs[si] = tsMs;
      return tsMs;
     }
   g_slotLastTsMs[si] = g_slotLastTsMs[si] + 1;
   return g_slotLastTsMs[si];
  }

//+------------------------------------------------------------------+
//| Capture 1 tick MT5 ke buffer batch slot chart (dipanggil OnTick). |
//| ts = tick.time_msc (jam server broker) dikonversi ke epoch ms     |
//| true UTC (kontrak EA v5). Buffer penuh -> buang tertua           |
//| (PRD 5.1 backpressure: sample likuiditas boleh dibuang,           |
//| event order tidak pernah menunggu tick).                          |
//+------------------------------------------------------------------+
void CaptureTick()
  {
   int si = SlotIndex(NormalizeSymbol(Symbol()));
   if(si < 0)
      return;   // tabel simbol belum siap
   MqlTick t;
   if(!SymbolInfoTick(Symbol(), t))
      return;
   if(t.bid <= 0 || t.ask <= 0)
      return;   // market closed / tick tidak valid

   double spread = t.ask - t.bid;
   long tsMs = (long)t.time_msc - g_brokerOffsetSec * 1000;
   tsMs = EnforceMonotonicTs(si, tsMs);
   string item = StringFormat("{\"ts\":%I64d,\"bid\":%s,\"ask\":%s,\"spread\":%s}",
                              tsMs, DoubleToString(t.bid, 5),
                              DoubleToString(t.ask, 5), DoubleToString(spread, 5));

   if(g_slotCount[si] >= TICK_BUF_MAX)
     {
      // buang tertua (shift kiri 1 slot)
      for(int i = 1; i < TICK_BUF_MAX; i++)
         g_slotItems[si][i - 1] = g_slotItems[si][i];
      g_slotCount[si] = TICK_BUF_MAX - 1;
      g_slotDropped[si]++;
     }
   g_slotItems[si][g_slotCount[si]] = item;
   g_slotCount[si]++;
  }

//+------------------------------------------------------------------+
//| Sampel sintetis 1x/detik per slot saat market idle (tidak ada     |
//| OnTick utk simbol tsb): quote terakhir MT5 masuk pipeline dengan |
//| ts = waktu sekarang sehingga liquidity_samples, parquet, dan     |
//| candle M1 tetap jalan di akhir pekan / market tutup. Slot dengan |
//| tick real tertunda menunda sampel sintetisnya sendiri; buffer    |
//| penuh -> sampel sintetis dibuang.                                |
//+------------------------------------------------------------------+
void CaptureSyntheticTicks()
  {
   for(int si = 0; si < g_nSlots; si++)
     {
      if(g_slotCount[si] > 0)
         continue;   // ada tick real menunggu flush — sintetis skip
      MqlTick t;
      if(!SymbolInfoTick(g_slotBroker[si], t))
         continue;
      if(t.bid <= 0 || t.ask <= 0)
         continue;   // tidak ada quote sama sekali

      double spread = t.ask - t.bid;
      long tsMs = (long)TimeGMT() * 1000 + (long)(GetTickCount64() % 1000);
      tsMs = EnforceMonotonicTs(si, tsMs);
      string item = StringFormat("{\"ts\":%I64d,\"bid\":%s,\"ask\":%s,\"spread\":%s}",
                                 tsMs, DoubleToString(t.bid, 5),
                                 DoubleToString(t.ask, 5), DoubleToString(spread, 5));

      if(g_slotCount[si] >= TICK_BUF_MAX)
         continue;   // penuh — buang sampel sintetis (backpressure)
      g_slotItems[si][g_slotCount[si]] = item;
      g_slotCount[si]++;
     }
  }

//+------------------------------------------------------------------+
//| Flush batch tick -> POST /bridge/tick (per slot simbol).          |
//| Gagal: batch slot dipertahankan (di-flush tick berikutnya), tapi  |
//| dibuang tertua bila buffer slot tejahan (backpressure).           |
//+------------------------------------------------------------------+
void FlushTickBatch()
  {
   for(int si = 0; si < g_nSlots; si++)
     {
      if(g_slotCount[si] <= 0)
         continue;

      string ticks = "[";
      for(int i = 0; i < g_slotCount[si]; i++)
        {
         if(i > 0) ticks += ",";
         ticks += g_slotItems[si][i];
        }
      ticks += "]";

      string json = BuildTickBody(g_slotBase[si], ticks, "");
      int res = HttpPostJson("/tick", json, 3000);
      if(res == 200)
        {
         MarkBridgeOk();
         g_slotCount[si] = 0;
         g_lastFlushMs = GetTickCount();
         g_lastTickSent = TimeLocal();
        }
      else if(res == -1)
        {
         int err = GetLastError();
         if(err == 4014)
            WarnWhitelist();
         else if(err != 0)
            MarkBridgeFail("FlushTickBatch", err);
         // backpressure: sisakan TICK_BUF_MAX/2 tick terbaru (per slot)
         if(g_slotCount[si] > TICK_BUF_MAX / 2)
           {
            int keep = TICK_BUF_MAX / 2;
            for(int i = 0; i < keep; i++)
               g_slotItems[si][i] = g_slotItems[si][g_slotCount[si] - keep + i];
            g_slotDropped[si] += (g_slotCount[si] - keep);
            g_slotCount[si] = keep;
           }
        }
      else if(res == 401 || res == 403)
         WarnAuth(res);
      else
         MarkBridgeFail("FlushTickBatch-http", res);
     }
  }

//+------------------------------------------------------------------+
//| Refresh bars M1 terbaru (120 bar) tiap 30 menit — candles_1m/5m/15m|
//| tetap FRESH walau seed awal sudah selesai. Multi-simbol: semua     |
//| entry g_seedSymbols (payload memakai nama base).                   |
//+------------------------------------------------------------------+
void SeedRecentM1()
  {
   if(g_seedDisabled) return;
   for(int s = 0; s < ArraySize(g_seedSymbols); s++)
     {
      string baseSym = NormalizeSymbol(g_seedSymbols[s]);
      string sym = BrokerSymbol(baseSym);
      MqlRates rates[];
      int got = CopyRates(sym, PERIOD_M1, 0, 120, rates);
      if(got <= 0)
        {
         Print("LumineEA-Fund2: SeedRecentM1 ", baseSym, " CopyRates err=", GetLastError());
         continue;
        }
      // JSON: [{ts, open, high, low, close, volume}...] oldest-first
      string candles = "[";
      for(int i = got - 1; i >= 0; i--)
        {
         if(i != got - 1) candles += ",";
         candles += StringFormat("{\"symbol\":\"%s\",\"timeframe\":\"1m\",\"ts\":\"%s\",\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s,\"volume\":%s}",
            baseSym, CandleTsUtc(rates[i].time),
            DoubleToString(rates[i].open, 2), DoubleToString(rates[i].high, 2),
            DoubleToString(rates[i].low, 2), DoubleToString(rates[i].close, 2),
            DoubleToString(rates[i].tick_volume, 0));
        }
      candles += "]";
      int res = HttpPostJson("/tick", BuildTickBody(baseSym, "", candles), 3000);
      if(res == 200)
         MarkBridgeOk();
      else if(res == -1)
        {
         int err = GetLastError();
         if(err == 4014)
            WarnWhitelist();
         else if(err != 0)
            MarkBridgeFail("SeedRecentM1", err);
        }
      else if(res == 401 || res == 403)
         WarnAuth(res);
      else
         MarkBridgeFail("SeedRecentM1-http", res);
     }
  }

//+------------------------------------------------------------------+
//| Normalize broker symbol → base (B9 multicurrency prefix)          |
//| XAUUSDc (cent) → XAUUSD; XAUUSD.stp / XAUUSD.m / XAUUSDx → XAUUSD |
//+------------------------------------------------------------------+
string NormalizeSymbol(const string raw)
  {
   string s = raw;
   // hapus prefix broker (#BTCUSD → BTCUSD)
   if(StringLen(s) > 0 && StringGetCharacter(s, 0) == '#')
      s = StringSubstr(s, 1);
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
//| Resolver nama simbol: base (API) → nama broker sesungguhnya.      |
//| BTCUSD → #BTCUSD (prefix broker). Fallback: nama base apa adanya  |
//| (OrderSend/CopyRates gagal = fail-closed, tidak ada order salah).  |
//+------------------------------------------------------------------+
int SlotIndex(const string base)
  {
   for(int i = 0; i < g_nSlots; i++)
      if(g_slotBase[i] == base)
         return i;
   return -1;
  }

bool AddSlot(const string base, const string broker)
  {
   if(g_nSlots >= MAX_EA_SYMBOLS)
      return false;
   g_slotBase[g_nSlots] = base;
   g_slotBroker[g_nSlots] = broker;
   g_slotCount[g_nSlots] = 0;
   g_slotDropped[g_nSlots] = 0;
   g_nSlots++;
   return true;
  }

string ResolveBrokerSymbol(const string base)
  {
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string name = SymbolName(i, false);
      if(NormalizeSymbol(name) == base)
        {
         if(!SymbolSelect(name, true))
            Print("LumineEA-Fund2: SymbolSelect(", name, ") gagal err=", GetLastError());
         return name;
        }
     }
   return base;
  }

string BrokerSymbol(const string base)
  {
   int si = SlotIndex(base);
   if(si >= 0)
      return g_slotBroker[si];
   string broker = ResolveBrokerSymbol(base);
   if(AddSlot(base, broker))
      Print("LumineEA-Fund2: symbol map ", base, " -> ", broker);
   return broker;
  }

void InitSymbolTable()
  {
   AddSlot(NormalizeSymbol(Symbol()), Symbol());   // slot 0: simbol chart
   for(int i = 0; i < ArraySize(g_seedSymbols) && g_nSlots < MAX_EA_SYMBOLS; i++)
     {
      string base = NormalizeSymbol(g_seedSymbols[i]);
      if(SlotIndex(base) >= 0)
         continue;
      string broker = ResolveBrokerSymbol(base);
      AddSlot(base, broker);
      Print("LumineEA-Fund2: symbol map ", base, " -> ", broker);
     }
  }

int TotalPendingTicks()
  {
   int n = 0;
   for(int i = 0; i < g_nSlots; i++)
      n += g_slotCount[i];
   return n;
  }

int MaxSlotPending()
  {
   int m = 0;
   for(int i = 0; i < g_nSlots; i++)
      if(g_slotCount[i] > m)
         m = g_slotCount[i];
   return m;
  }

//+------------------------------------------------------------------+
//| Send snapshot open positions + deal 24 jam → POST /positions      |
//| Format backend: {positions:[{ticket, order_id?, symbol, side,     |
//| volume, open_price?, open_time?, sl?, tp?, close_price?,          |
//| close_time?, profit, status}],                                    |
//| deals:[{ticket, position_id, symbol, side, volume, price?,        |
//| profit, time?, entry}]}  (deal 24 jam terakhir, PRD 5.8)          |
//+------------------------------------------------------------------+
void SendPositionsSnapshot()
  {
   string json = "{\"positions\":[";

   int total = PositionsTotal();
   int count = 0;
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;

      string symbol = NormalizeSymbol(PositionGetString(POSITION_SYMBOL));
      long   ptype  = PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl     = PositionGetDouble(POSITION_SL);
      double tp     = PositionGetDouble(POSITION_TP);
      double profit = PositionGetDouble(POSITION_PROFIT);
      datetime time  = (datetime)PositionGetInteger(POSITION_TIME);
      string side = (ptype == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      // order_id dari comment "Lumine2:<order_id>" (diekstrak manual)
      string cmt = PositionGetString(POSITION_COMMENT);
      string oid = "";
      int ci = StringFind(cmt, "Lumine2:");
      if(ci >= 0)
        {
         oid = StringSubstr(cmt, ci + 8);
         int sp = StringFind(oid, " ");   // comment bisa punya suffix broker
         if(sp > 0) oid = StringSubstr(oid, 0, sp);
        }

      if(count > 0) json += ",";
      json += StringFormat(
         "{\"ticket\":%I64d,\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":%.2f,"
         "\"open_price\":%.5f,\"open_time\":\"%s\",\"sl\":%.5f,\"tp\":%.5f,"
         "\"profit\":%.2f,\"status\":\"OPEN\"",
         ticket, symbol, side, volume, open,
         TimeToString(time, TIME_DATE|TIME_SECONDS), sl, tp, profit);
      if(StringLen(oid) > 0)
         json += ",\"order_id\":\"" + oid + "\"";
      json += "}";
      count++;
     }
   json += "]";
   // ── Deal 24 jam terakhir (PRD 5.8): bukti penutupan untuk reconciler ──
   json += ",\"deals\":[";
   int dealCount = 0;
   datetime dealFrom = TimeCurrent() - (datetime)InpDealWindowHours * 3600;
   if(HistorySelect(dealFrom, TimeCurrent() + 60))
     {
      int totalDeals = HistoryDealsTotal();
      int startDeal = (int)MathMax(0, totalDeals - 500);   // cap 500 deal terakhir
      for(int i = startDeal; i < totalDeals; i++)
       {
        ulong dticket = HistoryDealGetTicket(i);
        if(dticket == 0) continue;
        long   dtype  = HistoryDealGetInteger(dticket, DEAL_TYPE);
        if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) continue; // buang balance/credit
        long   entry  = HistoryDealGetInteger(dticket, DEAL_ENTRY);
        string dside  = (dtype == DEAL_TYPE_BUY) ? "BUY" : "SELL";
        string dent   = (entry == DEAL_ENTRY_IN) ? "IN"
                        : (entry == DEAL_ENTRY_INOUT ? "INOUT" : "OUT");
        if(dealCount > 0) json += ",";
        json += StringFormat(
           "{\"ticket\":%I64d,\"position_id\":%I64d,\"symbol\":\"%s\",\"side\":\"%s\","
           "\"volume\":%.2f,\"price\":%.5f,\"profit\":%.2f,\"time\":\"%s\",\"entry\":\"%s\"}",
           dticket,
           HistoryDealGetInteger(dticket, DEAL_POSITION_ID),
           NormalizeSymbol(HistoryDealGetString(dticket, DEAL_SYMBOL)),
           dside,
           HistoryDealGetDouble(dticket, DEAL_VOLUME),
           HistoryDealGetDouble(dticket, DEAL_PRICE),
           HistoryDealGetDouble(dticket, DEAL_PROFIT),
           TimeToString((datetime)HistoryDealGetInteger(dticket, DEAL_TIME),
                        TIME_DATE|TIME_SECONDS),
           dent);
        dealCount++;
       }
     }
   json += "]}";
   // Snapshot kosong tetap dikirim (positions:[]) — backend otomatis
   // men-CLOSED posisi yang hilang dari snapshot.

   int res = HttpPostJson("/positions", json, 3000);
   if(res == 200)
      MarkBridgeOk();
   else if(res == -1)
     {
      int err = GetLastError();
      if(err == 4014)
         WarnWhitelist();
      else if(err != 0)
         MarkBridgeFail("Positions", err);
     }
   else if(res == 401 || res == 403)
      WarnAuth(res);
   else
      MarkBridgeFail("Positions-http", res);
  }

//+------------------------------------------------------------------+
//| Poll bridge untuk command: GET /poll?timeout_s=0 (fast-poll)      |
//| Response: {command_id, order_id, symbol, side, volume, sl, tp}    |
//| atau null (204-style, tidak ada command)                          |
//+------------------------------------------------------------------+
// Transport GET gagal sementara jalur lain (heartbeat/tick/positions) hidup:
// jangan flip g_bridgeDown — itu memicu pasangan UNREACHABLE/RECOVERED tiap
// siklus = 15 ribu baris log sehari (insiden 22 Nov) tanpa menambah informasi.
void PollDegraded(const int res, const int err)
  {
   static datetime lastLog = 0;
   if(TimeLocal() - lastLog >= 60)
     {
      lastLog = TimeLocal();
      Print("LumineEA-Fund2: poll GET gagal res=", res, " err=", err,
            " — heartbeat/tick tetap jalan, polling diteruskan (log 60 dtk)");
     }
  }

void PollCommands()
  {
   // Server memaksa long-poll minimal 5 dtk (BRIDGE_POLL_MIN_S di bridge.py;
   // timeout_s=0 tetap di-clamp ke 5.0). Karena WebRequest MQL5 sinkron, polling
   // lebih cepat dari 5 dtk pasti timeout (res=1003, err=5203) dan — lebih
   // buruk — command yang sudah diberikan ke socket yang tutup dianggap
   // DELIVERED oleh server sehingga HILANG. Maka: interval >= 5 dtk dan timeout
   // HTTP > floor server.
   static uint   lastPollMs = 0;
   uint nowMs = GetTickCount();
   if(lastPollMs != 0 && (int)(nowMs - lastPollMs) < MathMax(1, InpPollSec) * 1000)
      return;
   lastPollMs = nowMs;

   string pathQuery = "/poll?timeout_s=0&v=510";
   int res = HttpGetJson(pathQuery, MathMax(5500, InpPollHttpMs));

   if(res == 200)
     {
      MarkBridgeOk();
      string json = CharArrayToString(g_pollResult, 0, WHOLE_ARRAY, CP_UTF8);
      if(StringLen(json) > 2 && StringFind(json, "null") != 0)
        {
         string cmd = UnwrapCommand(json);
         if(StringLen(cmd) > 0)
            ProcessCommand(cmd);
        }
     }
   else if(res == 204 || res == 408)
     {
      MarkBridgeOk();   // no command / timeout — normal
     }
   else if(res == -1)
     {
      int err = GetLastError();
      if(err == 4014)
         WarnWhitelist();
      else if(err == 5203 || err == 0)
         PollDegraded(res, err);      // transport GET gagal, bukan bridge mati
      else
         MarkBridgeFail("PollCommands", err);
     }
   else if(res == 401 || res == 403)
      WarnAuth(res);
   else if(res == 1003)
      PollDegraded(res, GetLastError());   // WebRequest Wine: 1003 + err 5203
   else
      MarkBridgeFail("PollCommands-http", res);
  }

//+------------------------------------------------------------------+
//| Terima command langsung ATAU terbungkus {"command":{...}}         |
//+------------------------------------------------------------------+
string UnwrapCommand(const string json)
  {
   // Sudah command langsung (punya command_id di level atas)?
   if(StringLen(ExtractJsonString(json, "command_id")) > 0)
      return json;

   // Cari pembungkus "command": { ... } (match brace berlapis)
   int key = StringFind(json, "\"command\"");
   if(key == -1) return "";   // bukan command (null/heartbeat)
   int start = StringFind(json, "{", key);
   if(start == -1) return "";
   int depth = 0;
   int n = StringLen(json);
   for(int i = start; i < n; i++)
     {
      ushort c = StringGetCharacter(json, i);
      if(c == '{')
         depth++;
      else if(c == '}')
        {
         depth--;
         if(depth == 0)
            return StringSubstr(json, start, i - start + 1);
        }
     }
   return "";
  }

//+------------------------------------------------------------------+
//| Process command JSON dari bridge (contract final, tanpa action):  |
//| {command_id, order_id, symbol, side, volume, sl, tp}             |
//| Tanpa field ticket → OPEN order baru. (Backend P1 hanya kirim    |
//| OPEN; CLOSE/MODIFY menyusul di fase berikutnya bila ditambah.)   |
//+------------------------------------------------------------------+
void ProcessCommand(const string json)
  {
   string id = ExtractJsonString(json, "command_id");
   if(StringLen(id) == 0) id = ExtractJsonString(json, "id");
   string action = ExtractJsonString(json, "action");
   string symbol = ExtractJsonString(json, "symbol");
   string side   = ExtractJsonString(json, "side");
   StringToUpper(side);
   double lots = ExtractJsonDouble(json, "volume");
   double sl = ExtractJsonDouble(json, "sl");
   double tp = ExtractJsonDouble(json, "tp");
   string ticketStr = ExtractJsonString(json, "ticket");

   g_orderId = ExtractJsonString(json, "order_id");
   if(StringLen(g_orderId) == 0) g_orderId = id;

   if(StringLen(id) == 0)
      return;   // empty command — silent

   // Infer action: ticket ada → CLOSE/MODIFY; side kosong → tidak valid;
   // default OPEN (contract backend P1: hanya kirim order baru).
   if(StringLen(action) == 0)
     {
      if(StringLen(ticketStr) > 0)
         action = "CLOSE";
      else if(StringLen(side) > 0)
         action = "OPEN";
      else
         return;
     }

   Print("LumineEA-Fund2 command received: id=", id, " action=", action,
         " symbol=", symbol, " side=", side, " vol=", lots);

   if(action == "OPEN")
     {
      if(StringLen(symbol) == 0) symbol = Symbol();
      // nama base (API) → simbol broker sesungguhnya (mis. BTCUSD → #BTCUSD)
      string brokerSym = BrokerSymbol(NormalizeSymbol(symbol));
      ExecuteOpen(id, brokerSym, side, lots, sl, tp);
     }
   else if(action == "CLOSE")
     {
      ulong ticket = (ulong)StringToInteger(ticketStr);
      ExecuteClose(id, ticket);
     }
   else if(action == "MODIFY" || action == "MODIFY_SL")
     {
      ulong ticket = (ulong)StringToInteger(ticketStr);
      ExecuteModify(id, ticket, sl, tp);
     }
   else
     {
      QueueResult(BuildResultJson(id, "FAILED", 0, "Unknown action: " + action, 0, 0));
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
   req.magic        = 20261121;          // fund2 (v1: 20260814)
   req.comment      = "Lumine2:" + id;
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
            HandleOrderFail(id, symbol, res.retcode, lots, "OPEN");
            return;
           }
        }
      else
        {
         HandleOrderFail(id, symbol, res.retcode, lots, "OPEN");
         return;
        }
     }

   if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL)
      QueueResult(BuildResultJson(id, "FILLED", (long)res.order, "", res.price, lots));
   else if(res.retcode == TRADE_RETCODE_PLACED)
      QueueResult(BuildResultJson(id, "FILLED", (long)res.order, "", res.price, lots));
   else
      HandleOrderFail(id, symbol, res.retcode, lots, "OPEN");
  }

//+------------------------------------------------------------------+
//| Execute CLOSE order                                               |
//+------------------------------------------------------------------+
void ExecuteClose(const string id, ulong ticket)
  {
   if(!PositionSelectByTicket(ticket))
     {
      QueueResult(BuildResultJson(id, "FAILED", 0, "Position not found: " + IntegerToString(ticket), 0, 0));
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
   req.magic        = 20261121;
   req.comment      = "Lumine2:CLOSE:" + id;
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
            HandleOrderFail(id, symbol, res.retcode, volume, "CLOSE");
            return;
           }
        }
      else
        {
         HandleOrderFail(id, symbol, res.retcode, volume, "CLOSE");
         return;
        }
     }

   if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_DONE_PARTIAL)
      QueueResult(BuildResultJson(id, "FILLED", (long)res.order, "", res.price, volume));
   else
      HandleOrderFail(id, symbol, res.retcode, volume, "CLOSE");
  }

//+------------------------------------------------------------------+
//| Execute MODIFY order (SL/TP)                                      |
//+------------------------------------------------------------------+
void ExecuteModify(const string id, ulong ticket, double sl, double tp)
  {
   if(!PositionSelectByTicket(ticket))
     {
      QueueResult(BuildResultJson(id, "FAILED", 0, "Position not found: " + IntegerToString(ticket), 0, 0));
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
      QueueResult(BuildResultJson(id, "FILLED", (long)ticket, "", 0, 0));
   else
      HandleOrderFail(id, PositionGetString(POSITION_SYMBOL), res.retcode, 0, "MODIFY");
  }

//+------------------------------------------------------------------+
//| v5.10 — kegagalan OrderSend terstruktur.                          |
//| retcode 10018 (TRADE_RETCODE_MARKET_CLOSED): TIDAK di-retry       |
//| (retry hanya akan gagal lagi dan membanjiri broker), result       |
//| dikirim ke bridge {status FAILED, retcode 10018, reason "market   |
//| closed"}, log SEKALI per kejadian (dedup 60 dtk per simbol untuk  |
//| command yang dikirim ulang backend), dan slot ditandai CLOSED/    |
//| 'broker' di heartbeat selama InpClosedHoldSec.                    |
//+------------------------------------------------------------------+
void HandleOrderFail(const string id, const string symbol, const uint retcode,
                     const double volume, const string kind)
  {
   int si = SlotIndex(NormalizeSymbol(symbol));

   if(retcode == 10018)   // TRADE_RETCODE_MARKET_CLOSED
     {
      datetime now = TimeLocal();
      if(si >= 0)
        {
         g_slotClosedAt[si] = now;
         if(g_slotClosedLog[si] != 0 && now - g_slotClosedLog[si] < 60)
           {
            QueueResult(BuildClosedResultJson(id, retcode, volume, kind));
            return;                       // log sudah ada untuk kejadian ini
           }
         g_slotClosedLog[si] = now;
        }
      Print("LumineEA-Fund2: ", kind, " ", id, " DITOLAK market closed (retcode=10018) ",
            symbol, " — TIDAK di-retry; heartbeat melaporkan CLOSED/broker");
      QueueResult(BuildClosedResultJson(id, retcode, volume, kind));
      return;
     }

   // Retcode lain: kontrak lama dipertahankan (alasan teks sama seperti v5.03)
   // supaya konsumen backend yang mem-parse string tidak berubah perilaku.
   string msg = "OrderSend failed retcode=" + IntegerToString((int)retcode);
   if(kind == "CLOSE")
      msg = "OrderSend CLOSE failed retcode=" + IntegerToString((int)retcode);
   Print("LumineEA-Fund2: ", kind, " ", id, " gagal retcode=", retcode,
         " (", RetcodeStr(retcode), ") ", symbol);
   QueueResult(BuildResultJson(id, "FAILED", 0, msg, 0, volume));
  }

// Result terstruktur untuk order yang ditolak market closed (10018).
string BuildClosedResultJson(const string id, const uint retcode, const double volume,
                             const string kind)
  {
   return StringFormat("{\"command_id\":\"%s\",\"status\":\"FAILED\",\"ticket\":0,"
                       "\"price\":0.0,\"profit\":0.0,\"reason\":\"market closed\","
                       "\"retcode\":%s,\"error\":\"market_closed\","
                       "\"action\":\"%s\",\"volume\":%.2f}",
                       id, IntegerToString((int)retcode), kind, volume);
  }

//+------------------------------------------------------------------+
//| Build result JSON (contract backend):                             |
//| {command_id, status: FILLED|FAILED, ticket, price, profit, reason}|
//| Idempotent by command_id di backend.                              |
//+------------------------------------------------------------------+
string   BuildResultJson(const string id, const string status, long ticket,
                       const string error, double fillPrice, double fillVolume)
  {
   return StringFormat("{\"command_id\":\"%s\",\"status\":\"%s\",\"ticket\":%I64d,"
                       "\"price\":%.5f,\"profit\":0.0,\"reason\":\"%s\"}",
                       id, status, ticket, fillPrice, EscapeJson(error));
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
