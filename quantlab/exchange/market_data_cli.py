import json

from quantlab.exchange.bybit_market_data import fetch_demo_market_data


def main():
    report = fetch_demo_market_data()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
