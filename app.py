import streamlit as st
import requests
import pandas as pd
import math

# Configuração da página web
st.set_page_config(page_title="Backtest V6 Quant", page_icon="🤖", layout="wide")

st.title("🤖 Laboratório de Backtest Quantitativo (V6)")
st.markdown("Testador de estratégia com Trailing Stop Adaptativo (ATR) + EMA200 + RSI")

# Painel lateral para configurações do utilizador
st.sidebar.header("⚙️ Parâmetros do Teste")
moeda_input = st.sidebar.text_input("Moeda (ex: BTCUSDT, SOLUSDT):", "BTCUSDT").upper().strip()
capital_inicial = st.sidebar.number_input("Capital Inicial ($):", min_value=10.0, value=100.0)
horas_historico = st.sidebar.slider("Horas de Histórico:", min_value=300, max_value=1000, value=1000)

if st.sidebar.button("🚀 Iniciar Backtest", type="primary"):
    
    if not moeda_input.endswith("USDT"):
        moeda_input += "USDT"
        
    progresso = st.progress(0, text=f"A descarregar {horas_historico} horas de {moeda_input}...")
    
    try:
        # 1. Busca de Dados
        url = f"https://api.binance.com/api/v3/klines?symbol={moeda_input}&interval=1h&limit={horas_historico}"
        velas = requests.get(url).json()
        
        if not isinstance(velas, list) or len(velas) < 260:
            st.error("Histórico insuficiente ou moeda inválida na Binance.")
            st.stop()

        progresso.progress(40, text="A calcular indicadores (EMA, RSI, ATR)...")

        # 2. Construção do DataFrame e Matemática (Igual ao seu código original)
        df = pd.DataFrame(velas, columns=["t", "o", "h", "l", "c", "v", "ct", "qav", "nt", "tbv", "tqv", "ig"])
        df[["o", "h", "l", "c", "v"]] = df[["o", "h", "l", "c", "v"]].astype(float)

        df["ema_200"] = df["c"].ewm(span=200, adjust=False).mean()
        delta = df["c"].diff()
        ganho = delta.clip(lower=0).rolling(window=14).mean()
        perda = (-delta.clip(upper=0)).rolling(window=14).mean()
        rs = ganho / perda.replace(0, math.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        df["prev_c"] = df["c"].shift(1)
        df["tr1"] = df["h"] - df["l"]
        df["tr2"] = (df["h"] - df["prev_c"]).abs()
        df["tr3"] = (df["l"] - df["prev_c"]).abs()
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)
        df["atr"] = df["tr"].rolling(window=14).mean()

        progresso.progress(70, text="A simular operações no mercado...")

        # 3. Motor de Simulação
        trades_ganhos = 0
        trades_perdidos = 0
        capital_simulado = capital_inicial
        i = 250
        
        historico_trades = [] # Lista para mostrar na tela depois

        while i < len(df) - 1:
            atual = df.iloc[i]
            janela_24h = df.iloc[i - 24 : i]
            resistencia = janela_24h["h"].max()
            vol_medio = janela_24h["v"].mean()

            # A sua lógica exata de gatilho V6
            entrada_valida = (
                atual["h"] >= resistencia
                and atual["v"] > (vol_medio * 1.5)
                and atual["h"] > atual["ema_200"]
                and atual["rsi"] < 70
                and not pd.isna(atual["atr"])
            )

            if not entrada_valida:
                i += 1
                continue

            preco_entrada = max(resistencia, atual["o"])
            atr_entrada = atual["atr"]
            sl_dinamico = preco_entrada - (atr_entrada * 2)
            fechamento_idx = None

            # Procura a saída da operação
            for j in range(i + 1, len(df)):
                vela = df.iloc[j]

                # Bateu no Stop (seja ele de perda ou o trailing stop de lucro)
                if vela["l"] <= sl_dinamico:
                    resultado_trade = (sl_dinamico - preco_entrada) / preco_entrada
                    lucro_dolar = capital_simulado * resultado_trade
                    capital_simulado += lucro_dolar
                    fechamento_idx = j

                    if resultado_trade > 0:
                        trades_ganhos += 1
                        status = "✅ WIN (Trailing Stop)"
                    else:
                        trades_perdidos += 1
                        status = "❌ LOSS (Stop Loss)"
                        
                    historico_trades.append({
                        "Vela Entrada": i,
                        "Vela Saída": j,
                        "Preço Entrada": f"${preco_entrada:.4f}",
                        "Preço Saída": f"${sl_dinamico:.4f}",
                        "Resultado (%)": f"{resultado_trade * 100:.2f}%",
                        "Lucro/Prejuízo ($)": f"${lucro_dolar:.2f}",
                        "Status": status
                    })
                    break

                # Atualiza o Trailing Stop se o preço subir
                novo_sl_possivel = vela["h"] - (atr_entrada * 2)
                if novo_sl_possivel > sl_dinamico:
                    sl_dinamico = novo_sl_possivel

            if fechamento_idx is None:
                break
            i = fechamento_idx + 1

        progresso.empty()

        # 4. Apresentação dos Resultados no Web App
        total_trades = trades_ganhos + trades_perdidos
        taxa_acerto = (trades_ganhos / total_trades * 100) if total_trades else 0
        lucro_total = capital_simulado - capital_inicial

        st.subheader(f"📊 Relatório de Performance: {moeda_input}")
        
        # Cria caixas de métricas bonitas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Capital Final", f"${capital_simulado:.2f}", f"${lucro_total:.2f}")
        col2.metric("Total de Trades", total_trades)
        col3.metric("Taxa de Acerto", f"{taxa_acerto:.1f}%")
        col4.metric("Wins / Losses", f"{trades_ganhos} / {trades_perdidos}")
        
        st.divider()
        st.subheader("📜 Histórico de Operações")
        if historico_trades:
            st.dataframe(pd.DataFrame(historico_trades), use_container_width=True)
        else:
            st.info("Nenhuma operação atendeu aos critérios rigorosos da V6 neste período.")

    except Exception as erro:
        st.error(f"Erro durante o backtest: {erro}")