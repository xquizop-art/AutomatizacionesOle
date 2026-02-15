//+------------------------------------------------------------------+
//|                                      AsiaRangeReversal_M5.mq5    |
//|                        Reversa Rango Asia — BTC/USD M5            |
//|                                                                    |
//|  Estrategia:                                                       |
//|    - Rango Asia: 00:00–06:59 (hora Madrid CET/CEST)               |
//|    - ATR_Asia: media simple de TR de velas Asia                    |
//|    - Ventana entradas: 07:30–12:00 (Madrid)                       |
//|    - SELL si Bid >= AsiaHigh, BUY si Ask <= AsiaLow               |
//|    - SL/TP: D = ATR_Multiplier * ATR_Asia, RR 1:1                |
//|    - Max 1 trade/dia                                               |
//|    - Filtros: min velas, rango minimo, spread maximo, outliers    |
//+------------------------------------------------------------------+
#property copyright "AutomatizacionesOle"
#property link      "https://github.com/xquizop-art/AutomatizacionesOle"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| Inputs                                                            |
//+------------------------------------------------------------------+
input group "=== Parametros de la Estrategia ==="
input double   InpATRMultiplier       = 2.0;    // Multiplicador ATR para SL/TP
input int      InpMinAsiaBars         = 78;     // Minimo velas Asia requeridas (de 84)
input double   InpMinRangeRatio       = 0.8;    // Ratio minimo AsiaRange/ATR
input double   InpMaxSpreadRatio      = 0.25;   // Ratio maximo Spread/ATR
input int      InpMaxTradesPerDay     = 1;      // Max trades por dia
input double   InpWickOutlierMult     = 5.0;    // Multiplicador outlier de mechas

input group "=== Configuracion de Horario (Europe/Madrid) ==="
input int      InpAsiaStartHour       = 0;      // Hora inicio Asia (Madrid)
input int      InpAsiaEndHour         = 7;      // Hora fin Asia / congelacion (Madrid)
input int      InpEntryStartHour      = 7;      // Hora inicio entradas (Madrid)
input int      InpEntryStartMin       = 30;     // Minuto inicio entradas (Madrid)
input int      InpEntryEndHour        = 12;     // Hora fin entradas (Madrid)
input int      InpEntryEndMin         = 0;      // Minuto fin entradas (Madrid)

input group "=== Configuracion de Operativa ==="
input double   InpLotSize             = 0.01;   // Tamano de lote
input int      InpMagicNumber         = 20260215; // Magic number
input int      InpSlippage            = 30;     // Slippage maximo (puntos)
input string   InpComment             = "AsiaRangeReversal"; // Comentario de ordenes

input group "=== Offset Horario ==="
input int      InpBrokerGMTOffset     = 2;      // GMT offset del servidor broker (ej: 2 para UTC+2)
// Madrid = UTC+1 (CET) o UTC+2 (CEST). Ajusta segun tu broker.
// Si broker=UTC+2 y Madrid=UTC+1 (invierno): offset servidor - offset Madrid = +1h
// Si broker=UTC+2 y Madrid=UTC+2 (verano): offset = 0h
// Se calcula automaticamente si el broker usa UTC+2 todo el año.
input bool     InpAutoDetectDST       = true;   // Auto-detectar horario verano/invierno

//+------------------------------------------------------------------+
//| Enumeracion de estados                                            |
//+------------------------------------------------------------------+
enum ENUM_ASIA_STATE
{
   STATE_BUILDING_ASIA  = 0,  // A: Construyendo rango (00:00-06:59)
   STATE_ASIA_FROZEN    = 1,  // B: Congelado, validando (07:00-07:29)
   STATE_SEEKING_ENTRY  = 2,  // C: Buscando entrada (07:30-12:00)
   STATE_DONE_FOR_DAY   = 3   // D: Cerrado para el dia
};

//+------------------------------------------------------------------+
//| Variables globales                                                 |
//+------------------------------------------------------------------+
CTrade         trade;

