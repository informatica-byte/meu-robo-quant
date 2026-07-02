import csv
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests


HEADERS = {
    "accept": "application/json",
    "user-agent": "Meu-Robo-Quant-24h/1.0",
}

STATE_FILE = Path(os.getenv("BOT_STATE_FILE", "bot_state.json"))
TRADES_FILE = Path(os.getenv("BOT_TRADES_FILE", "bot_trades.csv"))


def env_bool(nome, padrao=False):
    valor = os.getenv(nome, str(padrao)).strip().lower()
    return valor in {"1", "true", "yes", "sim", "on"}


def env_float(nome, padrao):
    try:
        return float(os.getenv(nome, str(padrao)))
    except ValueError:
        return float(padrao)


def env_int(nome, padrao):
    try:
        return int(os.getenv(nome, str(padrao)))
    except ValueError:
        return int(padrao)


def agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg):
    print(f"[{agora()}] {msg}", flush=True)


def base_url():
    usar_testnet = env_bool("BINANCE_USE_TESTNET", True)
    return os.getenv(
        "BINANCE_BASE_URL",
        "https://testnet.binance.vision" if usar_testnet else "https://api.binance.com",
    ).rstrip("/")


def public_get(path, params=None):
    resposta = requests.get(f"{base_url()}{path}", params=params or {}, headers=HEADERS, timeout=20)
    resposta.raise_for_status()
    return resposta.json()


def credenciais():
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        raise RuntimeError("Configure BINANCE_API_KEY e BINANCE_API_SECRET.")
    return api_key, api_secret


def assinar(params, api_secret):
    query = urlencode(params, doseq=True)
    signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**params, "signature": signature}


def binance_request(method, path, params=None):
    api_key, api_secret = credenciais()
    params = {
        **(params or {}),
        "recvWindow": 5000,
        "timestamp": int(time.time() * 1000),
    }
    params = assinar(params, api_secret)
    resposta = requests.request(
        method,
        f"{base_url()}{path}",
        params=params,
        headers={"X-MBX-APIKEY": api_key},
        timeout=20,
    )
    resposta.raise_for_status()
    return resposta.json() if resposta.text else {"status": "OK"}


