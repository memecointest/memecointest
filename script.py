import requests
import base58
import base64
import struct
import time
import json
import random

TOKEN_MINT = "8ss1fMcLCZ8teV9hpPe8JXqfsPF12TF3X4PtN5kNJray"
TOP_N = 50

MAINNET_RPC = "https://api.mainnet-beta.solana.com"
DEX_PRICE_URL = "https://api.dexscreener.com/latest/dex/tokens/"
PUMP_PORTAL_URL = f"https://pumpportal.fun/api/token/{TOKEN_MINT}"

KNOWN_TAGS = {}  # nefolosit în JSON

def rpc_call(method, params, max_retries=10, base_delay=5):
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(MAINNET_RPC, json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params
            }, timeout=30)
            if resp.status_code == 429:
                delay = base_delay * (2 ** (attempt - 1)) + random.random() * 5
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise Exception(data["error"]["message"])
            return data["result"]
        except Exception as e:
            if attempt == max_retries:
                raise Exception(f"Eșec după {max_retries} încercări: {e}")
            time.sleep(base_delay * (2 ** (attempt - 1)))
    raise Exception("RPC nereușit")

def get_token_supply():
    res = rpc_call("getTokenSupply", [TOKEN_MINT])
    dec = res["value"]["decimals"]
    raw_supply = int(res["value"]["amount"])
    return dec, raw_supply

def get_all_holders():
    filters = [
        {"dataSize": 165},
        {"memcmp": {"offset": 0, "bytes": TOKEN_MINT}}
    ]
    config = {"encoding": "base64", "filters": filters}
    program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    accounts = []
    before = None
    page = 1
    while True:
        params = [program, config.copy()]
        if before:
            params[1]["before"] = before
        result = rpc_call("getProgramAccounts", params)
        if not result:
            break
        accounts.extend(result)
        page += 1
        if len(result) < 1000:
            break
        before = result[-1]["pubkey"]
        time.sleep(0.5)
    return accounts

def parse_account(acc):
    try:
        token_acc = acc["pubkey"]
        data_b64 = acc["account"]["data"][0]
        raw = base64.b64decode(data_b64)
        owner_bytes = raw[32:64]
        owner = base58.b58encode(owner_bytes).decode()
        amount = struct.unpack_from('<Q', raw, 64)[0]
        return token_acc, owner, amount
    except:
        return None

def get_price():
    try:
        resp = requests.get(f"{DEX_PRICE_URL}{TOKEN_MINT}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            pairs = data.get("pairs", [])
            if pairs:
                for p in pairs:
                    if p.get("chainId") == "solana":
                        return float(p.get("priceUsd", 0))
                return float(pairs[0].get("priceUsd", 0))
    except:
        pass
    return 0.0

try:
    decimals, supply_raw = get_token_supply()
    total_supply = supply_raw / 10**decimals

    raw_accounts = get_all_holders()
    holders = []
    for acc in raw_accounts:
        parsed = parse_account(acc)
        if parsed:
            tok_acc, owner, amt_raw = parsed
            if amt_raw > 0:
                qty = amt_raw / 10**decimals
                pct = (qty / total_supply * 100) if total_supply else 0
                holders.append({
                    "token_account": tok_acc,
                    "owner": owner,
                    "quantity": qty,
                    "percentage": pct
                })

    holders.sort(key=lambda h: h["quantity"], reverse=True)
    price = get_price()
    for h in holders:
        h["value"] = h["quantity"] * price

    top = holders[:TOP_N]
    top_json = []
    for i, h in enumerate(top, 1):
        top_json.append({
            "Rank": i,
            "Account (Owner)": h["owner"],
            "Token Account": h["token_account"],
            "Quantity": round(h["quantity"], 6),
            "%": round(h["percentage"], 2),
            "Value": round(h["value"], 2)
        })

    with open("date.json", "w", encoding="utf-8") as f:
        json.dump(top_json, f, indent=2, ensure_ascii=False)

except Exception as e:
    with open("date.json", "w", encoding="utf-8") as f:
        json.dump({"error": str(e)}, f, indent=2, ensure_ascii=False)
