//+------------------------------------------------------------------+
//| LumineEA.mq5 — Redis bridge agent untuk Lumine Hedge Fund        |
//|                                                                  |
//| Transport: Redis (raw TCP via MQL5 Socket*)                      |
//|   - BRPOP  mt5:commands  → eksekusi order (OPEN/CLOSE/MODIFY)    |
//|   - PUBLISH mt5:results  → hasil eksekusi (ResultMessage JSON)    |
//|   - LPUSH  mt5:ticks     → feed harga real (bid/ask/last)         |
//|                                                                  |
//| Protokol sinkron dengan backend/src/lumine/trading/mt5_bridge.py |
//| (CommandMessage / ResultMessage).                                |
//+------------------------------------------------------------------+
#property strict
#property description "Lumine Redis bridge: execute orders from mt5:commands, publish results + ticks"

input string  InpRedisHost = "172.18.0.3";     // Redis host (IP hardcoded bypass DNS)
input int     InpRedisPort = 6379;              // Redis port
input bool    InpPublishTicks = true;        // Publish ticks ke mt5:ticks
input int     InpCommandTimeoutMs = 60000;   // BRPOP timeout per loop

// Redis channels (harus match mt5_bridge.py)
#define CMD_QUEUE   "mt5:commands"
#define RES_CHANNEL "mt5:results"
#define TICK_QUEUE  "mt5:ticks"

int    g_socket   = INVALID_HANDLE;
bool   g_connected = false;
double g_lastBid  = 0.0;
double g_lastAsk  = 0.0;
ulong  g_lastTickMs = 0;

//+------------------------------------------------------------------+
//| JSON field extraction (minimal, cukup untuk CommandMessage)      |
//+------------------------------------------------------------------+
string JsonGetString(const string json, const string key)
  {
   string pattern = "\"" + key + "\"";
   int pos = StringFind(json, pattern);
   if(pos < 0)
      return "";
   int colon = StringFind(json, ":", pos + StringLen(pattern));
   if(colon < 0)
      return "";
   int start = StringFind(json, "\"", colon + 1);
   if(start < 0)
      return "";
   int end = StringFind(json, "\"", start + 1);
   if(end < 0)
      return "";
   return StringSubstr(json, start + 1, end - start - 1);
  }

double JsonGetDouble(const string json, const string key)
  {
   string pattern = "\"" + key + "\"";
   int pos = StringFind(json, pattern);
   if(pos < 0)
      return 0.0;
   int colon = StringFind(json, ":", pos + StringLen(pattern));
   if(colon < 0)
      return 0.0;
   int start = colon + 1;
   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' ' ||
         StringGetCharacter(json, start) == '\t'))
      start++;
   if(start >= StringLen(json))
      return 0.0;
   if(StringGetCharacter(json, start) == 'n')   // null
      return 0.0;
   int end = start;
   while(end < StringLen(json))
     {
      ushort c = StringGetCharacter(json, end);
      if(c == ',' || c == '}' || c == ' ')
         break;
      end++;
     }
   string num = StringSubstr(json, start, end - start);
   if(num == "")
      return 0.0;
   return StringToDouble(num);
  }

//+------------------------------------------------------------------+
//| Redis protocol helpers                                           |
//+------------------------------------------------------------------+
bool RedisSend(const string cmd)
  {
   if(g_socket == INVALID_HANDLE)
      return false;
   uchar data[];
   StringToCharArray(cmd, data, 0, StringLen(cmd), CP_UTF8);
   int sent = SocketSend(g_socket, data, ArraySize(data));
   return sent > 0;
  }

// Baca sampai CRLF. Return false jika timeout/error.
bool RedisReadLine(string &out, const int timeoutMs)
  {
   out = "";
   ulong start = GetTickCount64();
   while(GetTickCount64() - start < (ulong)timeoutMs)
     {
      uchar buf[1];
      uint available = SocketIsReadable(g_socket);
      if(available > 0)
        {
         uint n = SocketRead(g_socket, buf, 1, 500);
         if(n == 1)
           {
            out += CharToString(buf[0]);
            if(StringLen(out) >= 2 && StringSubstr(out, StringLen(out) - 2) == "\r\n")
               return true;
           }
        }
      Sleep(5);
     }
   return false;
  }

