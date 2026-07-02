import urllib3
import json
import base58
import base64
import struct
import time
import random

# Dezactivăm warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Pool de conexiuni reutilizabile - mult mai rapid
http = urllib3.PoolManager(
    num_pools=10,
    maxsize=10,
    retries=urllib3.Retry(3, redirect=2),
    timeout=urllib3.Timeout(connect=5.0, read=30.0)
)

TOKEN_MINT = "8ss1fMcLCZ8teV9hpPe8JXqfsPF12TF3X4PtN5kNJray"
TOP_N = 50

MAINNET_RPC = "https://api.mainnet-beta.solana.com"
DEX_PRICE_URL = "https://api.dexscreener.com/latest/dex/tokens/"

def rpc_call(method, params, max_retries=10, base_delay=5):
    """Face apel RPC cu retry logic și backoff exponențial"""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }).encode('utf-8')
    
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            resp = http.request(
                'POST',
                MAINNET_RPC,
                body=payload,
                headers=headers
            )
            
            if resp.status == 429:
                delay = base_delay * (2 ** (attempt - 1)) + random.random() * 5
                time.sleep(delay)
                continue
                
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}: {resp.data.decode()}")
            
            data = json.loads(resp.data.decode('utf-8'))
            
            if "error" in data:
                raise Exception(data["error"]["message"])
                
            return data["result"]
            
        except Exception as e:
            if attempt == max_retries:
                raise Exception(f"Eșec după {max_retries} încercări: {e}")
            time.sleep(base_delay * (2 ** (attempt - 1)))
    
    raise Exception("RPC nereușit")

def get_token_supply():
    """Obține supply-ul token-ului"""
    res = rpc_call("getTokenSupply", [TOKEN_MINT])
    dec = res["value"]["decimals"]
    raw_supply = int(res["value"]["amount"])
    return dec, raw_supply

def get_all_holders():
    """Obține toți deținătorii de token"""
    filters = [
        {"dataSize": 165},
        {"memcmp": {"offset": 0, "bytes": TOKEN_MINT}}
    ]
    config = {"encoding": "base64", "filters": filters}
    program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    
    accounts = []
    before = None
    
    while True:
        params = [program, config.copy()]
        if before:
            params[1]["before"] = before
            
        result = rpc_call("getProgramAccounts", params)
        
        if not result:
            break
            
        accounts.extend(result)
        
        if len(result) < 1000:
            break
            
        before = result[-1]["pubkey"]
        time.sleep(0.3)  # Pauză mai mică pentru viteză
    
    return accounts

def parse_account(acc):
    """Parsează un cont de token"""
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
    """Obține prețul de pe DexScreener"""
    try:
        url = f"{DEX_PRICE_URL}{TOKEN_MINT}"
        resp = http.request('GET', url, headers={'Accept': 'application/json'})
        
        if resp.status == 200:
            data = json.loads(resp.data.decode('utf-8'))
            pairs = data.get("pairs", [])
            
            if pairs:
                # Caută perechea pe Solana
                for p in pairs:
                    if p.get("chainId") == "solana":
                        return float(p.get("priceUsd", 0))
                # Fallback la prima pereche
                return float(pairs[0].get("priceUsd", 0))
    except:
        pass
    
    return 0.0

def main():
    try:
        # Obține supply
        decimals, supply_raw = get_token_supply()
        total_supply = supply_raw / 10 ** decimals
        
        # Obține toți deținătorii
        raw_accounts = get_all_holders()
        
        holders = []
        for acc in raw_accounts:
            parsed = parse_account(acc)
            if parsed:
                tok_acc, owner, amt_raw = parsed
                if amt_raw > 0:
                    qty = amt_raw / 10 ** decimals
                    pct = (qty / total_supply * 100) if total_supply else 0
                    holders.append({
                        "token_account": tok_acc,
                        "owner": owner,
                        "quantity": qty,
                        "percentage": pct
                    })
        
        # Sortează după cantitate
        holders.sort(key=lambda h: h["quantity"], reverse=True)
        
        # Obține prețul
        price = get_price()
        
        # Calculează valoarea
        for h in holders:
            h["value"] = h["quantity"] * price
        
        # Ia top N
        top = holders[:TOP_N]
        
        # Formatează pentru JSON
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
        
        # Salvează JSON
        with open("date.json", "w", encoding="utf-8") as f:
            json.dump(top_json, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Actualizare reușită: {len(top_json)} deținători salvați")
        
    except Exception as e:
        # Salvează eroarea în JSON pentru debugging
        error_data = {
            "error": str(e),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        }
        
        with open("date.json", "w", encoding="utf-8") as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)
        
        print(f"❌ Eroare: {e}")
        raise  # Aruncă eroarea pentru ca workflow-ul să eșueze

if __name__ == "__main__":
    main()
