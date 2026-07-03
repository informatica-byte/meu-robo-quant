import hashlib
import hmac
import os
import time
from datetime import datetime
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


st.set_page_config(page_title="Meu App Crypto", page_icon="📱", layout="wide")

st.title("📱 Meu App Crypto - Robô Quant IA")

HEADERS = {
    "accept": "application/json",
    "user-agent": "Meu-App-Crypto/2.0",
}


def buscar_json(url, params=None, timeout=15):
    resposta = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resposta.raise_for_status()
    return resposta.json()


def buscar_segredo(nome, padrao=""):
    try:
        valor = st.secrets.get(nome, "")
    except Exception:
        valor = ""
    return valor or os.getenv(nome, padrao)


def binance_base_url():
    usar_testnet = str(buscar_segredo("BINANCE_USE_TESTNET", "true")).lower() == "true"
    base_padrao = "https://testnet.binance.vision" if usar_testnet else "https://api.binance.com"
    return buscar_segredo("BINANCE_BASE_URL", base_padrao).rstrip("/")


def binance_credenciais():
    return buscar_segredo("BINANCE_API_KEY"), buscar_segredo("BINANCE_API_SECRET")


def binance_assinar(params, api_secret):
    query = urlencode(params, doseq=True)
    assinatura = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**params, "signature": assinatura}


def binance_request(method, path, params=None):
    api_key, api_secret = binance_credenciais()
    if not api_key or not api_secret:
        raise RuntimeError("Configure BINANCE_API_KEY e BINANCE_API_SECRET nos secrets do Streamlit.")

    params = params or {}
    params = {
        **params,
        "recvWindow": 5000,
        "timestamp": int(time.time() * 1000),
    }
    params = binance_assinar(params, api_secret)
    resposta = requests.request(
        method,
        f"{binance_base_url()}{path}",
        params=params,
        headers={"X-MBX-APIKEY": api_key},
        timeout=15,
    )
    resposta.raise_for_status()
    if not resposta.text:
        return {"status": "OK"}
    return resposta.json()


def binance_conta():
    return binance_request("GET", "/api/v3/account", {"omitZeroBalances": "true"})


def binance_ordem_market(symbol, side, quote_order_qty=None, quantity=None, testar=True):
    params = {
        "symbol": symbol.upper().strip(),
        "side": side,
        "type": "MARKET",
    }
    if side == "BUY":
        params["quoteOrderQty"] = f"{float(quote_order_qty):.8f}"
    else:
        params["quantity"] = f"{float(quantity):.8f}"

    endpoint = "/api/v3/order/test" if testar else "/api/v3/order"
    return binance_request("POST", endpoint, params)


def binance_ordens_abertas(symbol=""):
    params = {"symbol": symbol.upper().strip()} if symbol else {}
    return binance_request("GET", "/api/v3/openOrders", params)


@st.cache_data(ttl=300)
def buscar_mercado():
    return buscar_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
            "locale": "en",
        },
    )


