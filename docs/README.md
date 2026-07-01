# CA Fantasy 5 Prediction System

6-engine fusion lottery prediction analysis system for California Fantasy 5 (1-39).

## Live Dashboard
👉 [https://likeyourlife.github.io/ca-lottery-predictor/](https://likeyourlife.github.io/ca-lottery-predictor/)

## Disclaimer
⚠️ This software does NOT claim to predict lottery winning numbers. Lottery draws are inherently random. The model outputs probability rankings for statistical reference only, not as betting advice.
Confidence: B (Statistical level, not causal)

## Architecture
- **6 Engines**: Frequency Deviation (8%), Bayesian (22%), Markov (36%), Joint Co-occurrence (34%), FFT (1%), Monte Carlo (0%)
- **Dual Modes**: Avoid (exclude least likely) + Rebound (catch cold numbers returning)
- **Backtest-driven weights**: Random search 200 groups + local optimization
- **Top10 hit rate**: 80% > baseline 79.37% (+0.63%)

## Quick Start
```bash
# Run prediction
python run_predictor.py --mode full

# Generate frontend data
python frontend/generate_api_data.py

# Scrape data (Puppeteer)
node data/puppeteer_scrape.js --year 2022 --year 2023 --year 2024

# Merge scraped data
python data/merge_scraped_data.py
```
