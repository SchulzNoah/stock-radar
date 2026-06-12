# Stock Radar: Automated Corporate Finance & Analytics Pipeline

I engineered this automated system to extract, process, and analyze fundamental financial stock metrics from the 2 major indices (**S&P 500** and **NASDAQ**). 

The entire system is fully autonomous, utilizing GitHub Actions as a serverless orchestrator for daily ETL operations, dashboard generation, and reporting.

## Key Features

* **Scalable Data Ingestion:** Features a multi-threaded scraping architecture with integrated proxy rotation. This ensures high-throughput data extraction for thousands of corporate records while effectively managing rate limits.
* **End-to-End Automation (CI/CD):** Orchestrated via GitHub Actions utilizing a `cron` schedule (`daily_finance_pipeline.yml`), ensuring an automated execution every single day.
* **ETL & Fundamental Analytics:** Raw market data is ingested, cleaned, and aggregated using pandas to calculate the essential fundamental metrics required for long-term equity analysis.
* **Automated Reporting:** The pipeline dynamically generates a static HTML dashboard (served seamlessly via GitHub Pages) and dispatches a curated daily email newsletter via SMTP.
* **Self-Healing State Management:** Custom CI/CD steps automatically rotate historical data files. By retaining only the most recent datasets and actively pruning the Git index, the pipeline prevents `.git` bloat and avoids runner memory exhaustion (SIGKILL) over time.

## Pipeline Architecture

The workflow is decoupled into two core Python modules, executed sequentially by the CI/CD runner:

1. **`main.py` (The Extractor):**
   * Establishes connections via configured proxy networks.
   * Executes concurrent threads to scrape daily fundamental metrics.
   * Dumps the raw output as structured CSV files into the `data/` directory.

2. **`newsletter.py` (The Transformer & Publisher):**
   * Ingests the latest raw CSV datasets.
   * Renders the updated frontend dashboard directly into the `docs/` folder for immediate hosting.
   * Formats the most critical market movements into an HTML email template and triggers the SMTP broadcast.

## Tech Stack

* **Language:** Python 3.11
* **Data Engineering:** Pandas, NumPy
* **Orchestration:** GitHub Actions
* **Deployment:** GitHub Pages

## 👨‍💻 About the Author

**Noah Schulz | Let's connect :)**[![LinkedIn](https://upload.wikimedia.org/wikipedia/commons/thumb/8/81/LinkedIn_icon.svg/32px-LinkedIn_icon.svg.png)](https://www.linkedin.com/in/noah-schulz-971031301/)

