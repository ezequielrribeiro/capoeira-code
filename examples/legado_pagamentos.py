import os
import json
import logging


class PaymentProcessor:
    def process(self, order):
        total = 0
        for item in order["items"]:
            total += item["price"] * item["quantity"]
        if total > 1000:
            total *= 0.9
        return self.charge(total)

    def charge(self, amount):
        logging.info("charging %s", amount)
        return {"ok": True, "amount": amount}

    async def notify(self, order):
        message = {"order_id": order["id"], "status": "paid"}
        return json.dumps(message)


def format_currency(value):
    return f"R$ {value:.2f}"


def main():
    processor = PaymentProcessor()
    return processor


if __name__ == "__main__":
    main()
