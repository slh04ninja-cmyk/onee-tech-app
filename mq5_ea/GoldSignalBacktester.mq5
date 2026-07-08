//+------------------------------------------------------------------+
//| GoldSignalBacktester.mq5                                         |
//| Expert Advisor — Backtesting signaux Telegram Gold               |
//| Version 1.0.2                                                    |
//| Lit les CSV exportés par Gold Signal Extractor                   |
//| Exécute les signaux selon la logique GZL TradingBot V9.0.0      |
//+------------------------------------------------------------------+
#property copyright "GZL TradingBot"
#property version   "1.02"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

//+------------------------------------------------------------------+
//| ENUMS                                                            |
//+------------------------------------------------------------------+
enum ENUM_ENTRY_MODE
{
   ENTRY_ZONE_LOW = 0,   // Zone Low
   ENTRY_ZONE_MID = 1,   // Zone Mid (milieu)
   ENTRY_ZONE_HIGH = 2   // Zone High
};

enum ENUM_BE_MODE
{
   BE_ENTRY = 0,    // SL @ Entry (1 position)
   BE_MEDIAN = 1    // SL @ Median (2 positions)
};

enum ENUM_TP_MODE
{
   TP_FIXED_GAIN = 0,    // Gain fixe par position
   TP_BROKER = 1,        // Broker TP (classique)
   TP_HYBRID = 2         // Gain fixe + Broker TP (le premier atteint)
};

//+------------------------------------------------------------------+
//| PARAMÈTRES D'ENTRÉE                                              |
//+------------------------------------------------------------------+
// --- Lots & Exécution ---
input group "📊 Lots & Exécution"
input double   InpLotTotal          = 0.02;    // Lot total (split 50/50 zone)
input double   InpLotUnique         = 0.01;    // Lot prix unique + Quick Alert
input int      InpMaxPositions      = 3;       // Positions max simultanées
input double   InpMaxSpreadPoints   = 50.0;    // Spread max (pts MT5)
input int      InpSlippage          = 20;      // Slippage (pts MT5)
input int      InpOrderExpiryMin    = 240;     // Expiration ordres LIMIT (minutes)
input long     InpMagicNumber       = 20250226;// Magic Number

// --- Break Even ---
input group "🔒 Break Even (BE)"
input bool     InpBE_Enabled        = true;    // Activer BE
input double   InpPNL_Trigger       = 8.0;    // PnL min ($) pour BE
input bool     InpBE_CancelPending  = true;    // Annuler pending au BE

// --- Gain Fixe ---
input group "🎯 Gain Fixe (TP_FIXED)"
input bool     InpTPFixed_Enabled   = true;    // Activer gain fixe
input double   InpTPFixed_GainUSD   = 15.0;   // Gain cible / position ($)
input bool     InpTPFixed_CloseAll  = true;    // Fermer tout au gain fixe

// --- TP_TRIGGER ---
input group "⚡ TP_TRIGGER"
input bool     InpTPTrigger_Enabled = true;    // Activer TP_TRIGGER
input int      InpTPTrigger_Index   = 2;       // Index TP déclencheur (0-based)

// --- Stop Loss ---
input group "🛡️ Stop Loss Configurable"
input bool     InpSL_Custom         = true;    // SL personnalisé (sinon signal)
input double   InpSL_PrixUnique     = 15.0;   // SL max prix unique ($)
input double   InpSL_PlusProche     = 10.0;   // Distance SL zone ($)
input double   InpSL_QuickAlert     = 10.0;   // SL provisoire Quick Alert ($)
input double   InpRR_Ratio          = 1.5;    // RR pour TP auto si SL seul

// --- Filtres ---
input group "⏰ Filtres"
input bool     InpTimeFilter        = true;    // Filtre horaire
input int      InpStartHour         = 3;       // Heure début (UTC)
input int      InpEndHour           = 20;      // Heure fin (UTC)
input double   InpDailyProfitLimit  = 30.0;    // PnL quotidien max ($)
input bool     InpDailyLimit_Enabled= true;    // Activer limite quotidienne

// --- Spread & Slippage ---
input group "📈 Spread & Slippage"
input bool     InpSpread_Filter     = true;    // Filtrer par spread
input bool     InpSlippage_Enabled  = true;    // Appliquer slippage
input double   InpSpread_Cost       = 0.0;    // Coût spread ajouté au SL ($)

// --- Scénarios ---
input group "📋 Scénarios d'exécution"
input bool     InpEnablePrixUnique  = true;    // Prix Unique (S1/S2)
input bool     InpEnableZone        = true;    // Zone (CAS 1/2-a/2-b)
input bool     InpEnableQuickAlert  = true;    // Quick Alert

// --- CSV ---
input group "📂 Fichier CSV"
input string   InpCSV_Folder        = "";      // Dossier CSV (vide = Files/)
input string   InpCSV_Prefix        = "";      // Préfixe fichier (vide = tous)

//+------------------------------------------------------------------+
//| STRUCTURES                                                       |
//+------------------------------------------------------------------+
struct SignalData
{
   datetime    dt;           // Date/heure du signal
   string      direction;    // BUY / SELL
   double      zone_low;     // Basse zone
   double      zone_high;    // Haute zone
   double      sl;           // Stop Loss
   double      tps[];        // Tableau de TPs
   int         tp_count;     // Nombre de TPs
   string      source_file;  // Fichier source
};

