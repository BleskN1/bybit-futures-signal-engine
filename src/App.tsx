import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  Clock,
  Database,
  Layers,
  Radio,
  RefreshCw,
  Send,
  Server,
  Settings,
  Shield,
  TrendingUp,
  Zap,
} from "lucide-react";

interface UniverseItem {
  rank: number;
  symbol: string;
  price: string;
  turnover24h: string;
  openInterest: string;
  spreadPct: string;
  volatility24h: string;
  score: number;
}

const SAMPLE_UNIVERSE: UniverseItem[] = [
  { rank: 1, symbol: "BTCUSDT", price: "64,820.50", turnover24h: "$1.85B", openInterest: "$2.94B", spreadPct: "0.01%", volatility24h: "3.4%", score: 98.4 },
  { rank: 2, symbol: "ETHUSDT", price: "3,485.20", turnover24h: "$940M", openInterest: "$1.12B", spreadPct: "0.01%", volatility24h: "4.1%", score: 92.1 },
  { rank: 3, symbol: "SOLUSDT", price: "152.40", turnover24h: "$520M", openInterest: "$340M", spreadPct: "0.02%", volatility24h: "5.8%", score: 86.7 },
  { rank: 4, symbol: "BNBUSDT", price: "582.10", turnover24h: "$210M", openInterest: "$180M", spreadPct: "0.02%", volatility24h: "2.9%", score: 79.5 },
  { rank: 5, symbol: "AVAXUSDT", price: "28.45", turnover24h: "$185M", openInterest: "$124M", spreadPct: "0.03%", volatility24h: "6.2%", score: 75.3 },
  { rank: 6, symbol: "DOGEUSDT", price: "0.1085", turnover24h: "$195M", openInterest: "$142M", spreadPct: "0.02%", volatility24h: "5.4%", score: 74.8 },
  { rank: 7, symbol: "SUIUSDT", price: "1.7420", turnover24h: "$165M", openInterest: "$110M", spreadPct: "0.03%", volatility24h: "7.1%", score: 73.2 },
  { rank: 8, symbol: "NEARUSDT", price: "4.850", turnover24h: "$140M", openInterest: "$92M", spreadPct: "0.03%", volatility24h: "6.5%", score: 71.0 },
];