// Estado
ENUM_ASIA_STATE g_state          = STATE_BUILDING_ASIA;
datetime       g_currentDate     = 0;

// Niveles Asia
double         g_asiaHigh        = 0.0;
double         g_asiaLow         = 0.0;
double         g_asiaRange       = 0.0;
double         g_atrAsia         = 0.0;
int            g_asiaCandleCount = 0;

// Control operativa
bool           g_tradeTaken      = false;
int            g_tradesToday     = 0;
bool           g_dayEnabled      = false;

// Info del trade
double         g_entryPrice      = 0.0;
double         g_slPrice         = 0.0;
double         g_tpPrice         = 0.0;
string         g_entrySide       = "";

// Arrays para outlier filter
double         g_barHighs[];
double         g_barLows[];
double         g_barOpens[];
double         g_barCloses[];
double         g_barRanges[];

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippage);
   trade.SetTypeFilling(ORDER_FILLING_IOC);
   
   Print("═══ AsiaRangeReversal_M5 inicializado ═══");
   Print("  Symbol: ", _Symbol);
   Print("  ATR Multiplier: ", InpATRMultiplier);
   Print("  Min Asia Bars: ", InpMinAsiaBars);
   Print("  Lot Size: ", InpLotSize);
   Print("  Magic: ", InpMagicNumber);
   Print("  Broker GMT Offset: ", InpBrokerGMTOffset);
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("═══ AsiaRangeReversal_M5 detenido ═══");
   Print("  Estado: ", EnumToString(g_state));
   Print("  Trades hoy: ", g_tradesToday);
}

//+------------------------------------------------------------------+
//| Convertir hora del servidor a hora Madrid                          |
//+------------------------------------------------------------------+
int GetMadridOffset()
{
   if(!InpAutoDetectDST)
      return InpBrokerGMTOffset - 1; // CET = UTC+1 por defecto
   
   // Detectar DST de Madrid (ultimo domingo de marzo - ultimo domingo de octubre)
   MqlDateTime dt;
   TimeCurrent(dt);
   
   int month = dt.mon;
   int day   = dt.day;
   int dow   = dt.day_of_week; // 0=domingo
   
   bool isCEST = false; // Horario de verano Madrid (UTC+2)
   
   if(month > 3 && month < 10)
      isCEST = true;
   else if(month == 3)
   {
      // Ultimo domingo de marzo
      int lastSunday = day - dow;
      // Buscar el ultimo domingo del mes
      while(lastSunday + 7 <= 31) lastSunday += 7;
      if(day >= lastSunday) isCEST = true;
   }
   else if(month == 10)
   {
      // Ultimo domingo de octubre
      int lastSunday = day - dow;
      while(lastSunday + 7 <= 31) lastSunday += 7;
      if(day < lastSunday) isCEST = true;
   }
   
   int madridGMT = isCEST ? 2 : 1;
   return InpBrokerGMTOffset - madridGMT;
}

//+------------------------------------------------------------------+
//| Obtener hora Madrid desde hora del servidor                        |
//+------------------------------------------------------------------+
void GetMadridTime(int &madridHour, int &madridMin, MqlDateTime &madridDT)
{
   int offsetHours = GetMadridOffset();
   datetime serverTime = TimeCurrent();
   datetime madridTime = serverTime - offsetHours * 3600;
   
   TimeToStruct(madridTime, madridDT);
   madridHour = madridDT.hour;
   madridMin  = madridDT.min;
}

//+------------------------------------------------------------------+
//| Obtener fecha Madrid como datetime (solo fecha, 00:00)             |
//+------------------------------------------------------------------+
datetime GetMadridDate()
{
   MqlDateTime dt;
   int h, m;
   GetMadridTime(h, m, dt);
   dt.hour = 0;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
}

//+------------------------------------------------------------------+
//| Convertir hora Madrid a hora servidor (para CopyRates)             |
//+------------------------------------------------------------------+
datetime MadridToServer(int year, int month, int day, int hour, int min)
{
   MqlDateTime dt;
   dt.year  = year;
   dt.mon   = month;
   dt.day   = day;
   dt.hour  = hour;
   dt.min   = min;
   dt.sec   = 0;
   datetime madridTime = StructToTime(dt);
   int offsetHours = GetMadridOffset();
   return madridTime + offsetHours * 3600;
}