@st.cache_data(ttl=1800)
def buscar_dolar_brl():
    try:
        dados = buscar_json("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        return float(dados["rates"]["BRL"])
    except Exception:
        return 5.50


@st.cache_data(ttl=300)
def buscar_ohlc(coin_id, dias=7):
    return buscar_json(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
        params={"vs_currency": "usd", "days": dias},
    )


def formatar_numero(valor, casas=4):
    if valor is None:
        return 0.0
    return float(f"{float(valor):.{casas}f}")


def formatar_opcao(moeda):
    return f"{moeda['symbol'].upper()} - {moeda['name']}"


def filtrar_moedas(moedas, busca):
    if not busca:
        return moedas[:20]

    busca = busca.lower()
    return [
        moeda
        for moeda in moedas
        if busca in moeda["symbol"].lower()
        or busca in moeda["name"].lower()
        or busca in moeda["id"].lower()
    ]


def dataframe_ohlc(moeda, dias=7):
    velas = buscar_ohlc(moeda["id"], dias=dias)
    df = pd.DataFrame(velas, columns=["tempo", "abertura", "maxima", "minima", "fechamento"])
    df["tempo"] = pd.to_datetime(df["tempo"], unit="ms")
    for coluna in ["abertura", "maxima", "minima", "fechamento"]:
        df[coluna] = df[coluna].astype(float)
    return df


def calcular_rsi(series, periodo=14):
    delta = series.diff()
    ganhos = delta.clip(lower=0)
    perdas = -delta.clip(upper=0)
    media_ganhos = ganhos.rolling(periodo, min_periods=periodo).mean()
    media_perdas = perdas.rolling(periodo, min_periods=periodo).mean()
    rs = media_ganhos / media_perdas.replace(0, 0.000001)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.dropna().empty else 50.0


def analisar_moeda(moeda):
    preco = float(moeda["current_price"] or 0)
    variacao = float(moeda["price_change_percentage_24h"] or 0)
    volume = float(moeda["total_volume"] or 0)
    high_24h = float(moeda["high_24h"] or preco or 0)
    low_24h = float(moeda["low_24h"] or preco or 0)

    try:
        df = dataframe_ohlc(moeda, dias=7)
        fechamento = df["fechamento"]
        sma_curta = float(fechamento.rolling(4, min_periods=1).mean().iloc[-1])
        sma_longa = float(fechamento.rolling(12, min_periods=1).mean().iloc[-1])
        rsi = calcular_rsi(fechamento)
        resistencia = float(df["maxima"].iloc[:-1].max()) if len(df) > 1 else high_24h
        suporte = float(df["minima"].iloc[:-1].min()) if len(df) > 1 else low_24h
    except Exception:
        sma_curta = preco
        sma_longa = preco
        rsi = 50.0
        resistencia = high_24h
        suporte = low_24h

    score = 50
    motivos = []

    if sma_curta > sma_longa:
        score += 15
        motivos.append("tendência curta acima da longa")
    else:
        score -= 10
        motivos.append("tendência curta abaixo da longa")

    if 45 <= rsi <= 68:
        score += 10
        motivos.append("RSI saudável")
    elif rsi < 35:
        score += 8
        motivos.append("RSI em sobrevenda")
    elif rsi > 75:
        score -= 18
        motivos.append("RSI esticado")

    if variacao > 2:
        score += 10
        motivos.append("força nas últimas 24h")
    elif variacao < -4:
        score -= 12
        motivos.append("queda forte nas últimas 24h")

    if resistencia and preco >= resistencia * 0.98:
        score += 12
        motivos.append("perto de rompimento")

    if volume > 100_000_000:
        score += 8
        motivos.append("volume forte")

    score = max(0, min(100, score))

    if score >= 72:
        sinal = "COMPRA"
        acao = "🟢 Comprar"
    elif score <= 38:
        sinal = "VENDA"
        acao = "🔴 Vender/Evitar"
    else:
        sinal = "AGUARDAR"
        acao = "🟡 Aguardar"

    return {
        "id": moeda["id"],
        "Ativo": moeda["symbol"].upper(),
        "Nome": moeda["name"],
        "Preço (US$)": preco,
        "Variação 24h": variacao,
        "Volume (US$)": volume,
        "RSI": rsi,
        "Suporte": suporte,
        "Resistência": resistencia,
        "Score IA": score,
        "Sinal": sinal,
        "Ação": acao,
        "Motivos": ", ".join(motivos[:3]),
    }


def desenhar_grafico(moeda):
    try:
        df = dataframe_ohlc(moeda, dias=7)
    except Exception as erro:
        st.warning(f"Não foi possível carregar o gráfico de {moeda['symbol'].upper()}: {erro}")
        return

    simbolo = moeda["symbol"].upper()
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["tempo"],
                open=df["abertura"],
                high=df["maxima"],
                low=df["minima"],
                close=df["fechamento"],
                name="Preço",
            )
        ]
    )

    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["fechamento"].rolling(4, min_periods=1).mean(),
            mode="lines",
            name="Média curta",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["fechamento"].rolling(12, min_periods=1).mean(),
            mode="lines",
            name="Média longa",
        )
    )

    fig.update_layout(
        title=f"📊 Análise Gráfica: {simbolo} (últimos 7 dias)",
        template="plotly_dark",
        yaxis_title="Preço (US$)",
        xaxis_title="Tempo",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)