export default function App() {
  const [selectedTf, setSelectedTf] = useState("15m");
  const [activeTab, setActiveTab] = useState<"universe" | "signals" | "architecture">("universe");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-emerald-500 selection:text-black">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-sm shadow-emerald-500/20">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold tracking-tight text-white">Bybit Futures Signal Engine</h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950 text-emerald-400 border border-emerald-800/60">
                MVP v1.0
              </span>
            </div>
            <p className="text-xs text-slate-400">Production-oriented Quant Engine &bull; Bybit V5 USDT Perps</p>
          </div>
        </div>

        {/* Global Cluster Indicators */}
        <div className="flex items-center gap-5 text-xs font-mono">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800">
            <Radio className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
            <span className="text-slate-400">WS V5:</span>
            <span className="text-emerald-400 font-semibold">CONNECTED</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800">
            <Database className="w-3.5 h-3.5 text-sky-400" />
            <span className="text-slate-400">DB:</span>
            <span className="text-sky-300 font-semibold">SQLITE ACTIVE</span>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-slate-900 border border-slate-800">
            <Send className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">TELEGRAM:</span>
            <span className="text-slate-300 font-semibold">SCORE &ge; 75</span>
          </div>
        </div>
      </header>

      {/* Main Content Dashboard */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {/* Metric Overview Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Monitored Universe</span>
              <Layers className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-white">20 Pairs</div>
            <p className="text-[11px] text-slate-400 mt-1">Dynamic ranking every 4 hours</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Lookahead Bias Policy</span>
              <Shield className="w-4 h-4 text-sky-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-emerald-400">Closed Bars Only</div>
            <p className="text-[11px] text-slate-400 mt-1">confirm == true strict gating</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Timeframe Analysis</span>
              <Clock className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-white">4H / 1H / 15m / 5m</div>
            <p className="text-[11px] text-slate-400 mt-1">2000 candles deep bootstrap</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-sm">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Ambiguous Candle Policy</span>
              <AlertTriangle className="w-4 h-4 text-violet-400" />
            </div>
            <div className="text-2xl font-bold font-mono text-violet-300">Conservative (SL)</div>
            <p className="text-[11px] text-slate-400 mt-1">Realistic paper tracking</p>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("universe")}
              className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
                activeTab === "universe"
                  ? "bg-slate-800 text-emerald-400 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Dynamic Universe (TOP 20)
            </button>
            <button
              onClick={() => setActiveTab("signals")}
              className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
                activeTab === "signals"
                  ? "bg-slate-800 text-emerald-400 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Signal Pipeline & Score Breakdown
            </button>
            <button
              onClick={() => setActiveTab("architecture")}
              className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
                activeTab === "architecture"
                  ? "bg-slate-800 text-emerald-400 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Architecture & API Spec
            </button>
          </div>

          <div className="text-xs text-slate-500 font-mono">
            Bybit V5 Public Linear Endpoint
          </div>
        </div>

        {/* Tab 1: Dynamic Universe */}
        {activeTab === "universe" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white">Multi-Factor Liquidity Ranking</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Filtered by USDT Perps &bull; Turnover, Open Interest, Volume, Bid/Ask Spread Penalty, Volatility
                </p>
              </div>
              <span className="text-xs font-mono px-2.5 py-1 bg-slate-800 text-slate-300 rounded border border-slate-700">
                TOP_SYMBOLS = 20
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/90 text-slate-400 font-mono">
                    <th className="py-3 px-4 font-medium">Rank</th>
                    <th className="py-3 px-4 font-medium">Symbol</th>
                    <th className="py-3 px-4 font-medium">Last Price</th>
                    <th className="py-3 px-4 font-medium">24h Turnover</th>
                    <th className="py-3 px-4 font-medium">Open Interest</th>
                    <th className="py-3 px-4 font-medium">Spread</th>
                    <th className="py-3 px-4 font-medium">24h Range</th>
                    <th className="py-3 px-4 font-medium text-right">Composite Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {SAMPLE_UNIVERSE.map((item) => (
                    <tr key={item.symbol} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-3 px-4 text-slate-400">#{item.rank}</td>
                      <td className="py-3 px-4 font-bold text-white flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                        {item.symbol}
                      </td>
                      <td className="py-3 px-4 text-slate-200">${item.price}</td>
                      <td className="py-3 px-4 text-slate-300">{item.turnover24h}</td>
                      <td className="py-3 px-4 text-slate-300">{item.openInterest}</td>
                      <td className="py-3 px-4 text-emerald-400">{item.spreadPct}</td>
                      <td className="py-3 px-4 text-slate-300">{item.volatility24h}</td>
                      <td className="py-3 px-4 text-right">
                        <span className="px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">
                          {item.score}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Signal Pipeline & Scoring */}
        {activeTab === "signals" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Weights Card */}
            <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/60 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <h3 className="text-sm font-semibold text-white">Scoring Weight Distribution</h3>
                <span className="text-xs font-mono text-emerald-400 font-bold">Total: 100%</span>
              </div>
              <p className="text-xs text-slate-400">
                Baseline quantitative hypothesis configured in <code className="text-slate-300">config/scoring.yaml</code>
              </p>

              <div className="space-y-2.5 text-xs font-mono">
                {[
                  { name: "HTF Trend (4H EMA Structure)", weight: "15%", color: "bg-emerald-500" },
                  { name: "Market Structure (BOS / CHOCH)", weight: "15%", color: "bg-emerald-500" },
                  { name: "Liquidity Sweep & Pools", weight: "15%", color: "bg-emerald-500" },
                  { name: "Derivatives (OI Delta & Funding)", weight: "15%", color: "bg-emerald-500" },
                  { name: "Price Action (Rejections / Engulf)", weight: "15%", color: "bg-emerald-500" },
                  { name: "Momentum (RSI / StochRSI / MACD)", weight: "10%", color: "bg-sky-500" },
                  { name: "Volume (SMA / VWAP / OBV)", weight: "10%", color: "bg-sky-500" },
                  { name: "Volatility (ATR Regime)", weight: "5%", color: "bg-amber-500" },
                ].map((item) => (
                  <div key={item.name} className="flex items-center justify-between p-2 rounded bg-slate-800/50">
                    <span className="text-slate-300">{item.name}</span>
                    <span className="font-bold text-white">{item.weight}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Signal Sample Card */}
            <div className="lg:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/60 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  <h3 className="text-sm font-semibold text-white">Live Formatted Alert Preview</h3>
                </div>
                <span className="text-xs font-mono text-slate-400">Telegram Dispatch Template</span>
              </div>

              <div className="p-5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs space-y-3 leading-relaxed text-slate-200">
                <div className="text-emerald-400 font-bold text-sm flex items-center gap-1.5">
                  <ArrowUpRight className="w-4 h-4" /> 🟢 LONG SIGNAL &bull; BTCUSDT
                </div>
                <div>
                  <span className="text-slate-400">Signal Score:</span>{" "}
                  <span className="text-emerald-300 font-bold text-sm">84.5 / 100</span>{" "}
                  <span className="text-slate-500 text-[11px]">(Directional Edge: +12.0)</span>
                </div>
                <div>
                  <span className="text-slate-400">Market Regime:</span>{" "}
                  <span className="text-sky-300 font-semibold">TRENDING_UP</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-800 text-[11px]">
                  <div className="p-2 rounded bg-slate-900">
                    <span className="text-slate-500 block">Entry Zone:</span>
                    <span className="text-white font-bold">64,800 – 64,850</span>
                  </div>
                  <div className="p-2 rounded bg-slate-900">
                    <span className="text-slate-500 block">Stop Loss:</span>
                    <span className="text-rose-400 font-bold">64,250</span>
                  </div>
                  <div className="p-2 rounded bg-slate-900">
                    <span className="text-slate-500 block">TP1 (1R):</span>
                    <span className="text-emerald-400 font-bold">65,400</span>
                  </div>
                  <div className="p-2 rounded bg-slate-900">
                    <span className="text-slate-500 block">TP2 (2R):</span>
                    <span className="text-emerald-400 font-bold">66,000</span>
                  </div>
                </div>
                <div className="pt-2 text-slate-400">
                  <span className="text-slate-300 font-semibold block mb-1">Confluence Breakdown:</span>
                  <div className="space-y-1 text-[11px]">
                    <div>&bull; 4H Trend: Bullish EMA 20 &gt; 50 &gt; 200 stack with positive slope</div>
                    <div>&bull; Structure: 15m BOS (Break of Structure) confirmed at 64,750</div>
                    <div>&bull; Liquidity: Asian session low swept followed by strong rejection candle</div>
                    <div>&bull; Derivatives: +3.2% Open Interest expansion on rising volume</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Architecture & API */}
        {activeTab === "architecture" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 space-y-6 text-xs">
            <div>
              <h3 className="text-sm font-semibold text-white mb-2">Bybit V5 Integration Matrix</h3>
              <p className="text-slate-400 mb-4">
                Real-time subscriptions and REST endpoints implemented in the engine layer.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono">
              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="text-emerald-400 font-bold block">REST Endpoints (https://api.bybit.com)</span>
                <ul className="space-y-1.5 text-slate-300 text-[11px]">
                  <li>&bull; <code className="text-sky-300">GET /v5/market/instruments-info</code> (category=linear)</li>
                  <li>&bull; <code className="text-sky-300">GET /v5/market/tickers</code> (24h turnover & volume)</li>
                  <li>&bull; <code className="text-sky-300">GET /v5/market/kline</code> (2000 bars paginated bootstrap)</li>
                  <li>&bull; <code className="text-sky-300">GET /v5/market/open-interest</code> (raw historical OI)</li>
                  <li>&bull; <code className="text-sky-300">GET /v5/market/funding/history</code> (settlement rates)</li>
                </ul>
              </div>

              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="text-emerald-400 font-bold block">WebSocket Topics (wss://stream.bybit.com)</span>
                <ul className="space-y-1.5 text-slate-300 text-[11px]">
                  <li>&bull; <code className="text-amber-300">kline.5.&#123;symbol&#125;</code> (confirm == true closed bar)</li>
                  <li>&bull; <code className="text-amber-300">kline.15.&#123;symbol&#125;</code> (setup timeframe)</li>
                  <li>&bull; <code className="text-amber-300">kline.60.&#123;symbol&#125;</code> (structure context)</li>
                  <li>&bull; <code className="text-amber-300">kline.240.&#123;symbol&#125;</code> (HTF macro context)</li>
                  <li>&bull; <code className="text-amber-300">tickers.&#123;symbol&#125;</code> (real-time price & paper tracking)</li>
                  <li>&bull; <code className="text-amber-300">allLiquidation.&#123;symbol&#125;</code> (liquidation streams)</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 px-6 py-4 bg-slate-950 text-xs text-slate-500 flex items-center justify-between">
        <div>Bybit Futures Quantitative Signal Engine &bull; Non-execution MVP</div>
        <div className="font-mono">Signal Score: 0–100 &bull; Python 3.12+ Async Engine</div>
      </footer>
    </div>
  );
}
