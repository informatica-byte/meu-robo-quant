import time

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st


st.set_page_config(page_title="Meu App Crypto", page_icon="📱", layout="wide")

st.title("📱 Meu App Crypto (Com Gráficos V6)")

HEADERS = {
    "accept": "application/json",
    "user-agent": "Meu-App-Crypto/1.0",
}


def buscar_json(url, params=None, timeout=15):
    resposta = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    resposta.raise_for_status()
    return resposta.json()


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
def buscar_ohlc(coin_id):
    return buscar_json(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
        params={"vs_currency": "usd", "days": 7},
    )


def formatar_numero(valor, casas=4):
    if valor is None:
        return 0.0
    return float(f"{float(valor):.{casas}f}")


def formatar_opcao(moeda):
    return f"{moeda['symbol'].upper()} - {moeda['name']}"


def desenhar_grafico(moeda):
    try:
        velas = buscar_ohlc(moeda["id"])
    except Exception as erro:
        st.warning(f"Não foi possível carregar o gráfico de {moeda['symbol'].upper()}: {erro}")
        return

    if not isinstance(velas, list) or not velas:
        st.warning(f"Não foi possível carregar o gráfico de {moeda['symbol'].upper()}.")
        return

    df_velas = pd.DataFrame(velas, columns=["t", "o", "h", "l", "c"])
    df_velas["t"] = pd.to_datetime(df_velas["t"], unit="ms")
    df_velas[["o", "h", "l", "c"]] = df_velas[["o", "h", "l", "c"]].astype(float)

    simbolo = moeda["symbol"].upper()
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df_velas["t"],
                open=df_velas["o"],
                high=df_velas["h"],
                low=df_velas["l"],
                close=df_velas["c"],
                name="Preço",
            )
        ]
    )

    fig.update_layout(
        title=f"📊 Análise Gráfica: {simbolo} (últimos 7 dias)",
        template="plotly_dark",
        yaxis_title="Preço (US$)",
        xaxis_title="Tempo",
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)


def calcular_resistencia(moeda):
    try:
        velas = buscar_ohlc(moeda["id"])
        maximas = [float(vela[2]) for vela in velas[:-1]]
        return max(maximas) if maximas else float(moeda["current_price"])
    except Exception:
        return float(moeda["high_24h"] or moeda["current_price"] or 0)


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


if "carteira" not in st.session_state:
    st.session_state.carteira = []


aba_mercado, aba_carteira = st.tabs(["📊 Cripto (Spot)", "💼 Holdings"])

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
                nome = moeda["symbol"].upper()
                preco_dolar = float(moeda["current_price"] or 0)
                preco_reais = preco_dolar * dolar_hoje
                variacao = float(moeda["price_change_percentage_24h"] or 0)
                volume = float(moeda["total_volume"] or 0) / 1_000_000

                progresso.progress(
                    int((idx + 1) / max(limite, 1) * 100),
                    text=f"A ler resistência de {nome}...",
                )

                resistencia = calcular_resistencia(moeda)

                status = "-"
                if resistencia and preco_dolar >= resistencia:
                    status = "🔥 ROMPENDO!"
                elif resistencia and (preco_dolar / resistencia) >= 0.98:
                    status = "👀 Quase Rompendo"

                sinal_var = "🟢 +" if variacao >= 0 else "🔴 "

                resultados.append(
                    {
                        "Ativo": nome,
                        "Preço (US$)": formatar_numero(preco_dolar),
                        "Preço (R$)": formatar_numero(preco_reais),
                        "Variação": f"{sinal_var}{variacao:.2f}%",
                        "Vol (US$)": formatar_numero(volume, 2),
                        "Robô Quant": status,
                    }
                )

                time.sleep(0.05)

            progresso.empty()

            if resultados:
                st.caption("Dados de mercado e gráfico via CoinGecko. Cotação BRL via ExchangeRate API.")
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

with aba_carteira:
    try:
        moedas = buscar_mercado()
        dolar_hoje = buscar_dolar_brl()
        moedas_por_label = {formatar_opcao(moeda): moeda for moeda in moedas}

        with st.form("form_carteira", clear_on_submit=True):
            col_ativo, col_qtd, col_preco = st.columns([2, 1, 1])

            with col_ativo:
                ativo_label = st.selectbox("Ativo", list(moedas_por_label.keys()))
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