def montar_carteira(moedas, dolar_hoje):
    precos = {moeda["id"]: moeda for moeda in moedas}
    linhas = []

    for item in st.session_state.carteira:
        moeda = precos.get(item["id"])
        if not moeda:
            continue

        preco_atual = float(moeda["current_price"] or 0)
        quantidade = float(item["quantidade"])
        preco_medio = float(item["preco_medio"])
        custo = quantidade * preco_medio
        valor_atual = quantidade * preco_atual
        resultado = valor_atual - custo
        resultado_pct = (resultado / custo * 100) if custo else 0

        linhas.append(
            {
                "Ativo": moeda["symbol"].upper(),
                "Nome": moeda["name"],
                "Quantidade": quantidade,
                "Preço Médio (US$)": preco_medio,
                "Preço Atual (US$)": preco_atual,
                "Valor Atual (US$)": valor_atual,
                "Valor Atual (R$)": valor_atual * dolar_hoje,
                "Resultado (US$)": resultado,
                "Resultado (%)": resultado_pct,
            }
        )

    return pd.DataFrame(linhas)


def registrar_trade(tipo, moeda, quantidade, preco):
    st.session_state.trade_log.append(
        {
            "Hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "Tipo": tipo,
            "Ativo": moeda["symbol"].upper(),
            "Quantidade": quantidade,
            "Preço (US$)": preco,
            "Total (US$)": quantidade * preco,
        }
    )


def comprar_paper(moeda, valor_usd):
    preco = float(moeda["current_price"] or 0)
    if preco <= 0 or valor_usd <= 0:
        return "Preço ou valor inválido."
    if valor_usd > st.session_state.paper_cash:
        return "Saldo virtual insuficiente."

    quantidade = valor_usd / preco
    posicao = st.session_state.paper_posicoes.get(
        moeda["id"],
        {"quantidade": 0.0, "preco_medio": 0.0, "nome": moeda["name"], "symbol": moeda["symbol"].upper()},
    )
    custo_antigo = posicao["quantidade"] * posicao["preco_medio"]
    nova_quantidade = posicao["quantidade"] + quantidade
    posicao["quantidade"] = nova_quantidade
    posicao["preco_medio"] = (custo_antigo + valor_usd) / nova_quantidade

    st.session_state.paper_posicoes[moeda["id"]] = posicao
    st.session_state.paper_cash -= valor_usd
    registrar_trade("COMPRA", moeda, quantidade, preco)
    return f"Compra paper executada: {quantidade:.8f} {moeda['symbol'].upper()}."


def vender_paper(moeda, percentual=100):
    preco = float(moeda["current_price"] or 0)
    posicao = st.session_state.paper_posicoes.get(moeda["id"])
    if not posicao or posicao["quantidade"] <= 0:
        return "Não há posição virtual para vender."

    quantidade = posicao["quantidade"] * (percentual / 100)
    valor = quantidade * preco
    posicao["quantidade"] -= quantidade
    st.session_state.paper_cash += valor
    registrar_trade("VENDA", moeda, quantidade, preco)

    if posicao["quantidade"] <= 0.00000001:
        del st.session_state.paper_posicoes[moeda["id"]]
    else:
        st.session_state.paper_posicoes[moeda["id"]] = posicao

    return f"Venda paper executada: {quantidade:.8f} {moeda['symbol'].upper()}."