def carregar_estado():
    if not STATE_FILE.exists():
        return {
            "cash_guard": 0,
            "positions": {},
            "realized_pnl": 0.0,
            "day": datetime.now().strftime("%Y-%m-%d"),
            "day_start_equity": None,
            "halted": False,
        }
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def salvar_estado(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def registrar_trade(row):
    existe = TRADES_FILE.exists()
    with TRADES_FILE.open("a", newline="", encoding="utf-8") as arquivo:
        campos = ["time", "mode", "symbol", "side", "qty", "price", "quote", "reason", "score"]
        writer = csv.DictWriter(arquivo, fieldnames=campos)
        if not existe:
            writer.writeheader()
        writer.writerow(row)


def klines(symbol, interval="1h", limit=72):
    dados = public_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    candles = []
    for item in dados:
        candles.append(
            {
                "open_time": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    return candles


def media(valores, periodo):
    if not valores:
        return 0.0
    fatia = valores[-periodo:]
    return sum(fatia) / len(fatia)


def rsi(fechamentos, periodo=14):
    if len(fechamentos) <= periodo:
        return 50.0
    ganhos = []
    perdas = []
    for anterior, atual in zip(fechamentos[-periodo - 1 : -1], fechamentos[-periodo:]):
        delta = atual - anterior
        ganhos.append(max(delta, 0))
        perdas.append(abs(min(delta, 0)))
    avg_gain = sum(ganhos) / periodo
    avg_loss = sum(perdas) / periodo or 0.000001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def analisar_symbol(symbol):
    candles = klines(symbol)
    fechamentos = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    preco = fechamentos[-1]
    sma_curta = media(fechamentos, 9)
    sma_longa = media(fechamentos, 21)
    rsi_atual = rsi(fechamentos)
    resistencia = max(c["high"] for c in candles[-24:-1])
    suporte = min(c["low"] for c in candles[-24:-1])
    volume_atual = volumes[-1]
    volume_medio = media(volumes, 24)
    variacao_24h = ((fechamentos[-1] - fechamentos[-24]) / fechamentos[-24] * 100) if len(fechamentos) >= 24 else 0

    score = 50
    motivos = []

    if sma_curta > sma_longa:
        score += 18
        motivos.append("media_curta_acima")
    else:
        score -= 12
        motivos.append("media_curta_abaixo")

    if 42 <= rsi_atual <= 68:
        score += 12
        motivos.append("rsi_saudavel")
    elif rsi_atual < 32:
        score += 6
        motivos.append("sobrevenda")
    elif rsi_atual > 74:
        score -= 20
        motivos.append("sobrecompra")

    if preco >= resistencia * 0.995:
        score += 14
        motivos.append("rompimento")
    elif preco <= suporte * 1.01:
        score -= 8
        motivos.append("perto_suporte")

    if volume_medio and volume_atual > volume_medio * 1.25:
        score += 10
        motivos.append("volume_acima_media")

    if variacao_24h > 2:
        score += 8
        motivos.append("momentum_24h")
    elif variacao_24h < -4:
        score -= 14
        motivos.append("queda_24h")

    score = max(0, min(100, score))
    if score >= env_int("BUY_SCORE", 74):
        sinal = "BUY"
    elif score <= env_int("SELL_SCORE", 36):
        sinal = "SELL"
    else:
        sinal = "HOLD"

    return {
        "symbol": symbol,
        "price": preco,
        "score": score,
        "signal": sinal,
        "rsi": rsi_atual,
        "support": suporte,
        "resistance": resistencia,
        "reason": ",".join(motivos[:4]),
    }


def ordem_market(symbol, side, quote_order_qty=None, quantity=None):
    params = {"symbol": symbol, "side": side, "type": "MARKET"}
    if side == "BUY":
        params["quoteOrderQty"] = f"{float(quote_order_qty):.8f}"
    else:
        params["quantity"] = f"{float(quantity):.8f}"

    testar = env_bool("BINANCE_TEST_ORDER", True) or not env_bool("BINANCE_REAL_TRADING_ENABLED", False)
    endpoint = "/api/v3/order/test" if testar else "/api/v3/order"
    return binance_request("POST", endpoint, params), testar


def comprar(state, analise, valor_usdt):
    symbol = analise["symbol"]
    preco = analise["price"]
    qty_estimado = valor_usdt / preco
    resposta, testar = ordem_market(symbol, "BUY", quote_order_qty=valor_usdt)

    pos = state["positions"].get(symbol, {"qty": 0.0, "avg": 0.0})
    custo_antigo = pos["qty"] * pos["avg"]
    nova_qty = pos["qty"] + qty_estimado
    pos["qty"] = nova_qty
    pos["avg"] = (custo_antigo + valor_usdt) / nova_qty
    state["positions"][symbol] = pos

    registrar_trade(
        {
            "time": agora(),
            "mode": "TEST" if testar else "REAL",
            "symbol": symbol,
            "side": "BUY",
            "qty": qty_estimado,
            "price": preco,
            "quote": valor_usdt,
            "reason": analise["reason"],
            "score": analise["score"],
        }
    )
    log(f"{'TESTE' if testar else 'REAL'} BUY {symbol} USDT {valor_usdt:.2f} score={analise['score']} resposta={resposta}")


def vender(state, analise, percentual, motivo_extra=""):
    symbol = analise["symbol"]
    pos = state["positions"].get(symbol)
    if not pos or pos["qty"] <= 0:
        return

    preco = analise["price"]
    qty = pos["qty"] * (percentual / 100)
    resposta, testar = ordem_market(symbol, "SELL", quantity=qty)
    pnl = (preco - pos["avg"]) * qty
    state["realized_pnl"] += pnl
    pos["qty"] -= qty

    if pos["qty"] <= 0.00000001:
        del state["positions"][symbol]
    else:
        state["positions"][symbol] = pos

    registrar_trade(
        {
            "time": agora(),
            "mode": "TEST" if testar else "REAL",
            "symbol": symbol,
            "side": "SELL",
            "qty": qty,
            "price": preco,
            "quote": qty * preco,
            "reason": f"{analise['reason']} {motivo_extra}".strip(),
            "score": analise["score"],
        }
    )
    log(f"{'TESTE' if testar else 'REAL'} SELL {symbol} qty={qty:.8f} pnl={pnl:.2f} resposta={resposta}")


def equity_estimado(state, analises):
    precos = {a["symbol"]: a["price"] for a in analises}
    posicoes = sum(pos["qty"] * precos.get(symbol, pos["avg"]) for symbol, pos in state["positions"].items())
    return state.get("cash_guard", 0) + posicoes + state.get("realized_pnl", 0)


def reset_diario(state, analises):
    hoje = datetime.now().strftime("%Y-%m-%d")
    if state.get("day") != hoje:
        state["day"] = hoje
        state["day_start_equity"] = equity_estimado(state, analises)
        state["halted"] = False


def ciclo():
    state = carregar_estado()
    symbols = [s.strip().upper() for s in os.getenv("BOT_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if s.strip()]
    valor_por_trade = env_float("BOT_USDT_PER_TRADE", 25)
    max_posicoes = env_int("BOT_MAX_POSITIONS", 3)
    stop_loss = abs(env_float("BOT_STOP_LOSS_PCT", 5))
    take_profit = abs(env_float("BOT_TAKE_PROFIT_PCT", 10))
    daily_loss = abs(env_float("BOT_DAILY_LOSS_LIMIT_PCT", 3))

    analises = []
    for symbol in symbols:
        try:
            analises.append(analisar_symbol(symbol))
        except Exception as erro:
            log(f"Falha ao analisar {symbol}: {erro}")

    if not analises:
        log("Nenhuma análise disponível neste ciclo.")
        return

    reset_diario(state, analises)
    equity = equity_estimado(state, analises)
    if state.get("day_start_equity") is None:
        state["day_start_equity"] = equity

    perda_dia_pct = 0
    if state["day_start_equity"]:
        perda_dia_pct = (state["day_start_equity"] - equity) / state["day_start_equity"] * 100

    if perda_dia_pct >= daily_loss:
        state["halted"] = True
        log(f"Trava diária ativada: perda estimada {perda_dia_pct:.2f}% >= {daily_loss:.2f}%.")

    if state.get("halted"):
        salvar_estado(state)
        return

    for analise in sorted(analises, key=lambda item: item["score"], reverse=True):
        symbol = analise["symbol"]
        pos = state["positions"].get(symbol)
        preco = analise["price"]

        log(
            f"{symbol} sinal={analise['signal']} score={analise['score']} "
            f"preco={preco:.6f} rsi={analise['rsi']:.2f}"
        )

        if pos:
            pnl_pct = ((preco - pos["avg"]) / pos["avg"] * 100) if pos["avg"] else 0
            if pnl_pct <= -stop_loss:
                vender(state, analise, 100, "stop_loss")
                continue
            if pnl_pct >= take_profit:
                vender(state, analise, 100, "take_profit")
                continue
            if analise["signal"] == "SELL":
                vender(state, analise, 50, "sell_signal")
                continue

        if (
            analise["signal"] == "BUY"
            and symbol not in state["positions"]
            and len(state["positions"]) < max_posicoes
        ):
            comprar(state, analise, valor_por_trade)

    salvar_estado(state)


def main():
    intervalo = env_int("BOT_INTERVAL_SECONDS", 300)
    log("Robô 24h iniciado.")
    log("Padrão seguro: BINANCE_TEST_ORDER=true e BINANCE_REAL_TRADING_ENABLED=false.")

    while True:
        try:
            ciclo()
        except KeyboardInterrupt:
            log("Robô encerrado manualmente.")
            break
        except Exception as erro:
            log(f"Erro no ciclo principal: {erro}")
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
