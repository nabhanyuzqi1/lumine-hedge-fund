//+------------------------------------------------------------------+
//| LumineEA.mq5 — HTTP bridge agent untuk Lumine Hedge Fund (v2)    |
//| Transport: HTTP polling (bypass demo account socket block)       |
//| Redis HTTP Proxy: GET /commands?timeout=30 → BRPOP mt5:commands  |
//|                   POST /results → PUBLISH mt5:results             |
//|                   POST /ticks → LPUSH mt5:ticks                   |
//+------------------------------------------------------------------+
#property copyright "Lumine"
#property version   "2.00"
#property strict

input string  InpProxyURL = "http://lumine.biz.id/mt5-proxy";  // Redis HTTP proxy URL (via Caddy)
input bool    InpSeedHistory = false;   // Seed history bars (CopyRates) sekali saat OnInit

// ── Global State ──────────────────────────────────────────────────────────
string g_proxyURL;
string g_orderId;              // order_id dari command aktif (untuk result sync)
datetime g_lastTickTime = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_proxyURL = InpProxyURL;
   Print("LumineEA starting (HTTP transport): proxy=", g_proxyURL);
   
   // WebRequest whitelist: add proxy URL to Tools → Options → Expert Advisors
   // (MT5 tidak punya API untuk cek whitelist programmatically)
   
   Print("LumineEA ready (HTTP polling mode)");
   
   // Seed history bars (sekali; CopyRates → POST /seed/bars per chunk)
   if(InpSeedHistory)
      SeedHistory();
   
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   Print("LumineEA stopping: reason=", reason);
  }

//+------------------------------------------------------------------+
//| Seed history bars: CopyRates → POST /seed/bars (chunk 1000)      |
//+------------------------------------------------------------------+
void SeedHistory()
  {
   string symbols[] = {"XAUUSD"};
   ENUM_TIMEFRAMES tfs[] = {PERIOD_M1, PERIOD_H1, PERIOD_D1};
   string tfNames[] = {"1m", "1h", "1d"};
   
   for(int s = 0; s < ArraySize(symbols); s++)
     {
      for(int t = 0; t < ArraySize(tfs); t++)
        {
         MqlRates rates[];
         int got = CopyRates(symbols[s], tfs[t], 0, 5000, rates);
         if(got <= 0)
           {
            Print("SeedHistory: CopyRates ", symbols[s], " ", tfNames[t], " gagal err=", GetLastError());
            continue;
           }
         ArraySetAsSeries(rates, false);
         for(int start = 0; start < got; start += 1000)
           {
            int n = MathMin(1000, got - start);
            string json = "{\"symbol\":\"" + symbols[s] + "\",\"timeframe\":\"" + tfNames[t] + "\",\"bars\":[";
            for(int i = 0; i < n; i++)
              {
               MqlRates r = rates[start + i];
               if(i > 0) json += ",";
               json += StringFormat("{\"ts\":%d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.2f}",
                                    (long)r.time, r.open, r.high, r.low, r.close, r.volume);
              }
            json += "]}";
            HttpPostJson("/seed/bars", json);
           }
         Print("SeedHistory: ", symbols[s], " ", tfNames[t], " -> ", got, " bars");
        }
     }
   Print("SeedHistory selesai");
  }

//+------------------------------------------------------------------+
//| HTTP POST JSON helper (WebRequest)                                |
//+------------------------------------------------------------------+
int HttpPostJson(const string path, const string json)
  {
   char data[];
   StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);  // tanpa null terminator
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string url = g_proxyURL + path;
   int res = WebRequest("POST", url, headers, 5000, data, result, headers);
   if(res != 200)
      Print("HttpPostJson ", path, " gagal http=", res, " err=", GetLastError());
   return res;
  }

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
  {
   // Send tick to Redis (throttle: 1 per second)
   datetime now = TimeCurrent();
   if(now > g_lastTickTime)
     {
      g_lastTickTime = now;
      SendTick();
     }
   
   // Poll for commands (non-blocking with timeout=1)
   PollCommands();
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
      string json = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
      if(StringLen(json) > 2)  // Not empty JSON
        {
         ProcessCommand(json);
        }
     }
   else if(res == 204)
     {
      // No command available (timeout expired) — normal, not an error
     }
   else if(res == -1)
     {
      int err = GetLastError();
      if(err != 0)  // Suppress repeat errors
        {
         Print("PollCommands WebRequest failed: error=", err, " (Add proxy URL to WebRequest whitelist)");
        }
     }
  }