def rodar_robo_paper(moedas, saldo_por_trade, stop_loss, take_profit, max_posicoes):
    mensagens = []
    posicoes_abertas = len(st.session_state.paper_posicoes)

    for moeda in moedas[:20]:
        analise = analisar_moeda(moeda)
        posicao = st.session_state.paper_posicoes.get(moeda["id"])
        preco = float(moeda["current_price"] or 0)

        if posicao:
            preco_medio = float(posicao["preco_medio"])
            resultado_pct = ((preco - preco_medio) / preco_medio * 100) if preco_medio else 0

            if resultado_pct <= -abs(stop_loss):
                mensagens.append(vender_paper(moeda, 100))
                continue
            if resultado_pct >= abs(take_profit):
                mensagens.append(vender_paper(moeda, 100))
                continue
            if analise["Sinal"] == "VENDA":
                mensagens.append(vender_paper(moeda, 50))
                continue

        if (
            analise["Sinal"] == "COMPRA"
            and not posicao
            and posicoes_abertas < max_posicoes
            and st.session_state.paper_cash >= saldo_por_trade
        ):
            mensagens.append(comprar_paper(moeda, saldo_por_trade))
            posicoes_abertas += 1

    return mensagens or ["Robô analisou o mercado e não encontrou operação dentro das regras."]


def dataframe_paper(moedas):
    precos = {moeda["id"]: moeda for moeda in moedas}
    linhas = []

    for coin_id, posicao in st.session_state.paper_posicoes.items():
        moeda = precos.get(coin_id)
        if not moeda:
            continue
        preco = float(moeda["current_price"] or 0)
        quantidade = float(posicao["quantidade"])
        preco_medio = float(posicao["preco_medio"])
        valor = quantidade * preco
        resultado = valor - (quantidade * preco_medio)
        resultado_pct = (resultado / (quantidade * preco_medio) * 100) if preco_medio else 0
        linhas.append(
            {
                "Ativo": moeda["symbol"].upper(),
                "Nome": moeda["name"],
                "Quantidade": quantidade,
                "Preço Médio": preco_medio,
                "Preço Atual": preco,
                "Valor": valor,
                "Resultado": resultado,
                "Resultado %": resultado_pct,
            }
        )

    return pd.DataFrame(linhas)


if "carteira" not in st.session_state:
    st.session_state.carteira = []
if "paper_cash" not in st.session_state:
    st.session_state.paper_cash = 10_000.0
if "paper_posicoes" not in st.session_state:
    st.session_state.paper_posicoes = {}
if "trade_log" not in st.session_state:
    st.session_state.trade_log = []


aba_mercado, aba_ia, aba_robo, aba_binance, aba_carteira = st.tabs(
    ["📊 Mercado", "🧠 IA Quant", "🤖 Robô Paper", "🔐 Binance Real", "💼 Holdings"]
)

