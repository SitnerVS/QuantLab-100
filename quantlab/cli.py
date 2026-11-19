import argparse
import yaml

from quantlab.data.download import download_all
from quantlab.backtest.runner import run_backtests
from quantlab.paper.runner import run_paper
from quantlab.data.quality import run_data_quality


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main():
    parser = argparse.ArgumentParser(description="QuantLab 100 research and paper signals")
    parser.add_argument("command", choices=["download", "backtest", "paper", "run"])
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.command in ("download", "run"):
        download_all(cfg)
    if args.command in ("download", "backtest", "paper", "run"):
        run_data_quality(cfg)
    if args.command in ("backtest", "run"):
        run_backtests(cfg)
    if args.command in ("paper", "run"):
        run_paper(cfg)


if __name__ == "__main__":
    main()