//+------------------------------------------------------------------+
//| Send tick data to Redis via HTTP                                 |
//+------------------------------------------------------------------+
void SendTick()
  {
   string symbol = Symbol();
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   datetime timestamp = TimeCurrent();
   
   string json = StringFormat("{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"timestamp\":%d}",
                              symbol, bid, ask, timestamp);
   
   char data[];
   StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);  // Remove null terminator
   
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string url = g_proxyURL + "/ticks";
   
   int res = WebRequest("POST", url, headers, 2000, data, result, headers);
   
   if(res != 200 && res != -1)
     {
      Print("SendTick failed: http_code=", res);
     }
  }

//+------------------------------------------------------------------+
//| Process command JSON from Redis                                   |
//+------------------------------------------------------------------+
void ProcessCommand(const string json)
  {
   // Parse JSON manual (MQL5 tidak punya JSON parser built-in).
   // Field dari bridge (mt5_bridge.CommandMessage): command_id, order_id,
   // action, symbol, volume, order_type. Support juga format legacy
   // (id, lots, side) agar robust terhadap kedua payload.
   string id = ExtractJsonString(json, "command_id");
   if(StringLen(id) == 0) id = ExtractJsonString(json, "id");
   string action = ExtractJsonString(json, "action");
   
   // Simpan order_id untuk result sync (bridge ResultMessage.order_id)
   g_orderId = ExtractJsonString(json, "order_id");
   if(StringLen(g_orderId) == 0) g_orderId = id;
   
   // Suppress log saat command kosong (queue timeout)
   if(StringLen(id) == 0 || StringLen(action) == 0)
      return;  // Skip empty command, tidak perlu log
   
   Print("Command received: id=", id, " action=", action);
   
   if(action == "OPEN")
     {
      string symbol = ExtractJsonString(json, "symbol");
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
      string ticket_str = ExtractJsonString(json, "ticket");
      ulong ticket = (ulong)StringToInteger(ticket_str);
      
      ExecuteClose(id, ticket);
     }
   else if(action == "MODIFY")
     {
      string ticket_str = ExtractJsonString(json, "ticket");
      ulong ticket = (ulong)StringToInteger(ticket_str);
      double sl = ExtractJsonDouble(json, "sl");
      double tp = ExtractJsonDouble(json, "tp");
      
      ExecuteModify(id, ticket, sl, tp);
     }
   else
     {
      SendResult(id, "ERROR", 0, "Unknown action: " + action, 0);
     }
  }