with aba_mercado:
    busca = st.text_input("🔍 Pesquisar ativo (Ex: BTC, SOL, NEAR)...", "").strip()

    if st.button("🔄 Atualizar Mercado", type="primary"):
        progresso = st.progress(0, text="A analisar o mercado...")

        try:
            dolar_hoje = buscar_dolar_brl()
            moedas = buscar_mercado()
            moedas_alvo = filtrar_moedas(moedas, busca)

            if busca and moedas_alvo:
                desenhar_grafico(moedas_alvo[0])

            resultados = []
            limite = min(len(moedas_alvo), 10)

            for idx, moeda in enumerate(moedas_alvo[:10]):
                analise = analisar_moeda(moeda)
                preco_dolar = analise["Preço (US$)"]

                progresso.progress(
                    int((idx + 1) / max(limite, 1) * 100),
                    text=f"A ler {analise['Ativo']}...",
                )

                resultados.append(
                    {
                        "Ativo": analise["Ativo"],
                        "Preço (US$)": formatar_numero(preco_dolar),
                        "Preço (R$)": formatar_numero(preco_dolar * dolar_hoje),
                        "Variação": f"{analise['Variação 24h']:.2f}%",
                        "Vol (US$)": formatar_numero(analise["Volume (US$)"] / 1_000_000, 2),
                        "Score IA": analise["Score IA"],
                        "Robô Quant": analise["Ação"],
                    }
                )
                time.sleep(0.05)

            progresso.empty()

            if resultados:
                st.caption("Dados via CoinGecko. O robô usa médias, RSI, volume, suporte e resistência.")
                st.dataframe(
                    pd.DataFrame(resultados),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Preço (US$)": st.column_config.NumberColumn(format="US$ %.4f"),
                        "Preço (R$)": st.column_config.NumberColumn(format="R$ %.4f"),
                        "Vol (US$)": st.column_config.NumberColumn(format="US$ %.2f M"),
                    },
                )
            else:
                st.warning("Nenhuma moeda encontrada.")

        except requests.HTTPError as erro:
            progresso.empty()
            st.error(
                "A API de mercado recusou a solicitação agora. "
                f"Tente novamente em alguns instantes. Detalhe: {erro}"
            )
        except Exception as erro:
            progresso.empty()
            st.error(f"Erro central: {erro}")

