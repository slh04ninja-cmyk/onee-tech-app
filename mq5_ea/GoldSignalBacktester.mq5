//+------------------------------------------------------------------+
//| GoldSignalBacktester.mq5                                         |
//| Expert Advisor — Backtesting signaux Telegram Gold               |
//| Version 1.0.1                                                    |
//| Lit les CSV exportés par Gold Signal Extractor                   |
//| Exécute les signaux selon la logique GZL TradingBot V9.0.0      |
//+------------------------------------------------------------------+
#property copyright "GZL TradingBot"
#property version   "1.01"
#property strict

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| ENUMS                                                            |
//+------------------------------------------------------------------+
enum ENUM_ENTRY_MODE
{
   ENTRY_ZONE_LOW = 0,   // Zone Low
   ENTRY_ZONE_MID = 1,   // Zone Mid
   ENTRY_ZONE_HIGH = 2   // Zone High
};

//+------------------------------------------------------------------+
//| PARAMÈTRES D'ENTRÉE                                              |
//+------------------------------------------------------------------+
// --- Lots & Exécution ---
input double   InpLotTotal          = 0.02;     // Lot total (split 50/50 zone)
input double   InpLotUnique         = 0.01;     // Lot prix unique + Quick Alert
input int      InpMaxPositions      = 3;        // Positions max simultanées
input double   InpMaxSpreadPoints   = 50.0;     // Spread max (pts MT5)
input int      InpSlippage          = 20;       // Slippage (pts MT5)
input int      InpOrderExpiryMin    = 240;      // Expiration ordres LIMIT (min)
input long     InpMagicNumber       = 20250226; // Magic Number

// --- Break Even ---
input bool     InpBE_Enabled        = true;     // Activer BE
input double   InpPNL_Trigger       = 8.0;      // PnL min ($) pour BE
input bool     InpBE_CancelPending  = true;     // Annuler pending au BE

// --- Gain Fixe ---
input bool     InpTPFixed_Enabled   = true;     // Activer gain fixe
input double   InpTPFixed_GainUSD   = 15.0;     // Gain cible / position ($)

// --- TP_TRIGGER ---
input bool     InpTPTrigger_Enabled = true;     // Activer TP_TRIGGER
input int      InpTPTrigger_Index   = 2;        // Index TP déclencheur (0-based)

// --- Stop Loss ---
input bool     InpSL_Custom         = true;     // SL personnalisé
input double   InpSL_PrixUnique     = 15.0;    // SL max prix unique ($)
input double   InpSL_PlusProche     = 10.0;    // Distance SL zone ($)
input double   InpSL_QuickAlert     = 10.0;    // SL provisoire Quick Alert ($)
input double   InpRR_Ratio          = 1.5;     // RR pour TP auto si SL seul

// --- Filtres ---
input bool     InpTimeFilter        = true;     // Filtre horaire
input int      InpStartHour         = 3;        // Heure début (UTC)
input int      InpEndHour           = 20;       // Heure fin (UTC)
input double   InpDailyProfitLimit  = 30.0;     // PnL quotidien max ($)
input bool     InpDailyLimit_Enabled= true;     // Activer limite quotidienne

// --- Spread & Slippage ---
input bool     InpSpread_Filter     = true;     // Filtrer par spread
input double   InpSpread_Cost       = 0.0;     // Coût spread ajouté au SL ($)

// --- Scénarios ---
input bool     InpEnablePrixUnique  = true;     // Prix Unique (S1/S2)
input bool     InpEnableZone        = true;     // Zone (CAS 1/2-a/2-b)
input bool     InpEnableQuickAlert  = true;     // Quick Alert

// --- CSV ---
input string   InpCSV_Prefix        = "";       // Préfixe fichier (vide = tous)

//+------------------------------------------------------------------+
//| CONSTANTES                                                       |
//+------------------------------------------------------------------+
#define MAX_TPS 10
#define MAX_SIGNALS 5000
#define MAX_ACTIVE 100
#define MAX_CHANNELS 20

//+------------------------------------------------------------------+
//| STRUCTURES                                                       |
//+------------------------------------------------------------------+
struct SignalData
{
   datetime    dt;
   string      direction;
   double      zone_low;
   double      zone_high;
   double      sl;
   double      tps[MAX_TPS];
   int         tp_count;
   string      source_file;
};

struct TradeEntry
{
   string      id;
   SignalData  signal;
   ulong       tickets[2];
   ulong       pending_orders[2];
   double      entry_prices[2];
   string      roles[2];
   int         ticket_count;
   int         pending_count;
   bool        be_activated;
   double      be_price;
   double      target_gain;
   datetime    open_time;
   string      scenario;
   bool        closed;
   double      pnl;
   string      close_reason;
};

struct ChannelStats
{
   string      name;
   int         total_signals;
   int         executed;
   int         wins;
   int         losses;
   int         be_count;
   double      total_pnl;
   double      max_drawdown;
   double      peak_pnl;
   int         tp_fixed_count;
   int         tp_trigger_count;
   int         daily_limit_count;
};

//+------------------------------------------------------------------+
//| VARIABLES GLOBALES                                               |
//+------------------------------------------------------------------+
CTrade         trade;

SignalData     g_signals[MAX_SIGNALS];
int            g_signal_count = 0;

TradeEntry     g_active[MAX_ACTIVE];
int            g_active_count = 0;

