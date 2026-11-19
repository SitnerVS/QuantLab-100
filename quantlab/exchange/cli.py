import json
from quantlab.exchange.bybit_demo import check_demo_connection
def main():
    print(json.dumps(check_demo_connection(), ensure_ascii=False, indent=2))
if __name__ == "__main__":
    main()