with aba_ia:
    st.caption("Motor educacional de sinais. Não é recomendação financeira.")

    try:
        moedas = buscar_mercado()
        universo = st.slider("Quantidade de ativos para escanear", 5, 30, 12)

        if st.button("🧠 Escanear oportunidades", type="primary"):
            progresso = st.progress(0, text="IA Quant analisando ativos...")
            analises = []

            for idx, moeda in enumerate(moedas[:universo]):
                progresso.progress(int((idx + 1) / universo * 100), text=f"Analisando {moeda['symbol'].upper()}...")
                analises.append(analisar_moeda(moeda))
                time.sleep(0.05)

            progresso.empty()
            df_ia = pd.DataFrame(analises).sort_values("Score IA", ascending=False)

            compras = int((df_ia["Sinal"] == "COMPRA").sum())
            vendas = int((df_ia["Sinal"] == "VENDA").sum())
            aguardando = int((df_ia["Sinal"] == "AGUARDAR").sum())

            col1, col2, col3 = st.columns(3)
            col1.metric("Compras potenciais", compras)
            col2.metric("Alertas de venda", vendas)
            col3.metric("Aguardando", aguardando)

            st.dataframe(
                df_ia[
                    [
                        "Ativo",
                        "Preço (US$)",
                        "Variação 24h",
                        "RSI",
                        "Suporte",
                        "Resistência",
                        "Score IA",
                        "Ação",
                        "Motivos",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Preço (US$)": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Variação 24h": st.column_config.NumberColumn(format="%.2f%%"),
                    "RSI": st.column_config.NumberColumn(format="%.2f"),
                    "Suporte": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Resistência": st.column_config.NumberColumn(format="US$ %.4f"),
                },
            )

            melhor = df_ia.iloc[0]
            st.success(
                f"Melhor setup agora: {melhor['Ativo']} com score {melhor['Score IA']}. "
                f"Ação sugerida: {melhor['Ação']}."
            )

    except Exception as erro:
        st.error(f"Não foi possível rodar a IA Quant agora: {erro}")

with aba_robo:
    st.caption("Compra e venda em modo paper trading. Nenhuma ordem real é enviada para corretoras.")

    try:
        moedas = buscar_mercado()
        moedas_por_label = {formatar_opcao(moeda): moeda for moeda in moedas}

        cfg1, cfg2, cfg3, cfg4 = st.columns(4)
        with cfg1:
            saldo_por_trade = st.number_input("US$ por compra", min_value=10.0, value=250.0, step=10.0)
        with cfg2:
            stop_loss = st.number_input("Stop loss (%)", min_value=1.0, value=6.0, step=0.5)
        with cfg3:
            take_profit = st.number_input("Take profit (%)", min_value=1.0, value=12.0, step=0.5)
        with cfg4:
            max_posicoes = st.number_input("Máx. posições", min_value=1, value=5, step=1)

        col_saldo, col_reset = st.columns([2, 1])
        with col_saldo:
            novo_saldo = st.number_input("Saldo virtual inicial/ajuste", min_value=0.0, value=st.session_state.paper_cash)
        with col_reset:
            if st.button("♻️ Ajustar saldo"):
                st.session_state.paper_cash = novo_saldo
                st.rerun()

        saldo_posicoes = dataframe_paper(moedas)
        valor_posicoes = 0 if saldo_posicoes.empty else float(saldo_posicoes["Valor"].sum())
        patrimonio_total = st.session_state.paper_cash + valor_posicoes

        m1, m2, m3 = st.columns(3)
        m1.metric("Caixa virtual", f"US$ {st.session_state.paper_cash:,.2f}")
        m2.metric("Em posições", f"US$ {valor_posicoes:,.2f}")
        m3.metric("Patrimônio paper", f"US$ {patrimonio_total:,.2f}")

        acao1, acao2, acao3 = st.columns(3)
        with acao1:
            if st.button("🤖 Rodar robô agora", type="primary"):
                mensagens = rodar_robo_paper(moedas, saldo_por_trade, stop_loss, take_profit, max_posicoes)
                for mensagem in mensagens:
                    st.info(mensagem)
                st.rerun()
        with acao2:
            ativo_manual = st.selectbox("Ativo manual", list(moedas_por_label.keys()))
        with acao3:
            valor_manual = st.number_input("Valor manual (US$)", min_value=10.0, value=100.0, step=10.0)

        b1, b2 = st.columns(2)
        moeda_manual = moedas_por_label[ativo_manual]
        if b1.button("🟢 Comprar manual"):
            st.success(comprar_paper(moeda_manual, valor_manual))
            st.rerun()
        if b2.button("🔴 Vender 100% manual"):
            st.success(vender_paper(moeda_manual, 100))
            st.rerun()

        df_paper = dataframe_paper(moedas)
        if df_paper.empty:
            st.info("Sem posições virtuais. Rode o robô ou faça uma compra manual.")
        else:
            st.dataframe(
                df_paper,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Quantidade": st.column_config.NumberColumn(format="%.8f"),
                    "Preço Médio": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Preço Atual": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Valor": st.column_config.NumberColumn(format="US$ %.2f"),
                    "Resultado": st.column_config.NumberColumn(format="US$ %.2f"),
                    "Resultado %": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

        if st.session_state.trade_log:
            st.subheader("Histórico do Robô")
            st.dataframe(pd.DataFrame(st.session_state.trade_log), use_container_width=True, hide_index=True)

    except Exception as erro:
        st.error(f"Não foi possível carregar o robô paper agora: {erro}")

with aba_binance:
    st.warning(
        "Área de ordens reais. Por padrão, use validação/testnet. "
        "Ordem real só deve ser ativada depois de testar bem o robô paper."
    )

    api_key, api_secret = binance_credenciais()
    trading_habilitado = str(buscar_segredo("BINANCE_TRADING_ENABLED", "false")).lower() == "true"

    st.caption(
        "Configure no Streamlit Cloud em Settings > Secrets: "
        "BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_USE_TESTNET e, só quando quiser liberar, "
        "BINANCE_TRADING_ENABLED=true."
    )

    status1, status2, status3 = st.columns(3)
    status1.metric("Credenciais", "OK" if api_key and api_secret else "Faltando")
    status2.metric("Endpoint", binance_base_url().replace("https://", ""))
    status3.metric("Trading real", "Liberado" if trading_habilitado else "Bloqueado")

    col_conta, col_ordens = st.columns(2)
    with col_conta:
        if st.button("🔎 Ver saldo Binance"):
            try:
                conta = binance_conta()
                saldos = [
                    {
                        "Ativo": item["asset"],
                        "Livre": float(item["free"]),
                        "Travado": float(item["locked"]),
                    }
                    for item in conta.get("balances", [])
                    if float(item["free"]) > 0 or float(item["locked"]) > 0
                ]
                if saldos:
                    st.dataframe(pd.DataFrame(saldos), use_container_width=True, hide_index=True)
                else:
                    st.info("Conta conectada, mas sem saldos positivos retornados.")
            except Exception as erro:
                st.error(f"Falha ao consultar conta Binance: {erro}")

    with col_ordens:
        simbolo_ordens = st.text_input("Símbolo para ordens abertas", "BTCUSDT")
        if st.button("📋 Ver ordens abertas"):
            try:
                ordens = binance_ordens_abertas(simbolo_ordens)
                if ordens:
                    st.dataframe(pd.DataFrame(ordens), use_container_width=True)
                else:
                    st.info("Nenhuma ordem aberta para esse símbolo.")
            except Exception as erro:
                st.error(f"Falha ao consultar ordens: {erro}")

    st.subheader("Compra e venda manual")
    ordem1, ordem2, ordem3, ordem4 = st.columns(4)
    with ordem1:
        simbolo_ordem = st.text_input("Par", "BTCUSDT")
    with ordem2:
        lado_ordem = st.selectbox("Lado", ["BUY", "SELL"], format_func=lambda item: "Comprar" if item == "BUY" else "Vender")
    with ordem3:
        valor_compra = st.number_input("Compra em USDT", min_value=5.0, value=10.0, step=5.0)
    with ordem4:
        qtd_venda = st.number_input("Qtd. para venda", min_value=0.0, value=0.0, step=0.0001, format="%.8f")

    validar_apenas = st.toggle("Validar apenas, sem executar ordem real", value=True)
    confirmacao = st.text_input("Para ordem real, digite: EU ASSUMO O RISCO")

    pode_executar_real = trading_habilitado and confirmacao == "EU ASSUMO O RISCO" and not validar_apenas
    texto_botao = "✅ Validar ordem" if validar_apenas else "🚨 Enviar ordem REAL"

    if st.button(texto_botao, type="primary"):
        try:
            if not validar_apenas and not pode_executar_real:
                st.error(
                    "Ordem real bloqueada. Ative BINANCE_TRADING_ENABLED=true nos secrets "
                    "e digite a frase de confirmação exatamente."
                )
            elif lado_ordem == "BUY":
                resposta = binance_ordem_market(
                    simbolo_ordem,
                    "BUY",
                    quote_order_qty=valor_compra,
                    testar=validar_apenas,
                )
                st.success("Validação concluída." if validar_apenas else "Compra real enviada.")
                st.json(resposta)
            else:
                if qtd_venda <= 0:
                    st.warning("Informe a quantidade para venda.")
                else:
                    resposta = binance_ordem_market(
                        simbolo_ordem,
                        "SELL",
                        quantity=qtd_venda,
                        testar=validar_apenas,
                    )
                    st.success("Validação concluída." if validar_apenas else "Venda real enviada.")
                    st.json(resposta)
        except Exception as erro:
            st.error(f"Falha na ordem Binance: {erro}")

    st.subheader("Robô real")
    st.info(
        "A automação real contínua precisa rodar em servidor/cron, não dentro do clique do Streamlit. "
        "Esta aba deixa a conexão e as ordens manuais preparadas; o próximo passo é criar um worker "
        "com limites diários, logs persistentes e trava de perda."
    )

with aba_carteira:
    try:
        moedas = buscar_mercado()
        dolar_hoje = buscar_dolar_brl()
        moedas_por_label = {formatar_opcao(moeda): moeda for moeda in moedas}

        with st.form("form_carteira", clear_on_submit=True):
            col_ativo, col_qtd, col_preco = st.columns([2, 1, 1])

            with col_ativo:
                ativo_label = st.selectbox("Ativo", list(moedas_por_label.keys()), key="holding_ativo")
            with col_qtd:
                quantidade = st.number_input("Quantidade", min_value=0.0, step=0.01, format="%.8f")
            with col_preco:
                preco_medio = st.number_input("Preço médio (US$)", min_value=0.0, step=0.01, format="%.8f")

            adicionar = st.form_submit_button("➕ Adicionar / Atualizar", type="primary")

        if adicionar:
            moeda = moedas_por_label[ativo_label]
            item_existente = next(
                (item for item in st.session_state.carteira if item["id"] == moeda["id"]),
                None,
            )

            if quantidade <= 0:
                st.warning("Informe uma quantidade maior que zero.")
            elif item_existente:
                item_existente["quantidade"] = quantidade
                item_existente["preco_medio"] = preco_medio
                st.success(f"{moeda['symbol'].upper()} atualizado na carteira.")
            else:
                st.session_state.carteira.append(
                    {
                        "id": moeda["id"],
                        "quantidade": quantidade,
                        "preco_medio": preco_medio,
                    }
                )
                st.success(f"{moeda['symbol'].upper()} adicionado à carteira.")

        df_carteira = montar_carteira(moedas, dolar_hoje)

        if df_carteira.empty:
            st.info("Adicione seus ativos acima para acompanhar patrimônio, resultado e alocação.")
        else:
            total_usd = float(df_carteira["Valor Atual (US$)"].sum())
            total_brl = float(df_carteira["Valor Atual (R$)"].sum())
            resultado_usd = float(df_carteira["Resultado (US$)"].sum())
            custo_total = total_usd - resultado_usd
            resultado_pct = (resultado_usd / custo_total * 100) if custo_total else 0

            metrica_total, metrica_brl, metrica_resultado = st.columns(3)
            metrica_total.metric("Patrimônio", f"US$ {total_usd:,.2f}")
            metrica_brl.metric("Patrimônio em R$", f"R$ {total_brl:,.2f}")
            metrica_resultado.metric("Resultado", f"US$ {resultado_usd:,.2f}", f"{resultado_pct:.2f}%")

            fig_alocacao = go.Figure(
                data=[
                    go.Pie(
                        labels=df_carteira["Ativo"],
                        values=df_carteira["Valor Atual (US$)"],
                        hole=0.45,
                    )
                ]
            )
            fig_alocacao.update_layout(
                title="Alocação da Carteira",
                template="plotly_dark",
                margin=dict(l=0, r=0, t=40, b=0),
                height=360,
            )
            st.plotly_chart(fig_alocacao, use_container_width=True)

            st.dataframe(
                df_carteira,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Quantidade": st.column_config.NumberColumn(format="%.8f"),
                    "Preço Médio (US$)": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Preço Atual (US$)": st.column_config.NumberColumn(format="US$ %.4f"),
                    "Valor Atual (US$)": st.column_config.NumberColumn(format="US$ %.2f"),
                    "Valor Atual (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    "Resultado (US$)": st.column_config.NumberColumn(format="US$ %.2f"),
                    "Resultado (%)": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )

            remover = st.multiselect("Remover ativos", df_carteira["Ativo"].tolist())
            if st.button("🗑️ Remover selecionados") and remover:
                simbolos_remover = {simbolo.lower() for simbolo in remover}
                st.session_state.carteira = [
                    item
                    for item in st.session_state.carteira
                    if next(
                        (moeda["symbol"].lower() for moeda in moedas if moeda["id"] == item["id"]),
                        "",
                    )
                    not in simbolos_remover
                ]
                st.rerun()

    except Exception as erro:
        st.error(f"Não foi possível carregar a carteira agora: {erro}")