ChannelStats   g_channels[MAX_CHANNELS];
int            g_channel_count = 0;

double         g_daily_pnl = 0;
datetime       g_daily_reset = 0;
int            g_total_executed = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFilling(ORDER_FILLING_FOK);

   g_signal_count = 0;
   g_active_count = 0;
   g_channel_count = 0;
   g_daily_pnl = 0;
   g_daily_reset = 0;
   g_total_executed = 0;

   int loaded = LoadAllCSV();
   if(loaded == 0)
   {
      Print("Aucun signal charge. Verifiez le dossier Files/");
      return INIT_FAILED;
   }

   Print(loaded, " signaux charges depuis CSV");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   GenerateReport();
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   CheckDailyReset();

   if(InpDailyLimit_Enabled && CheckDailyLimit())
      return;

   ProcessSignals();
   ManageActiveTrades();
}

//+------------------------------------------------------------------+
//| CHARGEMENT CSV                                                   |
//+------------------------------------------------------------------+
int LoadAllCSV()
{
   int total = 0;
   string filename;
   long handle = FileFindFirst("*.csv", filename);

   if(handle == INVALID_HANDLE)
      return 0;

   do
   {
      if(InpCSV_Prefix != "" && StringFind(filename, InpCSV_Prefix) < 0)
         continue;

      int count = LoadCSV(filename);
      total += count;
      Print(filename, " -> ", count, " signaux");
   }
   while(FileFindNext(handle, filename));

   FileFindClose(handle);

   SortSignalsByDate();
   return total;
}

//+------------------------------------------------------------------+
//| Lire un CSV                                                      |
//+------------------------------------------------------------------+
int LoadCSV(string filename)
{
   // Lire tout le fichier d'un coup
   int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return 0;

   string content = "";
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      if(content != "")
         content += "\n";
      content += line;
   }
   FileClose(handle);

   // Découper en lignes
   string lines[];
   int line_count = SplitString(content, "\n", lines);
   if(line_count < 2)
      return 0;

   // Parser le header
   string header[];
   int hdr_cols = SplitString(lines[0], ",", header);

   int idx_dt = -1, idx_dir = -1, idx_zl = -1, idx_zh = -1, idx_sl = -1;
   int idx_tps[MAX_TPS];
   int tp_cols = 0;

   for(int i = 0; i < hdr_cols; i++)
   {
      string col = TrimStr(header[i]);
      if(col == "datetime")       idx_dt = i;
      else if(col == "direction") idx_dir = i;
      else if(col == "zone_low")  idx_zl = i;
      else if(col == "zone_high") idx_zh = i;
      else if(col == "sl")        idx_sl = i;
      else if(StringFind(col, "tp") == 0 || StringFind(col, "TP") == 0)
      {
         if(tp_cols < MAX_TPS)
         {
            idx_tps[tp_cols] = i;
            tp_cols++;
         }
      }
   }

   if(idx_dir < 0 || idx_zl < 0)
   {
      Print("CSV format invalide: ", filename);
      return 0;
   }

   // Créer les stats du channel
   CreateChannelStats(filename);

   // Parser les lignes de données
   int count = 0;
   for(int r = 1; r < line_count; r++)
   {
      if(StringLen(lines[r]) < 5)
         continue;

      string cols[];
      int ncols = SplitString(lines[r], ",", cols);
      if(ncols < hdr_cols)
         continue;

      string direction = TrimStr(cols[idx_dir]);
      if(direction != "BUY" && direction != "SELL")
         continue;

      datetime dt = 0;
      if(idx_dt >= 0 && idx_dt < ncols)
         dt = ParseDateTime(TrimStr(cols[idx_dt]));

      double zone_low = 0, zone_high = 0, sl = 0;
      if(idx_zl >= 0 && idx_zl < ncols) zone_low = StringToDouble(TrimStr(cols[idx_zl]));
      if(idx_zh >= 0 && idx_zh < ncols) zone_high = StringToDouble(TrimStr(cols[idx_zh]));
      if(idx_sl >= 0 && idx_sl < ncols) sl = StringToDouble(TrimStr(cols[idx_sl]));

      // Parser TPs
      double tps[MAX_TPS];
      int tp_count = 0;
      for(int t = 0; t < tp_cols; t++)
      {
         if(idx_tps[t] < ncols)
         {
            string tp_str = TrimStr(cols[idx_tps[t]]);
            if(tp_str != "")
            {
               double tp_val = StringToDouble(tp_str);
               if(tp_val > 0)
               {
                  tps[tp_count] = tp_val;
                  tp_count++;
               }
            }
         }
      }

      if(tp_count == 0 && sl == 0)
         continue;

      // Ajouter le signal
      if(g_signal_count >= MAX_SIGNALS)
         break;

      g_signals[g_signal_count].dt = dt;
      g_signals[g_signal_count].direction = direction;
      g_signals[g_signal_count].zone_low = zone_low;
      g_signals[g_signal_count].zone_high = zone_high;
      g_signals[g_signal_count].sl = sl;
      g_signals[g_signal_count].tp_count = tp_count;
      for(int t = 0; t < tp_count; t++)
         g_signals[g_signal_count].tps[t] = tps[t];
      g_signals[g_signal_count].source_file = filename;
      g_signal_count++;
      count++;

      // Mettre à jour les stats
      for(int c = 0; c < g_channel_count; c++)
      {
         if(g_channels[c].name == filename)
         {
            g_channels[c].total_signals = count;
            break;
         }
      }
   }

   return count;
}