//+------------------------------------------------------------------+
//| Execute OPEN order                                                |
//+------------------------------------------------------------------+
void ExecuteOpen(const string id, const string symbol, const string side, 
                 double lots, double sl, double tp)
  {
   ENUM_ORDER_TYPE orderType = (side == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double price = (side == "BUY") ? SymbolInfoDouble(symbol, SYMBOL_ASK) : SymbolInfoDouble(symbol, SYMBOL_BID);
   
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   
   req.action = TRADE_ACTION_DEAL;
   req.symbol = symbol;
   req.volume = lots;
   req.type = orderType;
   req.price = price;
   req.sl = sl;
   req.tp = tp;
   req.deviation = 20;
   req.magic = 20260814;
   req.comment = "Lumine:" + id;
   req.type_filling = ORDER_FILLING_FOK;
   
   if(OrderSend(req, res))
     {
      if(res.retcode == TRADE_RETCODE_DONE)
        {
         SendResult(id, "FILLED", (long)res.order, "", res.price, lots);
        }
      else
        {
         SendResult(id, "REJECTED", 0, RetcodeStr(res.retcode), 0);
        }
     }
   else
     {
      SendResult(id, "ERROR", 0, "OrderSend failed: retcode=" + IntegerToString(res.retcode), 0);
     }
  }

//+------------------------------------------------------------------+
//| Execute CLOSE order                                               |
//+------------------------------------------------------------------+
void ExecuteClose(const string id, ulong ticket)
  {
   if(!PositionSelectByTicket(ticket))
     {
      SendResult(id, "ERROR", 0, "Position not found: " + IntegerToString(ticket), 0);
      return;
     }
   
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   
   req.action = TRADE_ACTION_DEAL;
   req.position = ticket;
   req.symbol = PositionGetString(POSITION_SYMBOL);
   req.volume = PositionGetDouble(POSITION_VOLUME);
   req.type = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.price = (req.type == ORDER_TYPE_SELL) ? SymbolInfoDouble(req.symbol, SYMBOL_BID) : SymbolInfoDouble(req.symbol, SYMBOL_ASK);
   req.deviation = 20;
   req.magic = 20260814;
   req.comment = "Lumine:CLOSE:" + id;
   req.type_filling = ORDER_FILLING_FOK;
   
   if(OrderSend(req, res))
     {
      if(res.retcode == TRADE_RETCODE_DONE)
        {
         SendResult(id, "CLOSED", (long)res.order, "", res.price, PositionGetDouble(POSITION_VOLUME));
        }
      else
        {
         SendResult(id, "REJECTED", 0, RetcodeStr(res.retcode), 0);
        }
     }
   else
     {
      SendResult(id, "ERROR", 0, "OrderSend CLOSE failed: retcode=" + IntegerToString(res.retcode), 0);
     }
  }

//+------------------------------------------------------------------+
//| Execute MODIFY order                                              |
//+------------------------------------------------------------------+
void ExecuteModify(const string id, ulong ticket, double sl, double tp)
  {
   if(!PositionSelectByTicket(ticket))
     {
      SendResult(id, "ERROR", 0, "Position not found: " + IntegerToString(ticket), 0);
      return;
     }
   
   MqlTradeRequest req = {};
   MqlTradeResult res = {};
   
   req.action = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol = PositionGetString(POSITION_SYMBOL);
   req.sl = sl;
   req.tp = tp;
   
   if(OrderSend(req, res))
     {
      if(res.retcode == TRADE_RETCODE_DONE)
        {
         SendResult(id, "MODIFIED", (long)ticket, "", 0);
        }
      else
        {
         SendResult(id, "REJECTED", 0, RetcodeStr(res.retcode), 0);
        }
     }
   else
     {
      SendResult(id, "ERROR", 0, "OrderSend MODIFY failed: retcode=" + IntegerToString(res.retcode), 0);
     }
  }

//+------------------------------------------------------------------+
//| Send result to Redis via HTTP                                     |
//+------------------------------------------------------------------+
void SendResult(const string id, const string status, long ticket, 
                const string error, double fillPrice, double fillVolume = 0)
  {
   string json = StringFormat("{\"id\":\"%s\",\"order_id\":\"%s\",\"status\":\"%s\",\"ticket\":%d,\"error\":\"%s\",\"fill_price\":%.5f,\"fill_volume\":%.5f}",
                              id, g_orderId, status, ticket, EscapeJson(error), fillPrice, fillVolume);
   
   char data[];
   StringToCharArray(json, data, 0, WHOLE_ARRAY, CP_UTF8);
   ArrayResize(data, ArraySize(data) - 1);
   
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string url = g_proxyURL + "/results";
   
   int res = WebRequest("POST", url, headers, 2000, data, result, headers);
   
   if(res != 200)
     {
      Print("SendResult failed: http_code=", res, " json=", json);
     }
  }

//+------------------------------------------------------------------+
//| Helper: Extract string from JSON (simple parser)                 |
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
//| Helper: Extract double from JSON                                 |
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
//| Helper: Escape JSON string                                       |
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
//| Helper: Retcode to string (simple map)                           |
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
      default: return "UNKNOWN_" + IntegerToString(retcode);
     }
  }
//+------------------------------------------------------------------+