struct TradeEntry
{
   string      id;               // Identifiant unique
   SignalData  signal;           // Signal original
   ulong       tickets[];        // Tickets positions ouvertes
   ulong       pending_orders[]; // Ordres pending
   double      entry_prices[];   // Prix d'entrée par ticket
   string      roles[];          // Rôle de chaque ticket
   bool        be_activated;     // BE activé
   double      be_price;         // Prix BE
   double      target_gain;      // Gain cible
   datetime    open_time;        // Heure d'ouverture
   string      scenario;         // PU-S1, PU-S2, C1, C2, QA
   bool        closed;           // Trade fermé
   double      pnl;              // PnL réalisé
   string      close_reason;     // TP, SL, BE, TP_FIXED, TP_TRIGGER, EXPIRATION
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
CPositionInfo  posInfo;
COrderInfo     orderInfo;

SignalData     g_signals[];        // Tous les signaux chargés
TradeEntry     g_active[];         // Trades actifs
ChannelStats   g_channels[];       // Stats par channel
double         g_daily_pnl;        // PnL quotidien
datetime       g_daily_reset;      // Dernier reset quotidien
int            g_total_signals;    // Total signaux chargés
int            g_total_executed;   // Total exécutés
string         g_report;           // Rapport final

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   // Configurer le trade
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFilling(ORDER_FILLING_FOK);

   // Initialiser les compteurs
   g_daily_pnl = 0;
   g_daily_reset = 0;
   g_total_signals = 0;
   g_total_executed = 0;
   g_report = "";

   // Charger les signaux depuis les CSV
   int loaded = LoadAllCSV();
   if(loaded == 0)
   {
      Print("❌ Aucun signal chargé. Vérifiez le dossier Files/");
      return INIT_FAILED;
   }

   Print("✅ ", loaded, " signaux chargés depuis CSV");
   Print("📊 Paramètres: Lot=", InpLotTotal, " BE=", InpBE_Enabled,
         " TP_FIXED=", InpTPFixed_Enabled, " Gain=", InpTPFixed_GainUSD);

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
   // Vérifier le reset quotidien
   CheckDailyReset();

   // Vérifier la limite quotidienne
   if(InpDailyLimit_Enabled && CheckDailyLimit())
      return;

   // Traiter les signaux dont le timestamp est atteint
   ProcessSignals();

   // Gérer les trades actifs (BE, TP_FIXED, TP_TRIGGER)
   ManageActiveTrades();

   // Vérifier les ordres pending (remplissage, expiration)
   CheckPendingOrders();
}

//+------------------------------------------------------------------+
//| CHARGEMENT CSV                                                   |
//+------------------------------------------------------------------+
int LoadAllCSV()
{
   int total = 0;
   string filename;

   // FileFindFirst cherche dans MQL5/Files/ automatiquement
   long handle = FileFindFirst("*.csv", filename);

   if(handle == INVALID_HANDLE)
   {
      Print("Aucun CSV trouve dans MQL5/Files/");
      return 0;
   }

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

   // Trier par date
   SortSignalsByDate();

   return total;
}

//+------------------------------------------------------------------+
//| Charger un fichier CSV                                           |
//+------------------------------------------------------------------+
int LoadCSV(string filepath, string filename)
{
   int handle = FileOpen(filepath, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("❌ Impossible d'ouvrir: ", filepath);
      return 0;
   }

   // Lire le header pour compter les colonnes TP
   string header[];
   int tp_cols = 0;
   string line = FileReadString(handle); // Header line
   StringSplit(line, ',', header);

   // Trouver les index des colonnes
   int idx_datetime = -1, idx_direction = -1, idx_zone_low = -1;
   int idx_zone_high = -1, idx_sl = -1;
   int idx_tps[];

   for(int i = 0; i < ArraySize(header); i++)
   {
      string col = header[i];
      StringTrimLeft(col);
      StringTrimRight(col);

      if(col == "datetime")    idx_datetime = i;
      else if(col == "direction") idx_direction = i;
      else if(col == "zone_low")  idx_zone_low = i;
      else if(col == "zone_high") idx_zone_high = i;
      else if(col == "sl")        idx_sl = i;
      else if(StringFind(col, "tp") == 0 || StringFind(col, "TP") == 0)
      {
         ArrayResize(idx_tps, tp_cols + 1);
         idx_tps[tp_cols] = i;
         tp_cols++;
      }
   }

   if(idx_direction < 0 || idx_zone_low < 0)
   {
      Print("❌ CSV format invalide: ", filepath);
      FileClose(handle);
      return 0;
   }

   // Lire les données
   int count = 0;
   while(!FileIsEnding(handle))
   {
      string cols[];
      int num_cols = 0;

      // Lire chaque colonne
      string row_data[];
      ArrayResize(row_data, 0);

      bool first = true;
      while(!FileIsEnding(handle))
      {
         string val = FileReadString(handle);
         if(first)
         {
            // Première colonne de la ligne
            ArrayResize(row_data, 1);
            row_data[0] = val;
            first = false;
         }
         else
         {
            int sz = ArraySize(row_data);
            ArrayResize(row_data, sz + 1);
            row_data[sz] = val;
         }

         // Vérifier si on a lu toutes les colonnes attendues
         if(ArraySize(row_data) >= ArraySize(header))
            break;
      }

      if(ArraySize(row_data) < ArraySize(header))
         continue;

      // Parser la direction
      string direction = row_data[idx_direction];
      StringTrimLeft(direction);
      StringTrimRight(direction);
      if(direction != "BUY" && direction != "SELL")
         continue;

      // Parser la date
      datetime dt = 0;
      if(idx_datetime >= 0)
      {
         string dt_str = row_data[idx_datetime];
         StringTrimLeft(dt_str);
         StringTrimRight(dt_str);
         dt = ParseDateTime(dt_str);
      }

      // Parser zone_low, zone_high, sl
      double zone_low = StringToDouble(row_data[idx_zone_low]);
      double zone_high = StringToDouble(row_data[idx_zone_high]);
      double sl = (idx_sl >= 0) ? StringToDouble(row_data[idx_sl]) : 0;

      // Parser TPs
      double tps[];
      int tp_count = 0;
      for(int t = 0; t < tp_cols; t++)
      {
         if(idx_tps[t] < ArraySize(row_data))
         {
            string tp_str = row_data[idx_tps[t]];
            StringTrimLeft(tp_str);
            StringTrimRight(tp_str);
            if(tp_str != "")
            {
               double tp_val = StringToDouble(tp_str);
               if(tp_val > 0)
               {
                  ArrayResize(tps, tp_count + 1);
                  tps[tp_count] = tp_val;
                  tp_count++;
               }
            }
         }
      }

      if(tp_count == 0 && sl == 0)
         continue; // Signal incomplet

      // Ajouter le signal
      int sz = ArraySize(g_signals);
      ArrayResize(g_signals, sz + 1);
      g_signals[sz].dt = dt;
      g_signals[sz].direction = direction;
      g_signals[sz].zone_low = zone_low;
      g_signals[sz].zone_high = zone_high;
      g_signals[sz].sl = sl;
      ArrayResize(g_signals[sz].tps, tp_count);
      for(int t = 0; t < tp_count; t++)
         g_signals[sz].tps[t] = tps[t];
      g_signals[sz].tp_count = tp_count;
      g_signals[sz].source_file = filename;

      count++;
   }

   FileClose(handle);

   // Créer les stats du channel
   CreateChannelStats(filename, count);

   return count;
}