//+------------------------------------------------------------------+
//| UTILITAIRES STRING                                               |
//+------------------------------------------------------------------+
int SplitString(string text, string sep, string &result[])
{
   int count = 0;
   int sep_len = StringLen(sep);
   int start = 0;

   while(start <= StringLen(text))
   {
      int pos = StringFind(text, sep, start);
      if(pos < 0)
         pos = StringLen(text);

      string part = StringSubstr(text, start, pos - start);
      if(count < ArraySize(result))
         result[count] = part;
      count++;
      start = pos + sep_len;
   }
   return count;
}

string TrimStr(string s)
{
   // Supprimer espaces début
   while(StringLen(s) > 0 && StringGetCharacter(s, 0) == ' ')
      s = StringSubstr(s, 1);
   // Supprimer espaces fin
   while(StringLen(s) > 0 && StringGetCharacter(s, StringLen(s) - 1) == ' ')
      s = StringSubstr(s, 0, StringLen(s) - 1);
   return s;
}

datetime ParseDateTime(string dt_str)
{
   // Format: YYYY-MM-DD HH:MM
   string parts[];
   SplitString(dt_str, " ", parts);

   string date_parts[];
   SplitString(parts[0], "-", date_parts);

   string time_parts[];
   if(ArraySize(parts) > 1)
      SplitString(parts[1], ":", time_parts);

   MqlDateTime mdt;
   mdt.year = (int)StringToInteger(date_parts[0]);
   mdt.mon = (int)StringToInteger(date_parts[1]);
   mdt.day = (int)StringToInteger(date_parts[2]);
   mdt.hour = (ArraySize(time_parts) > 0) ? (int)StringToInteger(time_parts[0]) : 0;
   mdt.min = (ArraySize(time_parts) > 1) ? (int)StringToInteger(time_parts[1]) : 0;
   mdt.sec = 0;

   return StructToTime(mdt);
}