//+------------------------------------------------------------------+
//| Resetear estado diario                                             |
//+------------------------------------------------------------------+
void ResetDay(datetime newDate)
{
   MqlDateTime dt;
   TimeToStruct(newDate, dt);
   Print("─── Nuevo dia: ", dt.year, ".", dt.mon, ".", dt.day, " ───");
   
   g_currentDate     = newDate;
   g_state           = STATE_BUILDING_ASIA;
   g_asiaHigh        = 0.0;
   g_asiaLow         = DBL_MAX;
   g_asiaRange       = 0.0;
   g_atrAsia         = 0.0;
   g_asiaCandleCount = 0;
   g_tradeTaken      = false;
   g_tradesToday     = 0;
   g_dayEnabled      = false;
   g_entryPrice      = 0.0;
   g_slPrice         = 0.0;
   g_tpPrice         = 0.0;
   g_entrySide       = "";
}

//+------------------------------------------------------------------+
//| Calcular mediana de un array double                                |
//+------------------------------------------------------------------+
double MedianArray(double &arr[], int size)
{
   if(size <= 0) return 0.0;
   
   // Copiar para no alterar el original
   double sorted[];
   ArrayResize(sorted, size);
   ArrayCopy(sorted, arr, 0, 0, size);
   ArraySort(sorted);
   
   if(size % 2 == 0)
      return (sorted[size/2 - 1] + sorted[size/2]) / 2.0;
   else
      return sorted[size/2];
}

//+------------------------------------------------------------------+
//| Obtener velas Asia y aplicar filtro de outliers                    |
//|                                                                    |
//| Carga las M5 entre 00:00-06:59 Madrid del dia actual,             |
//| aplica filtro de mechas anomalas, y rellena los arrays globales.   |
//| Retorna: numero de velas cargadas (original, antes de filtro)      |
//+------------------------------------------------------------------+
int LoadAsiaBars(bool applyOutlierFilter)
{
   MqlDateTime madridDT;
   int madridH, madridM;
   GetMadridTime(madridH, madridM, madridDT);
   
   // Hora inicio: 00:00 Madrid de hoy → convertir a servidor
   datetime serverStart = MadridToServer(madridDT.year, madridDT.mon, madridDT.day,
                                          InpAsiaStartHour, 0);
   // Hora fin: 06:59 Madrid → convertir a servidor
   datetime serverEnd   = MadridToServer(madridDT.year, madridDT.mon, madridDT.day,
                                          InpAsiaEndHour, 0) - 60; // 06:59
   
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   
   int copied = CopyRates(_Symbol, PERIOD_M5, serverStart, serverEnd, rates);
   
   if(copied <= 0)
   {
      Print("[AsiaRange] No se pudieron cargar velas Asia. Error: ", GetLastError());
      return 0;
   }
   
   // Copiar a arrays de trabajo
   ArrayResize(g_barHighs,  copied);
   ArrayResize(g_barLows,   copied);
   ArrayResize(g_barOpens,  copied);
   ArrayResize(g_barCloses, copied);
   ArrayResize(g_barRanges, copied);
   
   for(int i = 0; i < copied; i++)
   {
      g_barHighs[i]  = rates[i].high;
      g_barLows[i]   = rates[i].low;
      g_barOpens[i]  = rates[i].open;
      g_barCloses[i] = rates[i].close;
      g_barRanges[i] = rates[i].high - rates[i].low;
   }
   
   // ── Filtro de outliers ──────────────────────────────
   if(applyOutlierFilter && copied >= 3)
   {
      double median = MedianArray(g_barRanges, copied);
      
      if(median > 0)
      {
         double threshold = InpWickOutlierMult * median;
         int outliers = 0;
         
         for(int i = 0; i < copied; i++)
         {
            if(g_barRanges[i] > threshold)
            {
               // Recortar H/L al cuerpo (open/close)
               double bodyHigh = MathMax(g_barOpens[i], g_barCloses[i]);
               double bodyLow  = MathMin(g_barOpens[i], g_barCloses[i]);
               
               PrintFormat("[AsiaRange] OUTLIER vela %d: H=%.2f L=%.2f rango=%.2f (mediana=%.2f, umbral=%.2f) → H=%.2f L=%.2f",
                           i, g_barHighs[i], g_barLows[i], g_barRanges[i],
                           median, threshold, bodyHigh, bodyLow);
               
               g_barHighs[i] = bodyHigh;
               g_barLows[i]  = bodyLow;
               g_barRanges[i] = bodyHigh - bodyLow;
               outliers++;
            }
         }
         
         if(outliers > 0)
            PrintFormat("[AsiaRange] Filtro outliers: %d vela(s) recortada(s) de %d totales",
                        outliers, copied);
      }
   }
   
   return copied;
}

