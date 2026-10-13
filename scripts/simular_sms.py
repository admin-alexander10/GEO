"""Send one signed GR1 test message to a local GEORESCUE console webhook."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _secret_from_environment() -> bytes:
    encoded = os.environ.get("GEORESCUE_DEVICE_SECRET_B64", "")
    if not encoded:
        raise ValueError("Define GEORESCUE_DEVICE_SECRET_B64 con el secreto registrado en el dispositivo.")
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/sms/entrante")
    parser.add_argument("--lat", type=float, required=True, help="Latitud de prueba")
    parser.add_argument("--lng", type=float, required=True, help="Longitud de prueba")
    parser.add_argument("--precision", type=int, default=5)
    parser.add_argument("--age", type=int, default=0)
    parser.add_argument("--severity", type=int, default=4)
    args = parser.parse_args()

    try:
        if os.environ.get("SMS_PROVIDER", "console").lower() != "console":
            raise ValueError("Este simulador firma el webhook del proveedor console.")
        sender = os.environ["GEORESCUE_SMS_SENDER"]
        webhook_secret = os.environ["SMS_WEBHOOK_SECRET"].encode("utf-8")
        device_secret = _secret_from_environment()
    except (KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not sender.startswith("+"):
        print("GEORESCUE_SMS_SENDER debe estar en formato E.164.", file=sys.stderr)
        return 2

    client_alert_id = base64.b32encode(secrets.token_bytes(7)).decode("ascii")[:10]
    timestamp = int(time.time())
    unsigned = (
        f"GR1|{client_alert_id}|A|{args.lat:.5f}|{args.lng:.5f}|"
        f"{args.precision}|{args.age}|{timestamp}|{args.severity}"
    ).upper()
    signature = base64.b32encode(
        hmac.new(device_secret, unsigned.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")[:8]
    message = f"{unsigned}|{signature}"
    if len(message.encode("ascii")) > 160:
        print("El SMS excede los 160 bytes.", file=sys.stderr)
        return 2

    body = json.dumps(
        {"remitente": sender, "texto": message},
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    provider_signature = hmac.new(webhook_secret, body, hashlib.sha256).hexdigest()
    request = Request(
        args.url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-SMS-Signature": f"sha256={provider_signature}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Webhook rechazó el mensaje (HTTP {exc.code}).", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"No se pudo contactar el backend: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=True))
    return 0 if result.get("aceptado") else 1


if __name__ == "__main__":
    raise SystemExit(main())