//+------------------------------------------------------------------+
//| Trier les signaux par date                                       |
//+------------------------------------------------------------------+
void SortSignalsByDate()
{
   for(int i = 0; i < g_signal_count - 1; i++)
   {
      for(int j = 0; j < g_signal_count - i - 1; j++)
      {
         if(g_signals[j].dt > g_signals[j + 1].dt)
         {
            SignalData temp = g_signals[j];
            g_signals[j] = g_signals[j + 1];
            g_signals[j + 1] = temp;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Créer les stats d'un channel                                     |
//+------------------------------------------------------------------+
void CreateChannelStats(string filename)
{
   if(g_channel_count >= MAX_CHANNELS)
      return;

   g_channels[g_channel_count].name = filename;
   g_channels[g_channel_count].total_signals = 0;
   g_channels[g_channel_count].executed = 0;
   g_channels[g_channel_count].wins = 0;
   g_channels[g_channel_count].losses = 0;
   g_channels[g_channel_count].be_count = 0;
   g_channels[g_channel_count].total_pnl = 0;
   g_channels[g_channel_count].max_drawdown = 0;
   g_channels[g_channel_count].peak_pnl = 0;
   g_channels[g_channel_count].tp_fixed_count = 0;
   g_channels[g_channel_count].tp_trigger_count = 0;
   g_channels[g_channel_count].daily_limit_count = 0;
   g_channel_count++;
}

//+------------------------------------------------------------------+
//| TRAITEMENT DES SIGNAUX                                           |
//+------------------------------------------------------------------+
void ProcessSignals()
{
   datetime current_time = TimeCurrent();

   for(int i = 0; i < g_signal_count; i++)
   {
      if(g_signals[i].dt == 0 || g_signals[i].dt > current_time)
         continue;

      if(IsSignalProcessed(g_signals[i]))
         continue;

      if(InpTimeFilter && !IsWithinTradingHours(g_signals[i].dt))
         continue;

      if(InpSpread_Filter && !CheckSpread())
         continue;

      ExecuteSignal(g_signals[i]);
   }
}

//+------------------------------------------------------------------+
//| Vérifier si un signal a déjà été traité                          |
//+------------------------------------------------------------------+
bool IsSignalProcessed(SignalData &sig)
{
   for(int i = 0; i < g_active_count; i++)
   {
      if(g_active[i].signal.dt == sig.dt &&
         g_active[i].signal.direction == sig.direction &&
         g_active[i].signal.zone_low == sig.zone_low)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Vérifier les heures de trading                                   |
//+------------------------------------------------------------------+
bool IsWithinTradingHours(datetime dt)
{
   MqlDateTime mdt;
   TimeToStruct(dt, mdt);
   return (mdt.hour >= InpStartHour && mdt.hour < InpEndHour);
}

//+------------------------------------------------------------------+
//| Vérifier le spread                                               |
//+------------------------------------------------------------------+
bool CheckSpread()
{
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return (spread <= InpMaxSpreadPoints);
}

//+------------------------------------------------------------------+
//| Obtenir le prix actuel                                           |
//+------------------------------------------------------------------+
double GetCurrentPrice(string direction)
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return 0;
   return (direction == "BUY") ? tick.ask : tick.bid;
}

//+------------------------------------------------------------------+
//| EXÉCUTION D'UN SIGNAL                                            |
//+------------------------------------------------------------------+
void ExecuteSignal(SignalData &sig)
{
   double current_price = GetCurrentPrice(sig.direction);
   if(current_price == 0)
      return;

   bool is_zone = (sig.zone_low != sig.zone_high);
   bool is_qa = (sig.tp_count == 0 && sig.sl == 0);

   // Quick Alert
   if(is_qa && InpEnableQuickAlert)
   {
      ExecuteQuickAlert(sig, current_price);
      return;
   }

   // Prix Unique
   if(!is_zone && InpEnablePrixUnique)
   {
      if(IsPrixUnique_S1(sig, current_price))
         ExecutePrixUnique(sig, current_price, "PU-S1");
      else if(IsPrixUnique_S2(sig, current_price))
         ExecutePrixUnique(sig, current_price, "PU-S2");
      return;
   }

   // Zone
   if(is_zone && InpEnableZone)
   {
      if(IsCAS1(sig, current_price))
         ExecuteZone(sig, current_price, "C1");
      else if(IsCAS2a(sig, current_price))
         ExecuteZone(sig, current_price, "C2-a");
      else if(IsCAS2b(sig, current_price))
         ExecuteZone(sig, current_price, "C2-b");
      return;
   }
}

//+------------------------------------------------------------------+
//| Conditions scénarios                                             |
//+------------------------------------------------------------------+
bool IsPrixUnique_S1(SignalData &sig, double price)
{
   if(sig.direction == "BUY")
      return (sig.sl < price && price < sig.zone_low);
   else
      return (sig.zone_low < price && price < sig.sl);
}

bool IsPrixUnique_S2(SignalData &sig, double price)
{
   if(sig.tp_count == 0) return false;
   double tp1 = sig.tps[0];
   if(sig.direction == "BUY")
      return (sig.zone_low < price && price < tp1);
   else
      return (tp1 < price && price < sig.zone_low);
}

bool IsCAS1(SignalData &sig, double price)
{
   return (sig.zone_low <= price && price <= sig.zone_high);
}

bool IsCAS2a(SignalData &sig, double price)
{
   if(sig.tp_count < 1) return false;
   double tp1 = sig.tps[0];
   if(sig.direction == "BUY")
      return (sig.zone_high < price && price < tp1);
   else
      return (tp1 < price && price < sig.zone_low);
}

bool IsCAS2b(SignalData &sig, double price)
{
   if(sig.tp_count < 2) return false;
   double tp1 = sig.tps[0];
   double tp2 = sig.tps[1];
   if(sig.direction == "BUY")
      return (tp1 < price && price < tp2);
   else
      return (tp2 < price && price < tp1);
}

//+------------------------------------------------------------------+
//| CALCUL SL                                                        |
//+------------------------------------------------------------------+
double CalculateSL(SignalData &sig, double entry_price)
{
   double sl = sig.sl;

   if(InpSL_Custom)
   {
      bool is_zone = (sig.zone_low != sig.zone_high);
      bool is_qa = (sig.tp_count == 0 && sig.sl == 0);

      if(is_qa)
      {
         // Quick Alert : SL provisoire
         if(sig.direction == "BUY")
            sl = sig.zone_low - InpSL_QuickAlert;
         else
            sl = sig.zone_low + InpSL_QuickAlert;
      }
      else if(is_zone)
      {
         // Zone : SL_PlusProche = distance max ($) entre zone_edge et SL
         double zone_edge;
         if(sig.direction == "BUY")
            zone_edge = sig.zone_low;
         else
            zone_edge = sig.zone_high;

         double distance = MathAbs(sl - zone_edge);

         if(distance > InpSL_PlusProche)
         {
            if(sig.direction == "BUY")
               sl = zone_edge - InpSL_PlusProche;
            else
               sl = zone_edge + InpSL_PlusProche;
         }
      }
      else
      {
         // Prix Unique : SL_PrixUnique = distance max ($) entre entry et SL
         double distance = MathAbs(sl - entry_price);

         if(distance > InpSL_PrixUnique)
         {
            if(sig.direction == "BUY")
               sl = entry_price - InpSL_PrixUnique;
            else
               sl = entry_price + InpSL_PrixUnique;
         }
      }
   }

   // Ajouter le coût du spread
   if(InpSpread_Cost > 0)
   {
      if(sig.direction == "BUY")
         sl -= InpSpread_Cost;
      else
         sl += InpSpread_Cost;
   }

   return NormalizeDouble(sl, _Digits);
}

//+------------------------------------------------------------------+
//| Obtenir le TP final                                              |
//+------------------------------------------------------------------+
double GetTPFinal(SignalData &sig)
{
   if(sig.tp_count == 0)
      return 0;

   // Trier les TPs
   if(sig.direction == "BUY")
   {
      for(int i = 0; i < sig.tp_count - 1; i++)
         for(int j = 0; j < sig.tp_count - i - 1; j++)
            if(sig.tps[j] > sig.tps[j + 1])
            {
               double tmp = sig.tps[j];
               sig.tps[j] = sig.tps[j + 1];
               sig.tps[j + 1] = tmp;
            }
   }
   else
   {
      for(int i = 0; i < sig.tp_count - 1; i++)
         for(int j = 0; j < sig.tp_count - i - 1; j++)
            if(sig.tps[j] < sig.tps[j + 1])
            {
               double tmp = sig.tps[j];
               sig.tps[j] = sig.tps[j + 1];
               sig.tps[j + 1] = tmp;
            }
   }

   return NormalizeDouble(sig.tps[sig.tp_count - 1], _Digits);
}

//+------------------------------------------------------------------+
//| ORDRES                                                           |
//+------------------------------------------------------------------+
ulong OpenMarketOrder(string direction, double lot, double tp, double sl, string comment)
{
   bool ok = false;
   if(direction == "BUY")
      ok = trade.Buy(lot, _Symbol, 0, sl, tp, comment);
   else
      ok = trade.Sell(lot, _Symbol, 0, sl, tp, comment);

   if(ok)
      return trade.ResultOrder();

   Print("Echec MARKET ", direction, " ", trade.ResultRetcode());
   return 0;
}

ulong OpenLimitOrder(string direction, double lot, double price, double tp, double sl, string comment)
{
   MqlDateTime mdt;
   TimeToStruct(TimeCurrent(), mdt);
   mdt.hour += InpOrderExpiryMin / 60;
   datetime expiry = StructToTime(mdt);

   bool ok = false;
   if(direction == "BUY")
      ok = trade.BuyLimit(lot, price, _Symbol, sl, tp, ORDER_TIME_SPECIFIED, expiry, comment);
   else
      ok = trade.SellLimit(lot, price, _Symbol, sl, tp, ORDER_TIME_SPECIFIED, expiry, comment);

   if(ok)
      return trade.ResultOrder();

   Print("Echec LIMIT ", direction, " @", price, " ", trade.ResultRetcode());
   return 0;
}

//+------------------------------------------------------------------+
//| EXÉCUTION PRIX UNIQUE                                            |
//+------------------------------------------------------------------+
void ExecutePrixUnique(SignalData &sig, double price, string scenario)
{
   double sl_price = CalculateSL(sig, price);
   double tp_price = GetTPFinal(sig);
   double lot = InpLotUnique;
   ulong ticket = 0;

   if(scenario == "PU-S1")
      ticket = OpenMarketOrder(sig.direction, lot, tp_price, sl_price, "CH-PU-S1");
   else if(scenario == "PU-S2")
      ticket = OpenLimitOrder(sig.direction, lot, sig.zone_low, tp_price, sl_price, "CH-PU-S2");

   if(ticket > 0)
   {
      RegisterTrade(sig, ticket, price, scenario, lot);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed");
   }
}

//+------------------------------------------------------------------+
//| EXÉCUTION ZONE                                                   |
//+------------------------------------------------------------------+
void ExecuteZone(SignalData &sig, double price, string scenario)
{
   double sl_price = CalculateSL(sig, price);
   double tp_price = GetTPFinal(sig);
   double lot_half = InpLotTotal / 2.0;

   ulong ticket1 = 0, ticket2 = 0;

   if(scenario == "C1")
   {
      ticket1 = OpenMarketOrder(sig.direction, lot_half, tp_price, sl_price, "CH-C1-MKT");

      double limit_price = 0;
      if(sig.direction == "BUY")
         limit_price = (sig.zone_low + sig.sl) / 2.0;
      else
         limit_price = (sig.zone_high + sig.sl) / 2.0;

      ticket2 = OpenLimitOrder(sig.direction, lot_half, limit_price, tp_price, sl_price, "CH-C1-LMT");
   }
   else if(scenario == "C2-a")
   {
      ticket1 = OpenMarketOrder(sig.direction, lot_half, tp_price, sl_price, "CH-C2-MKT");

      double limit_price = (sig.direction == "BUY") ? sig.zone_low : sig.zone_high;
      ticket2 = OpenLimitOrder(sig.direction, lot_half, limit_price, tp_price, sl_price, "CH-C2-LMT");
   }
   else if(scenario == "C2-b")
   {
      double zone_edge = (sig.direction == "BUY") ? sig.zone_high : sig.zone_low;
      double zone_opp = (sig.direction == "BUY") ? sig.zone_low : sig.zone_high;

      ticket1 = OpenLimitOrder(sig.direction, lot_half, zone_edge, tp_price, sl_price, "CH-C2-L1");
      ticket2 = OpenLimitOrder(sig.direction, lot_half, zone_opp, tp_price, sl_price, "CH-C2-L2");
   }

   if(ticket1 > 0 || ticket2 > 0)
   {
      RegisterTradeZone(sig, ticket1, ticket2, price, scenario, lot_half);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed");
   }
}

//+------------------------------------------------------------------+
//| EXÉCUTION QUICK ALERT                                            |
//+------------------------------------------------------------------+
void ExecuteQuickAlert(SignalData &sig, double price)
{
   // SL_QuickAlert est en $, directement en prix
   double sl_price, tp_price;

   if(sig.direction == "BUY")
   {
      sl_price = sig.zone_low - InpSL_QuickAlert;
      tp_price = sig.zone_low + InpSL_QuickAlert * InpRR_Ratio;
   }
   else
   {
      sl_price = sig.zone_low + InpSL_QuickAlert;
      tp_price = sig.zone_low - InpSL_QuickAlert * InpRR_Ratio;
   }

   double lot = InpLotUnique;
   ulong ticket = 0;

   bool between = false;
   if(sig.direction == "BUY")
      between = (sl_price < price && price < sig.zone_low);
   else
      between = (sig.zone_low < price && price < sl_price);

   if(between)
      ticket = OpenMarketOrder(sig.direction, lot, tp_price, sl_price, "CH-QA-MKT");
   else
      ticket = OpenLimitOrder(sig.direction, lot, sig.zone_low, tp_price, sl_price, "CH-QA-LMT");

   if(ticket > 0)
   {
      RegisterTrade(sig, ticket, price, "QA", lot);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed");
   }
}

//+------------------------------------------------------------------+
//| ENREGISTREMENT DES TRADES                                        |
//+------------------------------------------------------------------+
void RegisterTrade(SignalData &sig, ulong ticket, double price, string scenario, double lot)
{
   if(g_active_count >= MAX_ACTIVE)
      return;

   TradeEntry entry;
   entry.id = IntegerToString(sig.dt) + "_" + sig.direction;
   entry.signal = sig;
   entry.tickets[0] = ticket;
   entry.ticket_count = 1;
   entry.pending_orders[0] = 0;
   entry.pending_orders[1] = 0;
   entry.pending_count = 0;
   entry.entry_prices[0] = price;
   entry.roles[0] = scenario;
   entry.be_activated = false;
   entry.be_price = 0;
   entry.target_gain = InpTPFixed_GainUSD;
   entry.open_time = TimeCurrent();
   entry.scenario = scenario;
   entry.closed = false;
   entry.pnl = 0;
   entry.close_reason = "";

   g_active[g_active_count] = entry;
   g_active_count++;
}

void RegisterTradeZone(SignalData &sig, ulong ticket1, ulong ticket2, double price, string scenario, double lot)
{
   if(g_active_count >= MAX_ACTIVE)
      return;

   TradeEntry entry;
   entry.id = IntegerToString(sig.dt) + "_" + sig.direction;
   entry.signal = sig;
   entry.ticket_count = 0;
   entry.pending_count = 0;

   if(ticket1 > 0)
   {
      entry.tickets[entry.ticket_count] = ticket1;
      entry.entry_prices[entry.ticket_count] = price;
      entry.roles[entry.ticket_count] = scenario + "-MKT";
      entry.ticket_count++;
   }
   if(ticket2 > 0)
   {
      entry.tickets[entry.ticket_count] = ticket2;
      entry.entry_prices[entry.ticket_count] = price;
      entry.roles[entry.ticket_count] = scenario + "-LMT";
      entry.ticket_count++;
   }

   entry.pending_orders[0] = 0;
   entry.pending_orders[1] = 0;
   entry.be_activated = false;
   entry.be_price = 0;
   entry.target_gain = InpTPFixed_GainUSD * entry.ticket_count;
   entry.open_time = TimeCurrent();
   entry.scenario = scenario;
   entry.closed = false;
   entry.pnl = 0;
   entry.close_reason = "";

   g_active[g_active_count] = entry;
   g_active_count++;
}

//+------------------------------------------------------------------+
//| GESTION DES TRADES ACTIFS                                        |
//+------------------------------------------------------------------+
void ManageActiveTrades()
{
   for(int i = g_active_count - 1; i >= 0; i--)
   {
      if(g_active[i].closed)
         continue;

      int open_count = 0;
      double total_pnl = 0;
      double min_pnl = 999999;

      for(int t = 0; t < g_active[i].ticket_count; t++)
      {
         ulong ticket = g_active[i].tickets[t];
         if(PositionSelectByTicket(ticket))
         {
            open_count++;
            double pnl = PositionGetDouble(POSITION_PROFIT) +
                         PositionGetDouble(POSITION_SWAP);
            total_pnl += pnl;
            if(pnl < min_pnl)
               min_pnl = pnl;
         }
      }

      if(open_count == 0)
      {
         CloseTrade(i, "CLOSED");
         continue;
      }

      // BE
      if(InpBE_Enabled && !g_active[i].be_activated && min_pnl >= InpPNL_Trigger)
         ApplyBE(i);

      // TP_FIXED
      if(InpTPFixed_Enabled && g_active[i].be_activated)
      {
         if(total_pnl >= g_active[i].target_gain)
         {
            CloseTrade(i, "TP_FIXED");
            continue;
         }
      }

      // TP_TRIGGER
      if(InpTPTrigger_Enabled)
         CheckTPTrigger(i);
   }
}

//+------------------------------------------------------------------+
//| Appliquer le BE                                                  |
//+------------------------------------------------------------------+
void ApplyBE(int idx)
{
   int open_count = 0;
   for(int t = 0; t < g_active[idx].ticket_count; t++)
   {
      if(PositionSelectByTicket(g_active[idx].tickets[t]))
         open_count++;
   }

   double be_price = 0;

   if(open_count == 1)
      be_price = g_active[idx].entry_prices[0];
   else if(open_count == 2)
      be_price = (g_active[idx].entry_prices[0] + g_active[idx].entry_prices[1]) / 2.0;
   else
      return;

   be_price = NormalizeDouble(be_price, _Digits);

   int modified = 0;
   for(int t = 0; t < g_active[idx].ticket_count; t++)
   {
      ulong ticket = g_active[idx].tickets[t];
      if(PositionSelectByTicket(ticket))
      {
         if(trade.PositionModify(ticket, be_price, PositionGetDouble(POSITION_TP)))
            modified++;
      }
   }

   if(modified > 0)
   {
      g_active[idx].be_activated = true;
      g_active[idx].be_price = be_price;

      if(InpBE_CancelPending)
         CancelPendingForEntry(idx);

      g_active[idx].target_gain = InpTPFixed_GainUSD * open_count;

      Print("BE active @", be_price, " | ", open_count, " POS | Target=", g_active[idx].target_gain);
      UpdateChannelStats(g_active[idx].signal.source_file, "be_count");
   }
}

//+------------------------------------------------------------------+
//| Annuler les ordres pending                                       |
//+------------------------------------------------------------------+
void CancelPendingForEntry(int idx)
{
   for(int o = 0; o < g_active[idx].pending_count; o++)
   {
      ulong order_ticket = g_active[idx].pending_orders[o];
      if(order_ticket > 0 && OrderSelect(order_ticket))
         trade.OrderDelete(order_ticket);
   }
   g_active[idx].pending_count = 0;
}

//+------------------------------------------------------------------+
//| Vérifier TP_TRIGGER                                              |
//+------------------------------------------------------------------+
void CheckTPTrigger(int idx)
{
   if(g_active[idx].pending_count == 0)
      return;

   SignalData &sig = g_active[idx].signal;
   int trigger_idx = InpTPTrigger_Index;
   if(trigger_idx >= sig.tp_count)
      trigger_idx = sig.tp_count - 1;
   if(trigger_idx < 0)
      return;

   double tp_trigger = sig.tps[trigger_idx];
   double current_price = GetCurrentPrice(sig.direction);
   bool triggered = false;

   if(sig.direction == "BUY" && current_price >= tp_trigger)
      triggered = true;
   else if(sig.direction == "SELL" && current_price <= tp_trigger)
      triggered = true;

   if(triggered)
   {
      int pending_count = g_active[idx].pending_count;
      CancelPendingForEntry(idx);

      Print("TP_TRIGGER @", tp_trigger, " | ", pending_count, " ordres annules");
      UpdateChannelStats(g_active[idx].signal.source_file, "tp_trigger_count");

      int open_count = 0;
      for(int t = 0; t < g_active[idx].ticket_count; t++)
      {
         if(PositionSelectByTicket(g_active[idx].tickets[t]))
            open_count++;
      }

      if(open_count == 0)
         CloseTrade(idx, "TP_TRIGGER");
   }
}

//+------------------------------------------------------------------+
//| Fermer un trade                                                  |
//+------------------------------------------------------------------+
void CloseTrade(int idx, string reason)
{
   double total_pnl = 0;

   for(int t = 0; t < g_active[idx].ticket_count; t++)
   {
      ulong ticket = g_active[idx].tickets[t];
      if(PositionSelectByTicket(ticket))
      {
         total_pnl += PositionGetDouble(POSITION_PROFIT) +
                      PositionGetDouble(POSITION_SWAP);
         trade.PositionClose(ticket);
      }
   }

   g_active[idx].closed = true;
   g_active[idx].pnl = total_pnl;
   g_active[idx].close_reason = reason;

   string src = g_active[idx].signal.source_file;
   UpdateChannelStatsPnl(src, total_pnl);

   if(total_pnl > 0)
      UpdateChannelStats(src, "wins");
   else if(total_pnl < 0)
      UpdateChannelStats(src, "losses");

   if(reason == "TP_FIXED")
      UpdateChannelStats(src, "tp_fixed_count");

   g_daily_pnl += total_pnl;

   Print("Trade ferme: ", reason, " PnL=", total_pnl, " | ", g_active[idx].scenario, " ", g_active[idx].signal.direction);
}

//+------------------------------------------------------------------+
//| MISE À JOUR DES STATS                                            |
//+------------------------------------------------------------------+
void UpdateChannelStats(string filename, string field)
{
   for(int i = 0; i < g_channel_count; i++)
   {
      if(g_channels[i].name == filename)
      {
         if(field == "executed")          g_channels[i].executed++;
         else if(field == "wins")         g_channels[i].wins++;
         else if(field == "losses")       g_channels[i].losses++;
         else if(field == "be_count")     g_channels[i].be_count++;
         else if(field == "tp_fixed_count") g_channels[i].tp_fixed_count++;
         else if(field == "tp_trigger_count") g_channels[i].tp_trigger_count++;
         break;
      }
   }
}

void UpdateChannelStatsPnl(string filename, double pnl)
{
   for(int i = 0; i < g_channel_count; i++)
   {
      if(g_channels[i].name == filename)
      {
         g_channels[i].total_pnl += pnl;
         if(g_channels[i].total_pnl > g_channels[i].peak_pnl)
            g_channels[i].peak_pnl = g_channels[i].total_pnl;
         double dd = g_channels[i].peak_pnl - g_channels[i].total_pnl;
         if(dd > g_channels[i].max_drawdown)
            g_channels[i].max_drawdown = dd;
         break;
      }
   }
}

//+------------------------------------------------------------------+
//| GESTION QUOTIDIENNE                                              |
//+------------------------------------------------------------------+
void CheckDailyReset()
{
   MqlDateTime mdt;
   TimeToStruct(TimeCurrent(), mdt);

   MqlDateTime start_mdt;
   start_mdt = mdt;
   start_mdt.hour = InpStartHour;
   start_mdt.min = 0;
   start_mdt.sec = 0;
   datetime today_start = StructToTime(start_mdt);

   if(g_daily_reset < today_start && TimeCurrent() >= today_start)
   {
      g_daily_pnl = 0;
      g_daily_reset = today_start;
      Print("Reset quotidien a ", InpStartHour, "h UTC");
   }
}

bool CheckDailyLimit()
{
   if(g_daily_pnl >= InpDailyProfitLimit)
   {
      for(int i = g_active_count - 1; i >= 0; i--)
      {
         if(!g_active[i].closed)
            CloseTrade(i, "DAILY_LIMIT");
      }
      Print("Limite quotidienne atteinte: ", g_daily_pnl, "$");
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| GÉNÉRATION DU RAPPORT                                            |
//+------------------------------------------------------------------+
void GenerateReport()
{
   string report = "";
   report += "==========================================\n";
   report += "  GOLD SIGNAL BACKTESTER - RAPPORT FINAL\n";
   report += "==========================================\n\n";

   report += "Parametres:\n";
   report += "  Lot Total: " + DoubleToString(InpLotTotal) + "\n";
   report += "  Lot Unique: " + DoubleToString(InpLotUnique) + "\n";
   report += "  Max Positions: " + IntegerToString(InpMaxPositions) + "\n";
   report += "  BE Trigger: " + DoubleToString(InpPNL_Trigger) + " $\n";
   report += "  TP_FIXED Gain: " + DoubleToString(InpTPFixed_GainUSD) + " $/pos\n";
   report += "  Daily Limit: " + DoubleToString(InpDailyProfitLimit) + " $\n";
   report += "  Spread Max: " + DoubleToString(InpMaxSpreadPoints) + " pts\n";
   report += "  Slippage: " + IntegerToString(InpSlippage) + " pts\n";
   report += "  SL Custom: " + (InpSL_Custom ? "ON" : "OFF") + "\n";
   report += "  SL PrixUnique: " + DoubleToString(InpSL_PrixUnique) + " $\n";
   report += "  SL PlusProche: " + DoubleToString(InpSL_PlusProche) + " $\n";
   report += "  SL QuickAlert: " + DoubleToString(InpSL_QuickAlert) + " $\n\n";

   report += "Signaux charges: " + IntegerToString(g_signal_count) + "\n";
   report += "Signaux executes: " + IntegerToString(g_total_executed) + "\n\n";

   // Rapport par channel
   for(int i = 0; i < g_channel_count; i++)
   {
      report += "------------------------------------------\n";
      report += "Channel: " + g_channels[i].name + "\n";
      report += "  Signaux analyses: " + IntegerToString(g_channels[i].total_signals) + "\n";
      report += "  Signaux executes: " + IntegerToString(g_channels[i].executed) + "\n";

      int total_trades = g_channels[i].wins + g_channels[i].losses + g_channels[i].be_count;
      double win_rate = (total_trades > 0) ? (double)g_channels[i].wins / total_trades * 100 : 0;

      double gross_profit = 0, gross_loss = 0;
      for(int t = 0; t < g_active_count; t++)
      {
         if(g_active[t].closed && g_active[t].signal.source_file == g_channels[i].name)
         {
            if(g_active[t].pnl > 0) gross_profit += g_active[t].pnl;
            else gross_loss += MathAbs(g_active[t].pnl);
         }
      }
      double profit_factor = (gross_loss > 0) ? gross_profit / gross_loss : 0;

      report += "  Trades: " + IntegerToString(total_trades) + "\n";
      report += "  Wins: " + IntegerToString(g_channels[i].wins) + " (" + DoubleToString(win_rate, 1) + "%)\n";
      report += "  Losses: " + IntegerToString(g_channels[i].losses) + "\n";
      report += "  BE: " + IntegerToString(g_channels[i].be_count) + "\n";
      report += "  PnL total: " + DoubleToString(g_channels[i].total_pnl, 2) + " $\n";
      report += "  Max Drawdown: " + DoubleToString(g_channels[i].max_drawdown, 2) + " $\n";
      report += "  Profit Factor: " + DoubleToString(profit_factor, 2) + "\n";
      report += "  TP_FIXED: " + IntegerToString(g_channels[i].tp_fixed_count) + "\n";
      report += "  TP_TRIGGER: " + IntegerToString(g_channels[i].tp_trigger_count) + "\n\n";
   }

   // Résumé global
   report += "==========================================\n";
   report += "  RESUME GLOBAL\n";
   report += "==========================================\n";
   report += "  PnL total: " + DoubleToString(g_daily_pnl, 2) + " $\n";
   report += "  Channels analyses: " + IntegerToString(g_channel_count) + "\n\n";

   report += "  CLASSEMENT:\n";
   for(int i = 0; i < g_channel_count; i++)
   {
      int rank = i + 1;
      report += "  #" + IntegerToString(rank) + " " + g_channels[i].name +
                " | PnL=" + DoubleToString(g_channels[i].total_pnl, 2) + "$" +
                " | Trades=" + IntegerToString(g_channels[i].wins + g_channels[i].losses) + "\n";
   }

   Print(report);

   int handle = FileOpen("BacktestReport.txt", FILE_WRITE | FILE_TXT);
   if(handle != INVALID_HANDLE)
   {
      FileWriteString(handle, report);
      FileClose(handle);
      Print("Rapport sauvegarde: BacktestReport.txt");
   }
}
//+------------------------------------------------------------------+