//+------------------------------------------------------------------+
//| Construir rango Asia (Estado A)                                    |
//+------------------------------------------------------------------+
void BuildAsiaRange()
{
   int n = LoadAsiaBars(true); // con filtro outliers
   
   if(n <= 0) return;
   
   g_asiaCandleCount = n;
   g_asiaHigh = g_barHighs[0];
   g_asiaLow  = g_barLows[0];
   
   for(int i = 1; i < n; i++)
   {
      if(g_barHighs[i] > g_asiaHigh) g_asiaHigh = g_barHighs[i];
      if(g_barLows[i]  < g_asiaLow)  g_asiaLow  = g_barLows[i];
   }
   
   g_asiaRange = g_asiaHigh - g_asiaLow;
}

//+------------------------------------------------------------------+
//| Calcular ATR Asia                                                  |
//+------------------------------------------------------------------+
double CalculateAsiaATR(int n)
{
   if(n < 2) return 0.0;
   
   double sumTR = 0.0;
   
   for(int i = 0; i < n; i++)
   {
      double hl = g_barHighs[i] - g_barLows[i];
      double tr = hl;
      
      if(i > 0)
      {
         double hc = MathAbs(g_barHighs[i] - g_barCloses[i-1]);
         double lc = MathAbs(g_barLows[i]  - g_barCloses[i-1]);
         tr = MathMax(hl, MathMax(hc, lc));
      }
      
      sumTR += tr;
   }
   
   return sumTR / n;
}

//+------------------------------------------------------------------+
//| Congelar Asia y validar filtros (Transicion A→B)                   |
//+------------------------------------------------------------------+
void FreezeAsia()
{
   int n = LoadAsiaBars(true); // con filtro outliers
   
   if(n <= 0)
   {
      Print("[AsiaRange] Sin velas Asia. No se opera hoy.");
      g_dayEnabled = false;
      return;
   }
   
   // Calcular niveles finales
   g_asiaCandleCount = n;
   g_asiaHigh = g_barHighs[0];
   g_asiaLow  = g_barLows[0];
   
   for(int i = 1; i < n; i++)
   {
      if(g_barHighs[i] > g_asiaHigh) g_asiaHigh = g_barHighs[i];
      if(g_barLows[i]  < g_asiaLow)  g_asiaLow  = g_barLows[i];
   }
   
   g_asiaRange = g_asiaHigh - g_asiaLow;
   g_atrAsia   = CalculateAsiaATR(n);
   
   PrintFormat("═══ Asia congelada ═══");
   PrintFormat("  AsiaHigh  = %.5f", g_asiaHigh);
   PrintFormat("  AsiaLow   = %.5f", g_asiaLow);
   PrintFormat("  Range     = %.5f", g_asiaRange);
   PrintFormat("  ATR_Asia  = %.5f", g_atrAsia);
   PrintFormat("  Velas     = %d/84", g_asiaCandleCount);
   
   // ── Filtro 7.1: Min velas ──────────────────────────
   if(g_asiaCandleCount < InpMinAsiaBars)
   {
      PrintFormat("[AsiaRange] FILTRO: Pocas velas (%d < %d). No trade hoy.",
                  g_asiaCandleCount, InpMinAsiaBars);
      g_dayEnabled = false;
      return;
   }
   
   // ── Filtro: ATR > 0 ────────────────────────────────
   if(g_atrAsia <= 0.0)
   {
      Print("[AsiaRange] FILTRO: ATR_Asia = 0. No trade hoy.");
      g_dayEnabled = false;
      return;
   }
   
   // ── Filtro 7.2: Rango minimo ───────────────────────
   double minRange = InpMinRangeRatio * g_atrAsia;
   if(g_asiaRange < minRange)
   {
      PrintFormat("[AsiaRange] FILTRO: Rango (%.5f) < %.1f * ATR (%.5f). No trade hoy.",
                  g_asiaRange, InpMinRangeRatio, minRange);
      g_dayEnabled = false;
      return;
   }
   
   // ── Todo OK ────────────────────────────────────────
   g_dayEnabled = true;
   double D = InpATRMultiplier * g_atrAsia;
   PrintFormat("[AsiaRange] DIA HABILITADO | D = %.1f x %.5f = %.5f",
              InpATRMultiplier, g_atrAsia, D);
}

