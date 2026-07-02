import streamlit as st
import requests
import time
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Meu App Crypto", page_icon="📱", layout="wide")

st.title("📱 Meu App Crypto (Com Gráficos V6)")

# --- Função para desenhar o Gráfico ---
def desenhar_grafico(simbolo):
    url = f'https://api.binance.com/api/v3/klines?symbol={simbolo}&interval=1h&limit=72'
    velas = requests.get(url).json()
    
    df_velas = pd.DataFrame(velas, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'qav', 'nt', 'tbv', 'tqv', 'ig'])
    df_velas['t'] = pd.to_datetime(df_velas['t'], unit='ms')
    df_velas[['o', 'h', 'l', 'c']] = df_velas[['o', 'h', 'l', 'c']].astype(float)
    
    fig = go.Figure(data=[go.Candlestick(
        x=df_velas['t'], open=df_velas['o'], high=df_velas['h'],
        low=df_velas['l'], close=df_velas['c'], name="Preço"
    )])
    
    fig.update_layout(
        title=f'📊 Análise Gráfica: {simbolo.replace("USDT", "")} (Últimos 3 dias)',
        template='plotly_dark', yaxis_title='Preço (USDT)', xaxis_title='Tempo',
        margin=dict(l=0, r=0, t=40, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)
# ---------------------------------------

aba_mercado, aba_carteira = st.tabs(["📊 Cripto (Spot)", "💼 Holdings"])

with aba_mercado:
    busca = st.text_input("🔍 Pesquisar par (Ex: BTC, SOL, NEAR)...", "").upper().strip()
    
    if st.button("🔄 Atualizar Mercado", type="primary"):
        progresso = st.progress(0, text="A analisar o mercado...")
        
        try:
            # CORREÇÃO BLINDADA: Tenta uma API super estável. Se falhar, usa o Plano B.
            try:
                url_dolar = 'https://api.exchangerate-api.com/v4/latest/USD'
                dolar_hoje = float(requests.get(url_dolar, timeout=5).json()['rates']['BRL'])
            except:
                dolar_hoje = 5.50 # Plano B: O app NÃO quebra se a API do dólar falhar!
            
            url_ticker = 'https://api.binance.com/api/v3/ticker/24hr'
            dados = requests.get(url_ticker).json()
            
            moedas_usdt = [m for m in dados if m['symbol'].endswith('USDT') 
                           and m['symbol'] not in ['USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'USDTUSDT']]
            
            if busca:
                moedas_alvo = [m for m in moedas_usdt if busca in m['symbol']]
                if len(moedas_alvo) > 0:
                    simbolo_exato = moedas_alvo[0]['symbol']
                    desenhar_grafico(simbolo_exato)
            else:
                moedas_usdt.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
                moedas_alvo = moedas_usdt[:20]
            
            resultados = []

            for idx, moeda in enumerate(moedas_alvo[:10]):
                simbolo = moeda['symbol']
                nome = simbolo.replace('USDT', '')
                preco_dolar = float(moeda['lastPrice'])
                preco_reais = preco_dolar * dolar_hoje
                variacao = float(moeda['priceChangePercent'])
                volume = float(moeda['quoteVolume']) / 1_000_000
                
                progresso.progress(int((idx + 1) / min(len(moedas_alvo), 10) * 100), text=f"A ler resistência de {nome}...")
                
                url_klines = f'https://api.binance.com/api/v3/klines?symbol={simbolo}&interval=1h&limit=24'
                velas = requests.get(url_klines).json()
                maximas = [float(v[2]) for v in velas[:-1]]
                resistencia = max(maximas) if maximas else preco_dolar
                
                status = "-"
                if preco_dolar >= resistencia:
                    status = "🔥 ROMPENDO!"
                elif (preco_dolar / resistencia) >= 0.98:
                    status = "👀 Quase Rompendo"
                
                sinal_var = "🟢 +" if variacao >= 0 else "🔴 "
                
                resultados.append({
                    "Ativo": nome,
                    "Preço (USDT)": float(f"{preco_dolar:.4f}"),
                    "Preço (R$)": float(f"{preco_reais:.4f}"),
                    "Variação": f"{sinal_var}{variacao:.2f}%",
                    "Vol ($)": float(f"{volume:.2f}"),
                    "Robô Quant": status
                })
                
                time.sleep(0.05)
                
            progresso.empty()
            
            if resultados:
                st.dataframe(
                    pd.DataFrame(resultados), 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "Preço (USDT)": st.column_config.NumberColumn(format="$ %f"),
                        "Preço (R$)": st.column_config.NumberColumn(format="R$ %f"),
                        "Vol ($)": st.column_config.NumberColumn(format="$ %f M")
                    }
                )
            else:
                st.warning("Nenhuma moeda encontrada.")
                
        except Exception as e:
            st.error(f"Erro central: {e}")

with aba_carteira:
    st.info("Aba de património em desenvolvimento.")