//+------------------------------------------------------------------+
//| Parser une date depuis le CSV                                    |
//+------------------------------------------------------------------+
datetime ParseDateTime(string dt_str)
{
   // Format: YYYY-MM-DD HH:MM
   string parts[];
   StringSplit(dt_str, ' ', parts);

   if(ArraySize(parts) < 2)
      return 0;

   string date_parts[];
   StringSplit(parts[0], '-', date_parts);

   string time_parts[];
   StringSplit(parts[1], ':', time_parts);

   if(ArraySize(date_parts) < 3 || ArraySize(time_parts) < 2)
      return 0;

   MqlDateTime mdt;
   mdt.year = (int)StringToInteger(date_parts[0]);
   mdt.mon = (int)StringToInteger(date_parts[1]);
   mdt.day = (int)StringToInteger(date_parts[2]);
   mdt.hour = (int)StringToInteger(time_parts[0]);
   mdt.min = (int)StringToInteger(time_parts[1]);
   mdt.sec = 0;

   return StructToTime(mdt);
}

//+------------------------------------------------------------------+
//| Trier les signaux par date                                       |
//+------------------------------------------------------------------+
void SortSignalsByDate()
{
   int n = ArraySize(g_signals);
   for(int i = 0; i < n - 1; i++)
   {
      for(int j = 0; j < n - i - 1; j++)
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
void CreateChannelStats(string filename, int count)
{
   int sz = ArraySize(g_channels);
   ArrayResize(g_channels, sz + 1);
   g_channels[sz].name = filename;
   g_channels[sz].total_signals = count;
   g_channels[sz].executed = 0;
   g_channels[sz].wins = 0;
   g_channels[sz].losses = 0;
   g_channels[sz].be_count = 0;
   g_channels[sz].total_pnl = 0;
   g_channels[sz].max_drawdown = 0;
   g_channels[sz].peak_pnl = 0;
   g_channels[sz].tp_fixed_count = 0;
   g_channels[sz].tp_trigger_count = 0;
   g_channels[sz].daily_limit_count = 0;
}

//+------------------------------------------------------------------+
//| TRAITEMENT DES SIGNAUX                                           |
//+------------------------------------------------------------------+
void ProcessSignals()
{
   datetime current_time = TimeCurrent();

   for(int i = 0; i < ArraySize(g_signals); i++)
   {
      if(g_signals[i].dt == 0 || g_signals[i].dt > current_time)
         continue;

      // Vérifier si déjà traité (chercher dans les trades actifs et fermés)
      if(IsSignalProcessed(g_signals[i]))
         continue;

      // Filtre horaire
      if(InpTimeFilter && !IsWithinTradingHours(g_signals[i].dt))
         continue;

      // Spread filter
      if(InpSpread_Filter && !CheckSpread(_Symbol))
         continue;

      // Exécuter le signal
      ExecuteSignal(g_signals[i]);

      // Marquer comme traité en avançant l'index
      // (on ne le re-traitera pas car dt <= current_time reste vrai)
   }
}

//+------------------------------------------------------------------+
//| Vérifier si un signal a déjà été traité                          |
//+------------------------------------------------------------------+
bool IsSignalProcessed(const SignalData &sig)
{
   // Chercher dans les trades actifs
   for(int i = 0; i < ArraySize(g_active); i++)
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
bool CheckSpread(string symbol)
{
   long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
   return (spread <= InpMaxSpreadPoints);
}

//+------------------------------------------------------------------+
//| EXÉCUTION D'UN SIGNAL                                            |
//+------------------------------------------------------------------+
void ExecuteSignal(const SignalData &sig)
{
   double current_price = GetCurrentPrice(sig.direction);
   if(current_price == 0)
      return;

   // Déterminer le scénario
   string scenario = "";
   bool is_zone = (sig.zone_low != sig.zone_high);
   bool is_quick_alert = (sig.tp_count == 0 && sig.sl == 0);

   // Quick Alert
   if(is_quick_alert && InpEnableQuickAlert)
   {
      scenario = "QA";
      ExecuteQuickAlert(sig, current_price, scenario);
      return;
   }

   // Prix Unique
   if(!is_zone && InpEnablePrixUnique)
   {
      if(IsPrixUnique_S1(sig, current_price))
         scenario = "PU-S1";
      else if(IsPrixUnique_S2(sig, current_price))
         scenario = "PU-S2";
      else
         return; // Hors zone

      ExecutePrixUnique(sig, current_price, scenario);
      return;
   }

   // Zone
   if(is_zone && InpEnableZone)
   {
      if(IsCAS1(sig, current_price))
         scenario = "C1";
      else if(IsCAS2a(sig, current_price))
         scenario = "C2-a";
      else if(IsCAS2b(sig, current_price))
         scenario = "C2-b";
      else
         return; // Hors zone

      ExecuteZone(sig, current_price, scenario);
      return;
   }
}

//+------------------------------------------------------------------+
//| Prix Unique — S1 (MARKET)                                        |
//+------------------------------------------------------------------+
bool IsPrixUnique_S1(const SignalData &sig, double price)
{
   if(sig.direction == "BUY")
      return (sig.sl < price && price < sig.zone_low);
   else
      return (sig.zone_low < price && price < sig.sl);
}

//+------------------------------------------------------------------+
//| Prix Unique — S2 (LIMIT)                                         |
//+------------------------------------------------------------------+
bool IsPrixUnique_S2(const SignalData &sig, double price)
{
   if(sig.tp_count == 0) return false;
   double tp1 = sig.tps[0];
   if(sig.direction == "BUY")
      return (sig.zone_low < price && price < tp1);
   else
      return (tp1 < price && price < sig.zone_low);
}

//+------------------------------------------------------------------+
//| CAS 1 — Prix dans la zone                                        |
//+------------------------------------------------------------------+
bool IsCAS1(const SignalData &sig, double price)
{
   return (sig.zone_low <= price && price <= sig.zone_high);
}

//+------------------------------------------------------------------+
//| CAS 2-a — Prix entre TP1 et zone                                 |
//+------------------------------------------------------------------+
bool IsCAS2a(const SignalData &sig, double price)
{
   if(sig.tp_count < 1) return false;
   double tp1 = sig.tps[0];
   if(sig.direction == "BUY")
      return (sig.zone_high < price && price < tp1);
   else
      return (tp1 < price && price < sig.zone_low);
}

//+------------------------------------------------------------------+
//| CAS 2-b — Prix entre TP1 et TP2                                  |
//+------------------------------------------------------------------+
bool IsCAS2b(const SignalData &sig, double price)
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
//| EXÉCUTION PRIX UNIQUE                                            |
//+------------------------------------------------------------------+
void ExecutePrixUnique(const SignalData &sig, double price, string scenario)
{
   double sl_price = CalculateSL(sig, price);
   double tp_price = GetTPFinal(sig);
   double lot = InpLotUnique;

   ulong ticket = 0;

   if(scenario == "PU-S1")
   {
      // MARKET
      ticket = OpenMarketOrder(sig.direction, lot, tp_price, sl_price,
                               "CH-PU-S1");
   }
   else if(scenario == "PU-S2")
   {
      // LIMIT @ entry
      ticket = OpenLimitOrder(sig.direction, lot, sig.zone_low, tp_price,
                              sl_price, "CH-PU-S2");
   }

   if(ticket > 0)
   {
      RegisterTrade(sig, ticket, price, scenario, lot);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed", 0);
   }
}

//+------------------------------------------------------------------+
//| EXÉCUTION ZONE                                                   |
//+------------------------------------------------------------------+
void ExecuteZone(const SignalData &sig, double price, string scenario)
{
   double sl_price = CalculateSL(sig, price);
   double tp_price = GetTPFinal(sig);
   double lot_half = InpLotTotal / 2.0;

   ulong ticket1 = 0, ticket2 = 0;

   if(scenario == "C1")
   {
      // CAS 1 : 50% MARKET + 50% LIMIT
      ticket1 = OpenMarketOrder(sig.direction, lot_half, tp_price, sl_price,
                                "CH-C1-MKT");

      // LIMIT entre zone_high et SL
      double limit_price = 0;
      if(sig.direction == "BUY")
         limit_price = (sig.zone_low + sig.sl) / 2.0;
      else
         limit_price = (sig.zone_high + sig.sl) / 2.0;

      ticket2 = OpenLimitOrder(sig.direction, lot_half, limit_price, tp_price,
                               sl_price, "CH-C1-LMT");
   }
   else if(scenario == "C2-a")
   {
      // CAS 2-a : 50% MARKET + 50% LIMIT @ l'autre bout de la zone
      ticket1 = OpenMarketOrder(sig.direction, lot_half, tp_price, sl_price,
                                "CH-C2-MKT");

      double limit_price = (sig.direction == "BUY") ? sig.zone_low : sig.zone_high;
      ticket2 = OpenLimitOrder(sig.direction, lot_half, limit_price, tp_price,
                               sl_price, "CH-C2-LMT");
   }
   else if(scenario == "C2-b")
   {
      // CAS 2-b : 2 LIMITS
      double zone_edge = (sig.direction == "BUY") ? sig.zone_high : sig.zone_low;
      double zone_opp = (sig.direction == "BUY") ? sig.zone_low : sig.zone_high;

      ticket1 = OpenLimitOrder(sig.direction, lot_half, zone_edge, tp_price,
                               sl_price, "CH-C2-L1");
      ticket2 = OpenLimitOrder(sig.direction, lot_half, zone_opp, tp_price,
                               sl_price, "CH-C2-L2");
   }

   if(ticket1 > 0 || ticket2 > 0)
   {
      RegisterTradeZone(sig, ticket1, ticket2, price, scenario, lot_half);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed", 0);
   }
}

//+------------------------------------------------------------------+
//| EXÉCUTION QUICK ALERT                                            |
//+------------------------------------------------------------------+
void ExecuteQuickAlert(const SignalData &sig, double price, string scenario)
{
   // Générer SL/TP provisoires (SL_QuickAlert est en $, directement en prix)
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

   // Vérifier si le prix est entre SL et entry
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
      RegisterTrade(sig, ticket, price, scenario, lot);
      g_total_executed++;
      UpdateChannelStats(sig.source_file, "executed", 0);
   }
}

//+------------------------------------------------------------------+
//| CALCUL SL                                                        |
//+------------------------------------------------------------------+
double CalculateSL(const SignalData &sig, double entry_price)
{
   double sl = sig.sl;

   // Si SL personnalisé activé
   if(InpSL_Custom)
   {
      bool is_zone = (sig.zone_low != sig.zone_high);
      bool is_qa = (sig.tp_count == 0 && sig.sl == 0);

      if(is_qa)
      {
         // Quick Alert : SL provisoire
         double dist = InpSL_QuickAlert;
         if(sig.direction == "BUY")
            sl = sig.zone_low - dist;
         else
            sl = sig.zone_low + dist;
      }
      else if(is_zone)
      {
         // Zone : SL_PlusProche = distance max ($) entre zone_edge et SL
         // Trouver le zone_edge le plus proche du SL
         double zone_edge;
         if(sig.direction == "BUY")
            zone_edge = sig.zone_low;   // zone basse → SL en dessous
         else
            zone_edge = sig.zone_high;  // zone haute → SL au-dessus

         double distance = MathAbs(sl - zone_edge);

         if(distance > InpSL_PlusProche)
         {
            // Resserrer le SL
            if(sig.direction == "BUY")
               sl = zone_edge - InpSL_PlusProche;
            else
               sl = zone_edge + InpSL_PlusProche;
         }
         // Sinon garder le SL du signal (déjà assez proche)
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
double GetTPFinal(const SignalData &sig)
{
   if(sig.tp_count == 0)
      return 0;

   // TP final = dernier TP
   double tp = sig.tps[sig.tp_count - 1];

   // Trier dans le bon ordre (BUY asc, SELL desc)
   if(sig.direction == "BUY")
   {
      // Trier croissant
      for(int i = 0; i < sig.tp_count - 1; i++)
         for(int j = 0; j < sig.tp_count - i - 1; j++)
            if(sig.tps[j] > sig.tps[j + 1])
            {
               double tmp = sig.tps[j];
               sig.tps[j] = sig.tps[j + 1];
               sig.tps[j + 1] = tmp;
            }
      tp = sig.tps[sig.tp_count - 1]; // Plus haut
   }
   else
   {
      // Trier décroissant
      for(int i = 0; i < sig.tp_count - 1; i++)
         for(int j = 0; j < sig.tp_count - i - 1; j++)
            if(sig.tps[j] < sig.tps[j + 1])
            {
               double tmp = sig.tps[j];
               sig.tps[j] = sig.tps[j + 1];
               sig.tps[j + 1] = tmp;
            }
      tp = sig.tps[sig.tp_count - 1]; // Plus bas
   }

   return NormalizeDouble(tp, _Digits);
}

//+------------------------------------------------------------------+
//| ORDRES                                                           |
//+------------------------------------------------------------------+
ulong OpenMarketOrder(string direction, double lot, double tp, double sl, string comment)
{
   if(!CheckVolume(lot)) return 0;

   bool ok = false;
   if(direction == "BUY")
      ok = trade.Buy(lot, _Symbol, 0, sl, tp, comment);
   else
      ok = trade.Sell(lot, _Symbol, 0, sl, tp, comment);

   if(ok)
   {
      ulong ticket = trade.ResultOrder();
      Print("✅ MARKET ", direction, " ", _Symbol, " lot=", lot,
            " @", trade.ResultPrice(), " TP=", tp, " SL=", sl, " #", ticket);
      return ticket;
   }

   Print("❌ Échec MARKET ", direction, " ", trade.ResultRetcode());
   return 0;
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
ulong OpenLimitOrder(string direction, double lot, double price, double tp, double sl, string comment)
{
   if(!CheckVolume(lot)) return 0;

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
   {
      ulong ticket = trade.ResultOrder();
      Print("✅ LIMIT ", direction, " ", _Symbol, " lot=", lot,
            " @", price, " TP=", tp, " SL=", sl, " #", ticket);
      return ticket;
   }

   Print("❌ Échec LIMIT ", direction, " @", price, " ", trade.ResultRetcode());
   return 0;
}

//+------------------------------------------------------------------+
//| Vérifier le volume                                               |
//+------------------------------------------------------------------+
bool CheckVolume(double lot)
{
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   return (lot >= min_lot && lot <= max_lot);
}

//+------------------------------------------------------------------+
//| ENREGISTREMENT DES TRADES                                        |
//+------------------------------------------------------------------+
void RegisterTrade(const SignalData &sig, ulong ticket, double price,
                   string scenario, double lot)
{
   int sz = ArraySize(g_active);
   ArrayResize(g_active, sz + 1);

   g_active[sz].id = IntegerToString(sig.dt) + "_" + sig.direction;
   g_active[sz].signal = sig;
   ArrayResize(g_active[sz].tickets, 1);
   g_active[sz].tickets[0] = ticket;
   ArrayResize(g_active[sz].pending_orders, 0);
   ArrayResize(g_active[sz].entry_prices, 1);
   g_active[sz].entry_prices[0] = price;
   ArrayResize(g_active[sz].roles, 1);
   g_active[sz].roles[0] = scenario;
   g_active[sz].be_activated = false;
   g_active[sz].be_price = 0;
   g_active[sz].target_gain = InpTPFixed_GainUSD;
   g_active[sz].open_time = TimeCurrent();
   g_active[sz].scenario = scenario;
   g_active[sz].closed = false;
   g_active[sz].pnl = 0;

   Print("📌 Trade enregistré: ", scenario, " ", sig.direction, " #", ticket);
}

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void RegisterTradeZone(const SignalData &sig, ulong ticket1, ulong ticket2,
                       double price, string scenario, double lot)
{
   int sz = ArraySize(g_active);
   ArrayResize(g_active, sz + 1);

   g_active[sz].id = IntegerToString(sig.dt) + "_" + sig.direction;
   g_active[sz].signal = sig;

   int ticket_count = 0;
   if(ticket1 > 0) ticket_count++;
   if(ticket2 > 0) ticket_count++;

   ArrayResize(g_active[sz].tickets, ticket_count);
   ArrayResize(g_active[sz].entry_prices, ticket_count);
   ArrayResize(g_active[sz].roles, ticket_count);

   int idx = 0;
   if(ticket1 > 0)
   {
      g_active[sz].tickets[idx] = ticket1;
      g_active[sz].entry_prices[idx] = price;
      g_active[sz].roles[idx] = scenario + "-MKT";
      idx++;
   }
   if(ticket2 > 0)
   {
      g_active[sz].tickets[idx] = ticket2;
      g_active[sz].entry_prices[idx] = price;
      g_active[sz].roles[idx] = scenario + "-LMT";
   }

   // Ordres pending
   ArrayResize(g_active[sz].pending_orders, 0);

   g_active[sz].be_activated = false;
   g_active[sz].be_price = 0;
   g_active[sz].target_gain = InpTPFixed_GainUSD * ticket_count;
   g_active[sz].open_time = TimeCurrent();
   g_active[sz].scenario = scenario;
   g_active[sz].closed = false;
   g_active[sz].pnl = 0;

   Print("📌 Trade zone enregistré: ", scenario, " ", sig.direction,
         " tickets=", ticket_count);
}

//+------------------------------------------------------------------+
//| GESTION DES TRADES ACTIFS                                        |
//+------------------------------------------------------------------+
void ManageActiveTrades()
{
   for(int i = ArraySize(g_active) - 1; i >= 0; i--)
   {
      if(g_active[i].closed)
         continue;

      // Compter les positions ouvertes
      int open_count = 0;
      double total_pnl = 0;
      double min_pnl = DBL_MAX;

      for(int t = 0; t < ArraySize(g_active[i].tickets); t++)
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

      // Aucune position ouverte → trade fermé
      if(open_count == 0)
      {
         CloseTrade(i, "CLOSED");
         continue;
      }

      // === BE ===
      if(InpBE_Enabled && !g_active[i].be_activated && min_pnl >= InpPNL_Trigger)
      {
         ApplyBE(i);
      }

      // === TP_FIXED ===
      if(InpTPFixed_Enabled && g_active[i].be_activated)
      {
         double target = g_active[i].target_gain;
         if(total_pnl >= target)
         {
            CloseTrade(i, "TP_FIXED");
            continue;
         }
      }

      // === TP_TRIGGER (pending orders) ===
      if(InpTPTrigger_Enabled)
      {
         CheckTPTrigger(i);
      }

      // === Expiration des ordres pending ===
      CheckOrderExpiry(i);
   }
}

//+------------------------------------------------------------------+
//| Appliquer le BE                                                  |
//+------------------------------------------------------------------+
void ApplyBE(int idx)
{
   int open_count = 0;
   for(int t = 0; t < ArraySize(g_active[idx].tickets); t++)
   {
      if(PositionSelectByTicket(g_active[idx].tickets[t]))
         open_count++;
   }

   double be_price = 0;

   if(open_count == 1)
   {
      // 1 position → SL @ entry
      be_price = g_active[idx].entry_prices[0];
   }
   else if(open_count == 2)
   {
      // 2 positions → SL @ median
      be_price = (g_active[idx].entry_prices[0] + g_active[idx].entry_prices[1]) / 2.0;
   }
   else
      return;

   be_price = NormalizeDouble(be_price, _Digits);

   // Modifier le SL de toutes les positions ouvertes
   int modified = 0;
   for(int t = 0; t < ArraySize(g_active[idx].tickets); t++)
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

      // Annuler les ordres pending
      if(InpBE_CancelPending)
         CancelPendingForEntry(idx);

      // Recalculer le target_gain
      g_active[idx].target_gain = InpTPFixed_GainUSD * open_count;

      Print("🔒 BE activé @", be_price, " | ", open_count, " POS | Target=",
            g_active[idx].target_gain);

      UpdateChannelStats(g_active[idx].signal.source_file, "be_count", 0);
   }
}

//+------------------------------------------------------------------+
//| Annuler les ordres pending d'un trade                            |
//+------------------------------------------------------------------+
void CancelPendingForEntry(int idx)
{
   for(int o = ArraySize(g_active[idx].pending_orders) - 1; o >= 0; o--)
   {
      ulong order_ticket = g_active[idx].pending_orders[o];
      if(OrderSelect(order_ticket))
      {
         trade.OrderDelete(order_ticket);
         Print("🗑️ Pending annulé: #", order_ticket);
      }
   }
   ArrayResize(g_active[idx].pending_orders, 0);
}

//+------------------------------------------------------------------+
//| Vérifier TP_TRIGGER                                              |
//+------------------------------------------------------------------+
void CheckTPTrigger(int idx)
{
   // Vérifier s'il reste des ordres pending
   if(ArraySize(g_active[idx].pending_orders) == 0)
      return;

   // Obtenir le TP_TRIGGER
   SignalData sig = g_active[idx].signal;
   int trigger_idx = InpTPTrigger_Index;
   if(trigger_idx >= sig.tp_count)
      trigger_idx = sig.tp_count - 1;
   if(trigger_idx < 0)
      return;

   double tp_trigger = sig.tps[trigger_idx];

   // Vérifier si le prix a atteint le trigger
   double current_price = GetCurrentPrice(sig.direction);
   bool triggered = false;

   if(sig.direction == "BUY" && current_price >= tp_trigger)
      triggered = true;
   else if(sig.direction == "SELL" && current_price <= tp_trigger)
      triggered = true;

   if(triggered)
   {
      int pending_count = ArraySize(g_active[idx].pending_orders);
      CancelPendingForEntry(idx);

      Print("⚡ TP_TRIGGER @", tp_trigger, " | ", pending_count, " ordres annulés");
      UpdateChannelStats(g_active[idx].signal.source_file, "tp_trigger_count", 0);

      // Si aucune position ouverte, fermer le trade
      int open_count = 0;
      for(int t = 0; t < ArraySize(g_active[idx].tickets); t++)
      {
         if(PositionSelectByTicket(g_active[idx].tickets[t]))
            open_count++;
      }

      if(open_count == 0)
         CloseTrade(idx, "TP_TRIGGER");
   }
}

//+------------------------------------------------------------------+
//| Vérifier l'expiration des ordres                                 |
//+------------------------------------------------------------------+
void CheckOrderExpiry(int idx)
{
   for(int o = ArraySize(g_active[idx].pending_orders) - 1; o >= 0; o--)
   {
      ulong order_ticket = g_active[idx].pending_orders[o];
      if(!OrderSelect(order_ticket))
      {
         // L'ordre n'existe plus (expiré ou rempli)
         // Vérifier s'il a été rempli
         ulong pos_ticket = FindFilledPosition(order_ticket);
         if(pos_ticket > 0)
         {
            // Ajouter la position
            int sz = ArraySize(g_active[idx].tickets);
            ArrayResize(g_active[idx].tickets, sz + 1);
            g_active[idx].tickets[sz] = pos_ticket;

            // Ajouter le prix d'entrée
            if(PositionSelectByTicket(pos_ticket))
            {
               ArrayResize(g_active[idx].entry_prices, sz + 1);
               g_active[idx].entry_prices[sz] = PositionGetDouble(POSITION_PRICE_OPEN);
            }

            Print("🔵 Limit remplie: #", order_ticket, " → Position #", pos_ticket);
         }

         // Retirer de la liste des pending
         for(int j = o; j < ArraySize(g_active[idx].pending_orders) - 1; j++)
            g_active[idx].pending_orders[j] = g_active[idx].pending_orders[j + 1];
         ArrayResize(g_active[idx].pending_orders, ArraySize(g_active[idx].pending_orders) - 1);
      }
   }
}

//+------------------------------------------------------------------+
//| Trouver une position remplie depuis un ordre pending             |
//+------------------------------------------------------------------+
ulong FindFilledPosition(ulong order_ticket)
{
   // Chercher dans l'historique des deals
   datetime from = TimeCurrent() - 3600; // Dernière heure
   datetime to = TimeCurrent();

   if(HistorySelect(from, to))
   {
      int deals = HistoryDealsTotal();
      for(int i = 0; i < deals; i++)
      {
         ulong deal = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(deal, DEAL_ENTRY) == DEAL_ENTRY_IN)
         {
            long deal_magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
            if(deal_magic == InpMagicNumber)
            {
               ulong pos_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
               if(PositionSelectByTicket(pos_id))
                  return pos_id;
            }
         }
      }
   }
   return 0;
}

//+------------------------------------------------------------------+
//| Fermer un trade                                                  |
//+------------------------------------------------------------------+
void CloseTrade(int idx, string reason)
{
   double total_pnl = 0;

   // Fermer toutes les positions ouvertes
   for(int t = 0; t < ArraySize(g_active[idx].tickets); t++)
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

   // Mettre à jour les stats
   string src = g_active[idx].signal.source_file;
   UpdateChannelStats(src, "pnl", total_pnl);

   if(total_pnl > 0)
      UpdateChannelStats(src, "wins", 0);
   else if(total_pnl < 0)
      UpdateChannelStats(src, "losses", 0);

   if(reason == "TP_FIXED")
      UpdateChannelStats(src, "tp_fixed_count", 0);

   g_daily_pnl += total_pnl;

   Print("📊 Trade fermé: ", reason, " PnL=", total_pnl, " | ",
         g_active[idx].scenario, " ", g_active[idx].signal.direction);
}

//+------------------------------------------------------------------+
//| Vérifier les ordres pending                                      |
//+------------------------------------------------------------------+
void CheckPendingOrders()
{
   // Géré dans CheckOrderExpiry via ManageActiveTrades
}

//+------------------------------------------------------------------+
//| GESTION QUOTIDIENNE                                              |
//+------------------------------------------------------------------+
void CheckDailyReset()
{
   MqlDateTime mdt;
   TimeToStruct(TimeCurrent(), mdt);

   datetime today_start = StringToTime(
      IntegerToString(mdt.year) + "." +
      IntegerToString(mdt.mon) + "." +
      IntegerToString(mdt.day) + " " +
      IntegerToString(InpStartHour) + ":00"
   );

   if(g_daily_reset < today_start && TimeCurrent() >= today_start)
   {
      g_daily_pnl = 0;
      g_daily_reset = today_start;
      Print("🔄 Reset quotidien à ", InpStartHour, "h UTC");
   }
}

//+------------------------------------------------------------------+
//| Vérifier la limite quotidienne                                   |
//+------------------------------------------------------------------+
bool CheckDailyLimit()
{
   if(g_daily_pnl >= InpDailyProfitLimit)
   {
      // Fermer tous les trades
      for(int i = ArraySize(g_active) - 1; i >= 0; i--)
      {
         if(!g_active[i].closed)
            CloseTrade(i, "DAILY_LIMIT");
      }
      Print("🚨 Limite quotidienne atteinte: ", g_daily_pnl, "$");
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| MISE À JOUR DES STATS                                            |
//+------------------------------------------------------------------+
void UpdateChannelStats(string filename, string field, double value)
{
   for(int i = 0; i < ArraySize(g_channels); i++)
   {
      if(g_channels[i].name == filename)
      {
         if(field == "executed")     g_channels[i].executed++;
         else if(field == "wins")    g_channels[i].wins++;
         else if(field == "losses")  g_channels[i].losses++;
         else if(field == "be_count") g_channels[i].be_count++;
         else if(field == "tp_fixed_count") g_channels[i].tp_fixed_count++;
         else if(field == "tp_trigger_count") g_channels[i].tp_trigger_count++;
         else if(field == "daily_limit_count") g_channels[i].daily_limit_count++;
         else if(field == "pnl")
         {
            g_channels[i].total_pnl += value;
            if(g_channels[i].total_pnl > g_channels[i].peak_pnl)
               g_channels[i].peak_pnl = g_channels[i].total_pnl;
            double dd = g_channels[i].peak_pnl - g_channels[i].total_pnl;
            if(dd > g_channels[i].max_drawdown)
               g_channels[i].max_drawdown = dd;
         }
         break;
      }
   }
}

//+------------------------------------------------------------------+
//| GÉNÉRATION DU RAPPORT                                            |
//+------------------------------------------------------------------+
void GenerateReport()
{
   string report = "";
   report += "═══════════════════════════════════════════════════\n";
   report += "  GOLD SIGNAL BACKTESTER — RAPPORT FINAL\n";
   report += "═══════════════════════════════════════════════════\n\n";

   report += "Paramètres:\n";
   report += "  Lot Total: " + DoubleToString(InpLotTotal) + "\n";
   report += "  Lot Unique: " + DoubleToString(InpLotUnique) + "\n";
   report += "  Max Positions: " + IntegerToString(InpMaxPositions) + "\n";
   report += "  BE Trigger: " + DoubleToString(InpPNL_Trigger) + " pts\n";
   report += "  TP_FIXED Gain: " + DoubleToString(InpTPFixed_GainUSD) + " pts/pos\n";
   report += "  Daily Limit: " + DoubleToString(InpDailyProfitLimit) + "$\n";
   report += "  Spread Max: " + DoubleToString(InpMaxSpreadPoints) + " pts\n";
   report += "  Slippage: " + IntegerToString(InpSlippage) + " pts\n";
   report += "  Time Filter: " + (InpTimeFilter ? "ON" : "OFF") + "\n";
   report += "  SL Custom: " + (InpSL_Custom ? "ON" : "OFF") + "\n\n";

   report += "Signaux chargés: " + IntegerToString(ArraySize(g_signals)) + "\n";
   report += "Signaux exécutés: " + IntegerToString(g_total_executed) + "\n\n";

   // Rapport par channel
   for(int i = 0; i < ArraySize(g_channels); i++)
   {
      ChannelStats cs = g_channels[i];
      report += "───────────────────────────────────────────────────\n";
      report += "Channel: " + cs.name + "\n";
      report += "  Signaux analysés: " + IntegerToString(cs.total_signals) + "\n";
      report += "  Signaux exécutés: " + IntegerToString(cs.executed) + "\n";

      int total_trades = cs.wins + cs.losses + cs.be_count;
      double win_rate = (total_trades > 0) ? (double)cs.wins / total_trades * 100 : 0;
      double profit_factor = 0;
      double gross_profit = 0, gross_loss = 0;

      // Calculer le profit factor depuis les trades fermés
      for(int t = 0; t < ArraySize(g_active); t++)
      {
         if(g_active[t].closed && g_active[t].signal.source_file == cs.name)
         {
            if(g_active[t].pnl > 0) gross_profit += g_active[t].pnl;
            else gross_loss += MathAbs(g_active[t].pnl);
         }
      }
      profit_factor = (gross_loss > 0) ? gross_profit / gross_loss : 0;

      report += "  Trades: " + IntegerToString(total_trades) + "\n";
      report += "  Wins: " + IntegerToString(cs.wins) + " (" + DoubleToString(win_rate, 1) + "%)\n";
      report += "  Losses: " + IntegerToString(cs.losses) + "\n";
      report += "  BE: " + IntegerToString(cs.be_count) + "\n";
      report += "  PnL total: " + DoubleToString(cs.total_pnl, 2) + "$\n";
      report += "  Max Drawdown: " + DoubleToString(cs.max_drawdown, 2) + "$\n";
      report += "  Profit Factor: " + DoubleToString(profit_factor, 2) + "\n";
      report += "  TP_FIXED: " + IntegerToString(cs.tp_fixed_count) + "\n";
      report += "  TP_TRIGGER: " + IntegerToString(cs.tp_trigger_count) + "\n";
      report += "  DAILY_LIMIT: " + IntegerToString(cs.daily_limit_count) + "\n\n";
   }

   // Résumé global
   report += "═══════════════════════════════════════════════════\n";
   report += "  RÉSUMÉ GLOBAL\n";
   report += "═══════════════════════════════════════════════════\n";
   report += "  PnL total: " + DoubleToString(g_daily_pnl, 2) + "$\n";
   report += "  Channels analysés: " + IntegerToString(ArraySize(g_channels)) + "\n";

   // Classement
   report += "\n  CLASSEMENT:\n";
   for(int i = 0; i < ArraySize(g_channels); i++)
   {
      int rank = i + 1;
      string medal = (rank == 1) ? "🥇" : (rank == 2) ? "🥈" : (rank == 3) ? "🥉" : "  ";
      report += "  " + medal + " " + g_channels[i].name +
                " | PnL=" + DoubleToString(g_channels[i].total_pnl, 2) + "$" +
                " | Trades=" + IntegerToString(g_channels[i].wins + g_channels[i].losses) +
                "\n";
   }

   // Sauvegarder le rapport
   g_report = report;
   Print(report);

   // Écrire dans un fichier
   int handle = FileOpen("BacktestReport.txt", FILE_WRITE | FILE_TXT);
   if(handle != INVALID_HANDLE)
   {
      FileWriteString(handle, report);
      FileClose(handle);
      Print("📄 Rapport sauvegardé: BacktestReport.txt");
   }
}
//+------------------------------------------------------------------+
