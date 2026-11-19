import json

from quantlab.exchange.bybit_demo_futures import fetch_bybit_demo_futures_data


def main():
    report = fetch_bybit_demo_futures_data()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
