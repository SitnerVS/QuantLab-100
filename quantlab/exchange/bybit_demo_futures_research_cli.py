import argparse

import yaml

from quantlab.exchange.bybit_demo_futures_research import run_bybit_demo_futures_backtests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--data-dir", default="data/bybit_demo")
    parser.add_argument("--report-dir", default="reports")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    run_bybit_demo_futures_backtests(
        cfg, data_dir=args.data_dir, report_dir=args.report_dir
    )


if __name__ == "__main__":
    main()
