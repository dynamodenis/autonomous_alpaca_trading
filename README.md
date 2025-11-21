---
title: Trading floor
emoji: 🚀
colorFrom: red
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
---

# 🤖 AI Trading Floor

An autonomous multi-agent trading simulation where AI traders powered by different language models compete in the stock market. Watch as each AI develops its own trading strategy and makes real-time decisions!

## 🎯 Live Demo

🔗 **[View Live Trading Floor](https://huggingface.co/spaces/dynamodenis254/trading_floor)**

## 📊 Meet the Traders

Each AI agent starts with **$10,000** and trades independently in the stock market:

| Name | Personality | Model | Strategy Style |
|------|------------|-------|----------------|
| **Warren Patience** | Conservative, long-term value investor | GPT-4.1 Mini | Patient, fundamental analysis |
| **George Bold** | Aggressive risk-taker | DeepSeek V3 | Bold moves, high conviction |
| **Ray Systematic** | Data-driven quantitative trader | Gemini 2.5 Flash | Systematic, rule-based |
| **Cathie Crypto** | Innovation-focused growth investor | Grok 3 Mini | Disruptive tech & crypto exposure |

## ✨ Features

- **Real-time Trading Dashboard**: Monitor all 4 agents simultaneously
- **Portfolio Tracking**: Live portfolio values, P&L, and holdings
- **Transaction History**: Complete audit trail of all trades
- **Performance Charts**: Visualize portfolio growth over time
- **Live Logs**: Watch AI decision-making in real-time
- **Multi-Model Competition**: Different AI models with unique trading styles
- **Market Hours Aware**: Respects actual market trading hours

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- API keys for the AI models you want to use

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/trading-floor.git
cd trading-floor
```

2. Install dependencies:
```bash
pip install -r requirements.txt
# or with uv
uv pip install -r requirements.txt
```

3. Create a `.env` file with your configuration:

```env
# Required: At least one API key
OPENAI_API_KEY=your_openai_key_here

# Optional: For multi-model competition (set USE_MANY_MODELS=true)
DEEPSEEK_API_KEY=your_deepseek_key_here
GOOGLE_API_KEY=your_google_key_here
GROK_API_KEY=your_grok_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Trading Configuration
RUN_EVERY_N_MINUTES=60
RUN_EVEN_WHEN_MARKET_IS_CLOSED=false
USE_MANY_MODELS=true
```

### Running Locally

**Option 1: Run Everything (UI + Agents)**
```bash
python app.py
```

**Option 2: Run Components Separately**
```bash
# Terminal 1: Start the trading agents
python trading_floor.py

# Terminal 2: Start the UI
python app.py
```

The dashboard will be available at `http://localhost:7860`

## ⚙️ Configuration Options

### Environment Variables

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `RUN_EVERY_N_MINUTES` | Trading cycle frequency | `60` | Any integer (minutes) |
| `RUN_EVEN_WHEN_MARKET_IS_CLOSED` | Trade outside market hours | `false` | `true` / `false` |
| `USE_MANY_MODELS` | Enable 4 different AI models | `false` | `true` / `false` |

### Single Model vs Multi-Model

**Single Model Mode** (`USE_MANY_MODELS=false`):
- All 4 agents use GPT-4.1 Mini
- Only requires `OPENAI_API_KEY`
- Lower API costs
- Great for testing strategies

**Multi-Model Mode** (`USE_MANY_MODELS=true`):
- Each agent uses a different AI model
- Requires multiple API keys
- Diverse trading strategies
- More interesting competition

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                   app.py                        │
│  (Gradio UI + Background Trading Thread)        │
└─────────────────┬───────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
┌────────▼────────┐ ┌─────▼──────────┐
│  trading_floor  │ │   Gradio UI    │
│   (Agents)      │ │   Dashboard    │
└────────┬────────┘ └────────────────┘
         │
    ┌────┴─────┬──────┬──────┐
    │          │      │      │
┌───▼───┐ ┌───▼───┐ ┌▼────┐ ┌▼─────┐
│Warren │ │George │ │Ray  │ │Cathie│
│ GPT-4 │ │DeepSeek│Gemini│ │ Grok │
└───────┘ └───────┘ └─────┘ └──────┘
```

## 📦 Project Structure

```
trading-floor/
├── app.py                 # Main Gradio UI application
├── trading_floor.py       # Autonomous agent scheduler
├── traders.py            # Trader class implementation
├── accounts.py           # Portfolio & transaction management
├── agents.py             # AI agent logic
├── market.py             # Market data & trading hours
├── database.py           # Logging & persistence
├── util.py               # Utilities & styling
├── requirements.txt      # Python dependencies
└── .env                  # Configuration (create this)
```

## 🎮 How It Works

1. **Initialization**: Each agent starts with $10,000 in cash
2. **Analysis Phase**: Agents analyze market conditions, news, and their portfolio
3. **Decision Making**: AI models decide on trades based on their personality
4. **Execution**: Buy/sell orders are executed at market prices
5. **Logging**: All decisions and transactions are recorded
6. **Repeat**: Cycle repeats every N minutes during market hours

## 📈 Dashboard Features

### Real-Time Metrics
- **Portfolio Value**: Current total value (cash + holdings)
- **P&L Indicator**: Profit/Loss with color coding (🟢/🔴)
- **Performance Chart**: Historical portfolio value over time

### Data Tables
- **Holdings**: Current stock positions
- **Recent Transactions**: Trade history with rationale
- **Live Logs**: AI thinking process and decisions

## 🔧 API Keys Setup

### Getting API Keys

1. **OpenAI (GPT-4.1 Mini)**: https://platform.openai.com/api-keys
2. **DeepSeek**: https://platform.deepseek.com/
3. **Google AI (Gemini)**: https://aistudio.google.com/apikey
4. **Grok (xAI)**: https://console.x.ai/
5. **OpenRouter**: https://openrouter.ai/keys

### Security Notes
- ⚠️ **Never commit your `.env` file**
- Add `.env` to `.gitignore`
- For Hugging Face Spaces, use the Secrets tab in settings
- Rotate keys regularly

## 🚀 Deploying to Hugging Face Spaces

1. Create a new Space at https://huggingface.co/spaces
2. Upload your code
3. Add secrets in Settings → Repository Secrets:
   - `OPENAI_API_KEY`
   - `DEEPSEEK_API_KEY` (if using multi-model)
   - `GOOGLE_API_KEY` (if using multi-model)
   - `GROK_API_KEY` (if using multi-model)
   - `RUN_EVERY_N_MINUTES=60`
   - `USE_MANY_MODELS=true`
4. Space will auto-deploy!

## 🤝 Contributing

Contributions are welcome! Ideas:
- New trading strategies
- Additional AI models
- Enhanced analytics
- Risk management features
- Backtesting capabilities

## ⚖️ Disclaimer

**This is a simulation for educational and entertainment purposes only.**

- 🚫 Not financial advice
- 🚫 Not suitable for real trading
- 🚫 No guarantee of accuracy
- ⚠️ AI models can make irrational decisions
- ⚠️ Past performance ≠ future results

**Do not use this for actual investment decisions. Always consult with a qualified financial advisor.**

## 📄 License

MIT License - feel free to use and modify!

## 🙏 Acknowledgments

- Built with [Gradio](https://gradio.app/)
- Powered by OpenAI, DeepSeek, Google, and xAI
- Inspired by legendary investors Warren Buffett, George Soros, Ray Dalio, and Cathie Wood

---

**Made with ❤️ by [DynamoDenis254](https://huggingface.co/dynamodenis254) [LinkedIn](https://www.linkedin.com/in/dynamo-denis-mbugua-53304b197/)**

⭐ Star this project if you find it interesting!