// Baca N byte (untuk bulk string Redis $<len>\r\n<payload>\r\n)
bool RedisReadBytes(const int n, string &out)
  {
   out = "";
   ulong start = GetTickCount64();
   while(StringLen(out) < n && GetTickCount64() - start < 5000)
     {
      uchar buf[256];
      uint available = SocketIsReadable(g_socket);
      if(available > 0)
        {
         int want = MathMin(256, n - StringLen(out));
         uint got = SocketRead(g_socket, buf, want, 500);
         if(got > 0)
            out += CharArrayToString(buf, 0, (int)got, CP_UTF8);
        }
      Sleep(5);
     }
   return StringLen(out) >= n;
  }

bool RedisConnect()
  {
   if(g_socket != INVALID_HANDLE)
      SocketClose(g_socket);
   g_socket = SocketCreate();
   if(g_socket == INVALID_HANDLE)
      return false;
   if(!SocketConnect(g_socket, InpRedisHost, InpRedisPort, 5000))
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
      return false;
     }
   g_connected = true;
   return true;
  }

// BRPOP mt5:commands 0 → payload atau empty string jika error/timeout.
string RedisBRPop(const int timeoutMs)
  {
   string cmd = "BRPOP " + CMD_QUEUE + " 0\r\n";
   if(!RedisSend(cmd))
      return "";
   string line;
   if(!RedisReadLine(line, timeoutMs))
      return "";
   // Response: *2\r\n$13\r\nmt5:commands\r\n$<len>\r\n<payload>\r\n
   if(StringGetCharacter(line, 0) == '*')
     {
      // skip array header line (sudah dibaca), baca $13 + key
      string l2;
      if(!RedisReadLine(l2, timeoutMs)) return "";
      if(StringGetCharacter(l2, 0) == '$')
        {
         int keyLen = (int)StringToInteger(StringSubstr(l2, 1));
         string key;
         if(!RedisReadBytes(keyLen + 2, key)) return "";
         string l3;
         if(!RedisReadLine(l3, timeoutMs)) return "";
         if(StringGetCharacter(l3, 0) == '$')
           {
            int payloadLen = (int)StringToInteger(StringSubstr(l3, 1));
            string payload;
            if(!RedisReadBytes(payloadLen + 2, payload)) return "";
            return StringSubstr(payload, 0, payloadLen);
           }
        }
     }
   return "";
  }

bool RedisPublish(const string channel, const string message)
  {
   string cmd = "PUBLISH " + channel + " " + IntegerToString(StringLen(message)) + "\r\n" + message + "\r\n";
   return RedisSend(cmd);
  }

bool RedisLPush(const string queue, const string message)
  {
   string cmd = "LPUSH " + queue + " " + IntegerToString(StringLen(message)) + "\r\n" + message + "\r\n";
   return RedisSend(cmd);
  }

//+------------------------------------------------------------------+
//| Order execution                                                  |
//+------------------------------------------------------------------+
string ExecuteCommand(const string payload)
  {
   string commandId  = JsonGetString(payload, "command_id");
   string orderId    = JsonGetString(payload, "order_id");
   string action     = JsonGetString(payload, "action");
   string symbol     = JsonGetString(payload, "symbol");
   string orderType  = JsonGetString(payload, "order_type");
   double volume     = JsonGetDouble(payload, "volume");
   double stopLoss   = JsonGetDouble(payload, "stop_loss");
   double takeProfit = JsonGetDouble(payload, "take_profit");

   MqlTradeRequest req;
   MqlTradeResult  res;
   ZeroMemory(req);
   ZeroMemory(res);

   req.symbol   = symbol;
   req.volume   = volume;
   req.sl       = stopLoss  > 0.0 ? stopLoss : 0.0;
   req.tp       = takeProfit > 0.0 ? takeProfit : 0.0;
   req.comment  = "LUMINE:" + orderId;
   req.deviation = 20;

   int status = "REJECTED";
   long ticket = 0;
   double fillPrice = 0.0;
   double fillVolume = 0.0;
   int errCode = 0;
   string errMsg = "";

   if(action == "OPEN")
     {
      req.action = TRADE_ACTION_DEAL;
      req.type   = (orderType == "SELL") ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.price  = (req.type == ORDER_TYPE_BUY)
                   ? SymbolInfoDouble(symbol, SYMBOL_ASK)
                   : SymbolInfoDouble(symbol, SYMBOL_BID);
     }
   else if(action == "CLOSE")
     {
      // order_id = posisi yang ditutup; cari posisi dengan komentar LUMINE:orderId
      req.action = TRADE_ACTION_DEAL;
      req.position = FindPositionTicket(orderId);
      req.type = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.price = (req.type == ORDER_TYPE_SELL)
                  ? SymbolInfoDouble(symbol, SYMBOL_BID)
                  : SymbolInfoDouble(symbol, SYMBOL_ASK);
     }
   else if(action == "MODIFY")
     {
      req.action = TRADE_ACTION_SLTP;
      req.position = FindPositionTicket(orderId);
     }
   else
     {
      errMsg = "unknown action: " + action;
      errCode = -1;
     }

   if(errCode == 0 && OrderSend(req, res))
     {
      if(res.retcode == TRADE_RETCODE_DONE || res.retcode == TRADE_RETCODE_PLACED)
        {
         status = "FILLED";
         ticket = res.order;
         fillPrice = res.price;
         fillVolume = res.volume;
        }
      else
        {
         status = "REJECTED";
         errCode = (int)res.retcode;
         errMsg = RetcodeStr(res.retcode);
        }
     }
   else
     {
      status = "ERROR";
      errCode = (int)res.retcode;
      errMsg = res.retcode == 0 ? "OrderSend failed" : RetcodeStr(res.retcode);
     }

   string result = StringFormat(
      "{\"command_id\":\"%s\",\"order_id\":\"%s\",\"ticket\":%I64d,\"status\":\"%s\","
      "\"fill_price\":%.5f,\"fill_volume\":%.2f,\"error_code\":%d,\"error_message\":\"%s\","
      "\"timestamp\":\"%s\"}",
      commandId, orderId, ticket, status, fillPrice, fillVolume, errCode,
      EscapeJson(errMsg), TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));

   RedisPublish(RES_CHANNEL, result);
   return result;
  }