//+------------------------------------------------------------------+
//| Contar trades propios de hoy                                       |
//+------------------------------------------------------------------+
int CountTodayTrades()
{
   int count = 0;
   datetime todayStart = GetMadridDate();
   
   // Revisar historial de deals
   HistorySelect(todayStart - 24*3600, TimeCurrent() + 24*3600);
   
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      
      if(HistoryDealGetInteger(ticket, DEAL_MAGIC) == InpMagicNumber &&
         HistoryDealGetString(ticket, DEAL_SYMBOL) == _Symbol &&
         HistoryDealGetInteger(ticket, DEAL_ENTRY) == DEAL_ENTRY_IN)
      {
         count++;
      }
   }
   
   return count;
}

//+------------------------------------------------------------------+
//| Verificar si ya hay posicion abierta con nuestro magic              |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol)
      {
         if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Buscar entrada (Estado C)                                          |
//+------------------------------------------------------------------+
int CheckEntry()
{
   // 0 = HOLD, 1 = BUY, -1 = SELL
   
   if(g_asiaHigh <= 0 || g_asiaLow <= 0 || g_atrAsia <= 0)
      return 0;
   
   // Ya tenemos posicion abierta?
   if(HasOpenPosition())
      return 0;
   
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   
   if(bid <= 0 || ask <= 0) return 0;
   
   // ── Filtro 7.3: Spread ─────────────────────────────
   double spread = ask - bid;
   double maxSpread = InpMaxSpreadRatio * g_atrAsia;
   
   if(spread > maxSpread)
   {
      // Solo loguear de vez en cuando para no spamear
      static datetime lastSpreadLog = 0;
      if(TimeCurrent() - lastSpreadLog > 300) // cada 5 min
      {
         PrintFormat("[AsiaRange] Spread (%.5f) > max (%.5f). Esperando...",
                     spread, maxSpread);
         lastSpreadLog = TimeCurrent();
      }
      return 0;
   }
   
   double D = InpATRMultiplier * g_atrAsia;
   
   // ── Detectar toques ────────────────────────────────
   bool touchHigh = (bid >= g_asiaHigh);
   bool touchLow  = (ask <= g_asiaLow);
   
   // ── Desempate (ambos a la vez, muy raro) ───────────
   if(touchHigh && touchLow)
   {
      double mid = (bid + ask) / 2.0;
      double distHigh = MathAbs(mid - g_asiaHigh);
      double distLow  = MathAbs(mid - g_asiaLow);
      if(distHigh <= distLow)
         touchLow = false;
      else
         touchHigh = false;
   }
   
   // ── SELL: Bid >= AsiaHigh ──────────────────────────
   if(touchHigh)
   {
      double sl = g_asiaHigh + D;
      double tp = g_asiaHigh - D;
      
      // Normalizar precios
      int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      sl = NormalizeDouble(sl, digits);
      tp = NormalizeDouble(tp, digits);
      
      PrintFormat("═══ SELL SIGNAL ═══");
      PrintFormat("  Entry ≈ %.5f (AsiaHigh)", g_asiaHigh);
      PrintFormat("  Bid   = %.5f", bid);
      PrintFormat("  SL    = %.5f (+%.5f)", sl, D);
      PrintFormat("  TP    = %.5f (-%.5f)", tp, D);
      
      if(trade.Sell(InpLotSize, _Symbol, 0, sl, tp, InpComment))
      {
         g_tradeTaken = true;
         g_tradesToday++;
         g_entryPrice = bid;
         g_slPrice    = sl;
         g_tpPrice    = tp;
         g_entrySide  = "SELL";
         PrintFormat("[AsiaRange] ═══ SELL EJECUTADO @ %.5f ═══", bid);
         return -1;
      }
      else
      {
         PrintFormat("[AsiaRange] ERROR en SELL: %d - %s",
                     trade.ResultRetcode(), trade.ResultComment());
      }
   }
   
   // ── BUY: Ask <= AsiaLow ────────────────────────────
   if(touchLow)
   {
      double sl = g_asiaLow - D;
      double tp = g_asiaLow + D;
      
      int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      sl = NormalizeDouble(sl, digits);
      tp = NormalizeDouble(tp, digits);
      
      PrintFormat("═══ BUY SIGNAL ═══");
      PrintFormat("  Entry ≈ %.5f (AsiaLow)", g_asiaLow);
      PrintFormat("  Ask   = %.5f", ask);
      PrintFormat("  SL    = %.5f (-%.5f)", sl, D);
      PrintFormat("  TP    = %.5f (+%.5f)", tp, D);
      
      if(trade.Buy(InpLotSize, _Symbol, 0, sl, tp, InpComment))
      {
         g_tradeTaken = true;
         g_tradesToday++;
         g_entryPrice = ask;
         g_slPrice    = sl;
         g_tpPrice    = tp;
         g_entrySide  = "BUY";
         PrintFormat("[AsiaRange] ═══ BUY EJECUTADO @ %.5f ═══", ask);
         return 1;
      }
      else
      {
         PrintFormat("[AsiaRange] ERROR en BUY: %d - %s",
                     trade.ResultRetcode(), trade.ResultComment());
      }
   }
   
   return 0;
}

//+------------------------------------------------------------------+
//| Dibujar niveles Asia en el grafico                                 |
//+------------------------------------------------------------------+
void DrawAsiaLevels()
{
   if(g_asiaHigh <= 0 || g_asiaLow <= 0) return;
   
   color clrHigh = clrRed;
   color clrLow  = clrLime;
   
   // Asia High
   if(ObjectFind(0, "AsiaHigh") < 0)
      ObjectCreate(0, "AsiaHigh", OBJ_HLINE, 0, 0, g_asiaHigh);
   else
      ObjectSetDouble(0, "AsiaHigh", OBJPROP_PRICE, g_asiaHigh);
   ObjectSetInteger(0, "AsiaHigh", OBJPROP_COLOR, clrHigh);
   ObjectSetInteger(0, "AsiaHigh", OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, "AsiaHigh", OBJPROP_WIDTH, 2);
   ObjectSetString(0, "AsiaHigh", OBJPROP_TEXT,
                   StringFormat("Asia High %.5f", g_asiaHigh));
   
   // Asia Low
   if(ObjectFind(0, "AsiaLow") < 0)
      ObjectCreate(0, "AsiaLow", OBJ_HLINE, 0, 0, g_asiaLow);
   else
      ObjectSetDouble(0, "AsiaLow", OBJPROP_PRICE, g_asiaLow);
   ObjectSetInteger(0, "AsiaLow", OBJPROP_COLOR, clrLow);
   ObjectSetInteger(0, "AsiaLow", OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, "AsiaLow", OBJPROP_WIDTH, 2);
   ObjectSetString(0, "AsiaLow", OBJPROP_TEXT,
                   StringFormat("Asia Low %.5f", g_asiaLow));
   
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Mostrar panel informativo                                          |
//+------------------------------------------------------------------+
void ShowInfoPanel()
{
   string stateStr = "";
   switch(g_state)
   {
      case STATE_BUILDING_ASIA: stateStr = "A: Construyendo Asia";  break;
      case STATE_ASIA_FROZEN:   stateStr = "B: Asia Congelada";     break;
      case STATE_SEEKING_ENTRY: stateStr = "C: Buscando Entrada";   break;
      case STATE_DONE_FOR_DAY:  stateStr = "D: Cerrado";            break;
   }
   
   string info = StringFormat(
      "═══ Asia Range Reversal ═══\n"
      "Estado: %s\n"
      "Asia H: %.5f | L: %.5f\n"
      "Range: %.5f | ATR: %.5f\n"
      "Velas: %d | Habilitado: %s\n"
      "Trade: %s | Trades hoy: %d/%d",
      stateStr,
      g_asiaHigh, g_asiaLow,
      g_asiaRange, g_atrAsia,
      g_asiaCandleCount,
      g_dayEnabled ? "SI" : "NO",
      g_tradeTaken ? g_entrySide : "---",
      g_tradesToday, InpMaxTradesPerDay
   );
   
   Comment(info);
}

//+------------------------------------------------------------------+
//| Expert tick function — Maquina de estados principal                 |
//+------------------------------------------------------------------+
void OnTick()
{
   // ── Obtener hora Madrid ────────────────────────────
   MqlDateTime madridDT;
   int madridH, madridM;
   GetMadridTime(madridH, madridM, madridDT);
   
   // ── Reset diario ──────────────────────────────────
   datetime todayDate = GetMadridDate();
   if(g_currentDate != todayDate)
      ResetDay(todayDate);
   
   // ── Codificar hora como minutos para comparaciones ─
   int currentMinutes = madridH * 60 + madridM;
   int asiaEndMinutes = InpAsiaEndHour * 60;
   int entryStartMinutes = InpEntryStartHour * 60 + InpEntryStartMin;
   int entryEndMinutes   = InpEntryEndHour * 60 + InpEntryEndMin;
   
   // ══════════════════════════════════════════════════
   // MAQUINA DE ESTADOS
   // ══════════════════════════════════════════════════
   
   // ── Estado A: Construyendo Asia (00:00–06:59) ─────
   if(currentMinutes < asiaEndMinutes)
   {
      g_state = STATE_BUILDING_ASIA;
      BuildAsiaRange();
      DrawAsiaLevels();
      ShowInfoPanel();
      return;
   }
   
   // ── Transicion A→B: Asia congelada (07:00–07:29) ──
   if(currentMinutes < entryStartMinutes)
   {
      if(g_state == STATE_BUILDING_ASIA)
         FreezeAsia();
      g_state = STATE_ASIA_FROZEN;
      DrawAsiaLevels();
      ShowInfoPanel();
      return;
   }
   
   // ── Estado C: Buscando entrada (07:30–11:59) ──────
   if(currentMinutes < entryEndMinutes)
   {
      // Asegurar freeze si llegamos aqui sin haber congelado
      if(g_state == STATE_BUILDING_ASIA || g_state == STATE_ASIA_FROZEN)
      {
         if(g_state == STATE_BUILDING_ASIA)
            FreezeAsia();
         g_state = STATE_SEEKING_ENTRY;
      }
      
      if(g_state == STATE_SEEKING_ENTRY)
      {
         if(!g_tradeTaken && g_dayEnabled &&
            g_tradesToday < InpMaxTradesPerDay)
         {
            CheckEntry();
         }
      }
      
      DrawAsiaLevels();
      ShowInfoPanel();
      return;
   }
   
   // ── Estado D: Cerrado para el dia (>=12:00) ───────
   g_state = STATE_DONE_FOR_DAY;
   ShowInfoPanel();
}
//+------------------------------------------------------------------+