long FindPositionTicket(const string orderId)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionSelectByTicket(ticket))
        {
         string comment = PositionGetString(POSITION_COMMENT);
         if(StringFind(comment, "LUMINE:" + orderId) >= 0)
            return (long)ticket;
        }
     }
   return 0;
  }

string EscapeJson(const string s)
  {
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "\\\"");
   return r;
  }

// MQL5 tidak punya retcode-to-string built-in — map sebagian, sisanya numerik.
string RetcodeStr(const uint retcode)
  {
   switch(retcode)
     {
      case TRADE_RETCODE_DONE:        return "DONE";
      case TRADE_RETCODE_REJECT:      return "REJECT";
      case TRADE_RETCODE_INVALID_PRICE: return "INVALID_PRICE";
      case TRADE_RETCODE_INVALID_STOPS: return "INVALID_STOPS";
      case TRADE_RETCODE_NO_MONEY:    return "NO_MONEY";
      case TRADE_RETCODE_MARKET_CLOSED: return "MARKET_CLOSED";
      case TRADE_RETCODE_TIMEOUT:     return "TIMEOUT";
      default:                        return "RETCODE_" + IntegerToString(retcode);
     }
  }

//+------------------------------------------------------------------+
//| Publish tick ke mt5:ticks (throttle 200ms)                       |
//+------------------------------------------------------------------+
void PublishTick()
  {
   if(!InpPublishTicks)
      return;
   ulong now = GetTickCount64();
   if(now - g_lastTickMs < 200)
      return;
   g_lastTickMs = now;

   string symbol = _Symbol;
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid == 0.0 || ask == 0.0)
      return;
   double last = SymbolInfoDouble(symbol, SYMBOL_LAST);
   if(last == 0.0)
      last = (bid + ask) / 2.0;

   string tick = StringFormat(
      "{\"symbol\":\"%s\",\"bid\":%.5f,\"ask\":%.5f,\"last\":%.5f,\"ts\":\"%s\"}",
      symbol, bid, ask, last, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS));
   RedisLPush(TICK_QUEUE, tick);
  }

//+------------------------------------------------------------------+
//| Expert initialization / deinit                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("LumineEA starting: redis=", InpRedisHost, ":", InpRedisPort);
   g_connected = RedisConnect();
   if(g_connected)
      Print("LumineEA connected to Redis");
   else
      Print("LumineEA Redis connect FAILED — retry in OnTick");
   EventSetTimer(1);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_socket != INVALID_HANDLE)
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
     }
  }

//+------------------------------------------------------------------+
//| Timer: heartbeat / reconnect + command processing                |
//+------------------------------------------------------------------+
void OnTimer()
  {
   if(!g_connected && !RedisConnect())
      return;

   // AutoTrading harus ON — kalau off, order ditolak MT5.
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return;

   string payload = RedisBRPop(InpCommandTimeoutMs);
   if(payload != "")
     {
      Print("LumineEA command: ", payload);
      ExecuteCommand(payload);
     }
  }

//+------------------------------------------------------------------+
//| OnTick: publish real market data                                 |
//+------------------------------------------------------------------+
void OnTick()
  {
   PublishTick();
  }
//+------------------------------------------------------------------+
